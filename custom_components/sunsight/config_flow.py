"""Config and options flow for SunSight."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    DEFAULT_MIN_ELEVATION,
    DEFAULT_PV_CLIP_KW,
    DEFAULT_WIND_HEIGHT,
    DEFAULT_WINDOW_AZ_MAX,
    DEFAULT_WINDOW_AZ_MIN,
    DEFAULT_WINDOW_LUX_THRESHOLD,
    DOMAIN,
)

# Every source entity is optional: SunSight degrades to whatever you have.
# A user with only PV still gets a clear-sky index; one with only a window
# sensor still gets beam detection.
_OPTIONAL_ENTITY_KEYS = (
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
)


def _number(minimum: float, maximum: float, step: float = 1.0, unit: str | None = None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _sensor(device_class: str | None = None):
    config = selector.EntitySelectorConfig(domain="sensor")
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _schema(defaults: dict[str, Any], include_name: bool) -> vol.Schema:
    """Build the form. `defaults` pre-fills it when editing."""

    def default(key, fallback=None):
        value = defaults.get(key, fallback)
        return {} if value is None else {"default": value}

    fields: dict[Any, Any] = {}
    if include_name:
        fields[vol.Required(CONF_NAME, default="SunSight")] = str

    fields.update(
        {
            vol.Optional(CONF_WINDOW_LUX, **default(CONF_WINDOW_LUX)): _sensor(
                "illuminance"
            ),
            vol.Optional(
                CONF_WINDOW_AZ_MIN,
                **default(CONF_WINDOW_AZ_MIN, DEFAULT_WINDOW_AZ_MIN),
            ): _number(0, 360, 1, "deg"),
            vol.Optional(
                CONF_WINDOW_AZ_MAX,
                **default(CONF_WINDOW_AZ_MAX, DEFAULT_WINDOW_AZ_MAX),
            ): _number(0, 360, 1, "deg"),
            vol.Optional(
                CONF_WINDOW_LUX_THRESHOLD,
                **default(CONF_WINDOW_LUX_THRESHOLD, DEFAULT_WINDOW_LUX_THRESHOLD),
            ): _number(0, 100000, 10, "lx"),
            vol.Optional(CONF_IRRADIANCE, **default(CONF_IRRADIANCE)): _sensor(
                "irradiance"
            ),
            vol.Optional(CONF_PV_POWER, **default(CONF_PV_POWER)): _sensor("power"),
            vol.Optional(
                CONF_PV_CLIP, **default(CONF_PV_CLIP, DEFAULT_PV_CLIP_KW)
            ): _number(0.1, 1000, 0.01, "kW"),
            vol.Optional(CONF_RAIN, **default(CONF_RAIN)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(
                CONF_FORECAST_OUTLOOK, **default(CONF_FORECAST_OUTLOOK)
            ): _sensor(),
            vol.Optional(
                CONF_FORECAST_RAIN_CHANCE, **default(CONF_FORECAST_RAIN_CHANCE)
            ): _sensor(),
            vol.Optional(
                CONF_CLEAR_THRESHOLD,
                **default(CONF_CLEAR_THRESHOLD, DEFAULT_CLEAR_THRESHOLD),
            ): _number(0, 100, 1, "%"),
            vol.Optional(
                CONF_MIN_ELEVATION,
                **default(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION),
            ): _number(-10, 90, 1, "deg"),
            # Evapotranspiration needs all four of these plus irradiance.
            vol.Optional(CONF_TEMPERATURE, **default(CONF_TEMPERATURE)): _sensor(
                "temperature"
            ),
            vol.Optional(CONF_HUMIDITY, **default(CONF_HUMIDITY)): _sensor("humidity"),
            vol.Optional(CONF_WIND_SPEED, **default(CONF_WIND_SPEED)): _sensor(
                "wind_speed"
            ),
            vol.Optional(CONF_PRESSURE, **default(CONF_PRESSURE)): _sensor(
                "atmospheric_pressure"
            ),
            vol.Optional(
                CONF_WIND_HEIGHT, **default(CONF_WIND_HEIGHT, DEFAULT_WIND_HEIGHT)
            ): _number(0.5, 50, 0.1, "m"),
        }
    )
    return vol.Schema(fields)


class SunSightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            title = user_input.pop(CONF_NAME, "SunSight")
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema({}, True))

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SunSightOptionsFlow()


class SunSightOptionsFlow(OptionsFlow):
    """Allow every setting to be changed after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # A cleared entity selector is simply absent from user_input, so
            # store None explicitly - otherwise the old value would survive
            # via the config-entry data fallback and the field could never
            # be emptied.
            cleaned = dict(user_input)
            for key in _OPTIONAL_ENTITY_KEYS:
                cleaned.setdefault(key, None)
            return self.async_create_entry(data=cleaned)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(current, False)
        )
