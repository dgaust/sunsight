"""Binary sensors for SunSight."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_FORECAST_OUTLOOK,
    CONF_WINDOW_LUX,
    DEFAULT_WINDOW_AZ_MAX,
    DEFAULT_WINDOW_AZ_MIN,
    CONF_WINDOW_AZ_MAX,
    CONF_WINDOW_AZ_MIN,
)
from .coordinator import SunSightManager
from .entity import SunSightEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SunSight binary sensors."""
    manager: SunSightManager = entry.runtime_data

    entities: list[SunSightEntity] = [FineOutdoorWeather(manager)]

    # Only meaningful when a window light sensor was configured.
    if manager._opt(CONF_WINDOW_LUX):
        entities.append(SunOnWindow(manager))
    if manager._opt(CONF_FORECAST_OUTLOOK):
        entities.append(FineDayExpected(manager))

    async_add_entities(entities)


class SunOnWindow(SunSightEntity, BinarySensorEntity):
    """Direct sun reaching the configured window."""

    _attr_device_class = BinarySensorDeviceClass.LIGHT

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(manager, "sun_on_window", "Sun on window")

    @property
    def is_on(self) -> bool:
        return self.manager.beam_on

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "illuminance": self.manager._float(
                self.manager._opt(CONF_WINDOW_LUX)
            ),
            "sun_azimuth": self.manager.sun_azimuth,
            "sun_elevation": self.manager.sun_elevation,
            "window_azimuth_min": self.manager._opt(
                CONF_WINDOW_AZ_MIN, DEFAULT_WINDOW_AZ_MIN
            ),
            "window_azimuth_max": self.manager._opt(
                CONF_WINDOW_AZ_MAX, DEFAULT_WINDOW_AZ_MAX
            ),
            "raining": "Yes" if self.manager.raining else "No",
        }


class FineOutdoorWeather(SunSightEntity, BinarySensorEntity):
    """Daylight, dry, and measurably sunny."""

    _attr_icon = "mdi:weather-sunny"

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(manager, "fine_outdoor_weather", "Fine outdoor weather")

    @property
    def is_on(self) -> bool:
        return self.manager.fine_weather

    @property
    def extra_state_attributes(self) -> dict:
        index = self.manager.best_clear_index
        return {
            "clear_sky_index": self.manager.clear_sky_index,
            "pv_clear_sky_index": self.manager.pv_clear_sky_index,
            "clear_index_used": None if index is None else round(index),
            "sun_elevation": self.manager.sun_elevation,
            "raining": "Yes" if self.manager.raining else "No",
            "sun_on_window": "Yes" if self.manager.beam_on else "No",
        }


class FineDayExpected(SunSightEntity, BinarySensorEntity):
    """Forecast-driven outlook for the day."""

    _attr_icon = "mdi:weather-partly-sunny"

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(manager, "fine_day_expected", "Fine day expected")

    @property
    def is_on(self) -> bool:
        return self.manager.fine_day_expected

    @property
    def extra_state_attributes(self) -> dict:
        outlook = self.manager.forecast_outlook
        return {
            "outlook": outlook.replace("_", " ").capitalize() if outlook else None,
            "sun_up": "Yes" if self.manager.sun_up else "No",
        }
