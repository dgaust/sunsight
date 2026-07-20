"""Sensors for SunSight."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_HUMIDITY,
    CONF_IRRADIANCE,
    CONF_PRESSURE,
    CONF_PV_POWER,
    CONF_TEMPERATURE,
    CONF_WIND_SPEED,
)
from .coordinator import SunSightManager
from .entity import SunSightEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SunSight sensors."""
    manager: SunSightManager = entry.runtime_data

    entities: list[SunSightEntity] = []
    if manager._opt(CONF_IRRADIANCE):
        entities.append(ClearSkyIndex(manager))
    if manager._opt(CONF_PV_POWER):
        entities.append(PVClearSkyIndex(manager))
    if manager.has_evapotranspiration:
        entities.append(EvapotranspirationRate(manager))
        entities.append(EvapotranspirationToday(manager))

    async_add_entities(entities)


class ClearSkyIndex(SunSightEntity, SensorEntity):
    """Measured irradiance as a percentage of the clear-sky expectation."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:white-balance-sunny"

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(manager, "clear_sky_index", "Clear sky index")

    @property
    def native_value(self) -> float | None:
        index = self.manager.clear_sky_index
        return None if index is None else round(index)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "irradiance": self.manager._float(self.manager._opt(CONF_IRRADIANCE)),
            "sun_elevation": self.manager.sun_elevation,
        }


class PVClearSkyIndex(SunSightEntity, SensorEntity):
    """PV generation as a percentage of this array's clear-sky potential."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:solar-power-variant"

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(manager, "pv_clear_sky_index", "PV clear sky index")

    @property
    def native_value(self) -> float | None:
        index = self.manager.pv_clear_sky_index
        return None if index is None else round(index)

    @property
    def extra_state_attributes(self) -> dict:
        expected = self.manager.pv_expected
        return {
            "pv_power": self.manager._float(self.manager._opt(CONF_PV_POWER)),
            "expected_clear_sky_power": None if expected is None else round(expected, 2),
            "sun_elevation": self.manager.sun_elevation,
            "sun_azimuth": self.manager.sun_azimuth,
            "learned_bins": self.manager.envelope.learned_bins,
        }


class EvapotranspirationRate(SunSightEntity, SensorEntity):
    """FAO-56 reference evapotranspiration, as an instantaneous rate."""

    _attr_native_unit_of_measurement = "mm/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-thermometer"
    _attr_suggested_display_precision = 3

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(manager, "evapotranspiration_rate", "Evapotranspiration rate")

    @property
    def native_value(self) -> float | None:
        rate = self.manager.evapotranspiration_rate
        return None if rate is None else round(rate, 4)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "temperature": self.manager._float(self.manager._opt(CONF_TEMPERATURE)),
            "humidity": self.manager._float(self.manager._opt(CONF_HUMIDITY)),
            "wind_speed": self.manager._float(self.manager._opt(CONF_WIND_SPEED)),
            "pressure": self.manager._float(self.manager._opt(CONF_PRESSURE)),
            "irradiance": self.manager._float(self.manager._opt(CONF_IRRADIANCE)),
            "cloudiness_ratio": round(self.manager._cloudiness_ratio, 2),
        }


class EvapotranspirationToday(SunSightEntity, SensorEntity):
    """Reference evapotranspiration accumulated since local midnight."""

    _attr_native_unit_of_measurement = "mm"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, manager: SunSightManager) -> None:
        super().__init__(
            manager, "evapotranspiration_today", "Evapotranspiration today"
        )

    @property
    def native_value(self) -> float | None:
        total = self.manager.evapotranspiration_today
        return None if total is None else round(total, 3)
