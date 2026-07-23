"""Runtime state and all derived logic for SunSight.

Event-driven rather than polled: everything recomputes when a source entity
changes, which for sun.sun is about once a minute.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from homeassistant.util import dt as dt_util

from .const import (
    CLOUDINESS_MIN_CLEAR_SKY,
    CONF_CLEAR_THRESHOLD,
    CONF_FORECAST_OUTLOOK,
    CONF_FORECAST_RAIN_CHANCE,
    CONF_HUMIDITY,
    CONF_IRRADIANCE,
    CONF_MIN_ELEVATION,
    CONF_PRESSURE,
    CONF_PV_CLIP,
    CONF_PV_POWER,
    CONF_RAIN,
    CONF_TEMPERATURE,
    CONF_WIND_HEIGHT,
    CONF_WIND_SPEED,
    CONF_WINDOW_AZ_MAX,
    CONF_WINDOW_AZ_MIN,
    CONF_WINDOW_LUX,
    CONF_WINDOW_LUX_THRESHOLD,
    DEFAULT_CLEAR_THRESHOLD,
    DEFAULT_CLOUDINESS_RATIO,
    DEFAULT_FORECAST_RAIN_MAX,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_PV_CLIP_KW,
    DEFAULT_WIND_HEIGHT,
    DEFAULT_WINDOW_AZ_MAX,
    DEFAULT_WINDOW_AZ_MIN,
    DEFAULT_WINDOW_LUX_THRESHOLD,
    ET_MAX_STEP_HOURS,
    FINE_OUTLOOKS,
    MIN_INDEX_ELEVATION,
    PV_MIN_ELEVATION,
    SAVE_DELAY,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .evapotranspiration import eto_hourly
from .pv_envelope import PVEnvelope
from .solar import (
    clear_sky_ghi,
    clear_sky_index,
    describe_sunlight,
    in_azimuth_window,
)

_LOGGER = logging.getLogger(__name__)

SUN_ENTITY = "sun.sun"

_UNAVAILABLE = ("unknown", "unavailable", "", None)


class SunSightManager:
    """Owns all SunSight state for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribe: list[Callable[[], None]] = []
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self.envelope = PVEnvelope(self._opt(CONF_PV_CLIP, DEFAULT_PV_CLIP_KW))
        # Evapotranspiration accumulator state.
        self._et_total: float = 0.0
        self._et_date: str | None = None
        self._et_last_tick: float | None = None
        self._cloudiness_ratio: float = DEFAULT_CLOUDINESS_RATIO

    # -- config ---------------------------------------------------------

    def _opt(self, key: str, default=None):
        """Options win over the original config, so edits take effect."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    # -- lifecycle ------------------------------------------------------

    async def async_setup(self) -> None:
        stored = await self._store.async_load() or {}
        self.envelope.load(stored.get("envelope"))
        self._load_et(stored.get("evapotranspiration"))

        tracked = [SUN_ENTITY]
        for key in (
            CONF_WINDOW_LUX,
            CONF_IRRADIANCE,
            CONF_PV_POWER,
            CONF_RAIN,
            CONF_FORECAST_OUTLOOK,
            CONF_FORECAST_RAIN_CHANCE,
            CONF_TEMPERATURE,
            CONF_HUMIDITY,
            CONF_WIND_SPEED,
            CONF_PRESSURE,
        ):
            entity_id = self._opt(key)
            if entity_id:
                tracked.append(entity_id)

        self._unsubscribe.append(
            async_track_state_change_event(self.hass, tracked, self._handle_change)
        )

    async def async_unload(self) -> None:
        for unsub in self._unsubscribe:
            unsub()
        self._unsubscribe.clear()
        # Flush pending writes so learning and the daily total survive a reload.
        await self._store.async_save(self._storage_payload())

    def _storage_payload(self) -> dict:
        return {
            "envelope": self.envelope.as_dict(),
            "evapotranspiration": {"total": self._et_total, "date": self._et_date},
        }

    def _load_et(self, data: dict | None) -> None:
        if not data:
            return
        total = data.get("total")
        if isinstance(total, (int, float)):
            self._et_total = float(total)
        date = data.get("date")
        if isinstance(date, str):
            self._et_date = date

    @callback
    def _handle_change(self, event: Event[EventStateChangedData]) -> None:
        if event.data.get("entity_id") == self._opt(CONF_PV_POWER):
            self._learn_pv()
        self._update_cloudiness()
        self._accumulate_et()
        self._notify()

    # -- listeners ------------------------------------------------------

    def register_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # -- source readings ------------------------------------------------

    def _float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNAVAILABLE:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _sun_attr(self, attribute: str) -> float | None:
        state = self.hass.states.get(SUN_ENTITY)
        if state is None:
            return None
        value = state.attributes.get(attribute)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def sun_elevation(self) -> float | None:
        return self._sun_attr("elevation")

    @property
    def sun_azimuth(self) -> float | None:
        return self._sun_attr("azimuth")

    @property
    def sun_up(self) -> bool:
        state = self.hass.states.get(SUN_ENTITY)
        return bool(state and state.state == "above_horizon")

    @property
    def sun_rising(self) -> bool | None:
        """Whether the sun is climbing (morning) or sinking (evening).

        None when sun.sun does not expose the attribute, so callers can tell
        "unknown direction" apart from a definite morning or evening.
        """
        state = self.hass.states.get(SUN_ENTITY)
        if state is None:
            return None
        value = state.attributes.get("rising")
        return bool(value) if value is not None else None

    @property
    def raining(self) -> bool:
        """True only when the rain sensor explicitly says wet.

        Fail-open on purpose: an unavailable rain sensor should not be able
        to suppress detection that the light sensors can make on their own.
        """
        entity_id = self._opt(CONF_RAIN)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return bool(state and state.state == "on")

    # -- clear sky ------------------------------------------------------

    @property
    def sky_status(self) -> str:
        """Human-readable reason the indices read what they do.

        Exists because a numeric sensor cannot say "night" in its state, and
        a bare 0 overnight invites the question of whether it has broken.
        """
        elevation = self.sun_elevation
        if elevation is None:
            return "Sun position unavailable"
        if not self.sun_up:
            return "Night"
        if elevation < MIN_INDEX_ELEVATION:
            return "Sun too low to measure"
        return "Measuring"

    @property
    def clear_sky_index(self) -> float | None:
        """Percentage of clear-sky irradiance, from a pyranometer/lux station.

        None only when a source is genuinely missing - that is a fault worth
        surfacing. A sun below the measurable threshold reports 0 instead,
        so the entity stays numeric and continuous overnight.
        """
        elevation = self.sun_elevation
        measured = self._float(self._opt(CONF_IRRADIANCE))
        if elevation is None or measured is None:
            return None
        if elevation < MIN_INDEX_ELEVATION:
            return 0.0
        return clear_sky_index(measured, elevation)

    @property
    def pv_clear_sky_index(self) -> float | None:
        """Percentage of the array's own clear-sky potential."""
        elevation = self.sun_elevation
        azimuth = self.sun_azimuth
        power = self._float(self._opt(CONF_PV_POWER))
        if elevation is None or azimuth is None or power is None:
            return None
        if elevation < PV_MIN_ELEVATION:
            return 0.0
        index = self.envelope.index(power, elevation, azimuth)
        return 0.0 if index is None else index

    @property
    def pv_expected(self) -> float | None:
        elevation = self.sun_elevation
        azimuth = self.sun_azimuth
        if elevation is None or azimuth is None or elevation < PV_MIN_ELEVATION:
            return None
        return self.envelope.expected(elevation, azimuth)

    @callback
    def _learn_pv(self) -> None:
        elevation = self.sun_elevation
        azimuth = self.sun_azimuth
        power = self._float(self._opt(CONF_PV_POWER))
        if elevation is None or azimuth is None or power is None:
            return
        if elevation < PV_MIN_ELEVATION or power <= 0:
            return
        self.envelope.observe(power, elevation, azimuth)
        self._store.async_delay_save(self._storage_payload, SAVE_DELAY)

    @property
    def sunlight_description(self) -> str | None:
        """Plain-English sunlight level, e.g. Darkness or Full sunshine.

        None only when sun position is unknown; unlike the numeric indices
        this stays useful without any irradiance or PV source, because at
        night the answer depends on the sun alone.
        """
        elevation = self.sun_elevation
        if elevation is None:
            return None
        return describe_sunlight(self.best_clear_index, elevation, self.sun_rising)

    @property
    def best_clear_index(self) -> float | None:
        """Preferred clear-sky signal.

        Irradiance wins when available: it measures the sky directly, whereas
        PV is an inference through hardware that can clip, soil, or be shaded.
        """
        index = self.clear_sky_index
        if index is not None:
            return index
        return self.pv_clear_sky_index

    # -- derived states -------------------------------------------------

    @property
    def beam_on(self) -> bool:
        """Is direct sun currently reaching the configured window?"""
        lux = self._float(self._opt(CONF_WINDOW_LUX))
        elevation = self.sun_elevation
        azimuth = self.sun_azimuth
        if lux is None or elevation is None or azimuth is None:
            return False
        if elevation <= 0:
            return False
        az_min = float(self._opt(CONF_WINDOW_AZ_MIN, DEFAULT_WINDOW_AZ_MIN))
        az_max = float(self._opt(CONF_WINDOW_AZ_MAX, DEFAULT_WINDOW_AZ_MAX))
        if not in_azimuth_window(azimuth, az_min, az_max):
            return False
        threshold = float(
            self._opt(CONF_WINDOW_LUX_THRESHOLD, DEFAULT_WINDOW_LUX_THRESHOLD)
        )
        return lux > threshold and not self.raining

    @property
    def fine_weather(self) -> bool:
        """Daylight, dry, and measurably sunny."""
        elevation = self.sun_elevation
        if elevation is None:
            return False
        if elevation <= float(self._opt(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION)):
            return False
        if self.raining:
            return False
        index = self.best_clear_index
        if index is None:
            return False
        return index > float(self._opt(CONF_CLEAR_THRESHOLD, DEFAULT_CLEAR_THRESHOLD))

    @property
    def forecast_outlook(self) -> str | None:
        entity_id = self._opt(CONF_FORECAST_OUTLOOK)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNAVAILABLE:
            return None
        return state.state

    @property
    def fine_day_expected(self) -> bool:
        """Forecast-driven: is today expected to be fine?"""
        if not self.sun_up:
            return False
        outlook = self.forecast_outlook
        if outlook is None:
            return False
        if outlook not in FINE_OUTLOOKS:
            return False
        rain_chance = self._float(self._opt(CONF_FORECAST_RAIN_CHANCE))
        if rain_chance is None:
            return True
        return rain_chance < DEFAULT_FORECAST_RAIN_MAX

    # -- evapotranspiration ---------------------------------------------

    @property
    def has_evapotranspiration(self) -> bool:
        """Every FAO-56 input must be configured for ET0 to mean anything."""
        return all(
            self._opt(key)
            for key in (
                CONF_IRRADIANCE,
                CONF_TEMPERATURE,
                CONF_HUMIDITY,
                CONF_WIND_SPEED,
                CONF_PRESSURE,
            )
        )

    @callback
    def _update_cloudiness(self) -> None:
        """Remember the daylight Rs/Rso ratio for use after dark.

        The net longwave term needs this ratio, but at night both terms are
        zero. FAO-56 directs you to carry forward the last daylight value.
        """
        elevation = self.sun_elevation
        measured = self._float(self._opt(CONF_IRRADIANCE))
        if elevation is None or measured is None:
            return
        expected = clear_sky_ghi(elevation)
        if expected < CLOUDINESS_MIN_CLEAR_SKY:
            return
        self._cloudiness_ratio = min(max(measured / expected, 0.25), 1.0)

    @property
    def evapotranspiration_rate(self) -> float | None:
        """Reference evapotranspiration rate [mm/hour]."""
        if not self.has_evapotranspiration:
            return None
        temp = self._float(self._opt(CONF_TEMPERATURE))
        humidity = self._float(self._opt(CONF_HUMIDITY))
        wind_kmh = self._float(self._opt(CONF_WIND_SPEED))
        pressure_hpa = self._float(self._opt(CONF_PRESSURE))
        solar = self._float(self._opt(CONF_IRRADIANCE))
        elevation = self.sun_elevation
        if None in (temp, humidity, wind_kmh, pressure_hpa, solar, elevation):
            return None

        return eto_hourly(
            temp_c=temp,
            humidity_pct=humidity,
            wind_ms=wind_kmh / 3.6,
            pressure_kpa=pressure_hpa / 10.0,
            solar_wm2=solar,
            clear_sky_wm2=clear_sky_ghi(elevation),
            cloudiness_ratio=self._cloudiness_ratio,
            is_daytime=elevation > 0,
            wind_height_m=float(self._opt(CONF_WIND_HEIGHT, DEFAULT_WIND_HEIGHT)),
        )

    @property
    def evapotranspiration_today(self) -> float | None:
        if not self.has_evapotranspiration:
            return None
        return self._et_total

    @callback
    def _accumulate_et(self) -> None:
        """Integrate the ET0 rate into a running daily total."""
        if not self.has_evapotranspiration:
            return

        now = dt_util.now()
        today = now.date().isoformat()
        if self._et_date != today:
            self._et_date = today
            self._et_total = 0.0
            self._et_last_tick = None

        rate = self.evapotranspiration_rate
        timestamp = now.timestamp()
        if rate is None:
            self._et_last_tick = timestamp
            return

        if self._et_last_tick is not None:
            hours = (timestamp - self._et_last_tick) / 3600.0
            # Clamp the step so a restart or stalled feed cannot project one
            # sampled rate across a long gap.
            hours = min(max(hours, 0.0), ET_MAX_STEP_HOURS)
            self._et_total += rate * hours
            self._store.async_delay_save(self._storage_payload, SAVE_DELAY)

        self._et_last_tick = timestamp
