"""SunSight - infer sky conditions from the sensors you already have."""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, CARD_VERSION, DOMAIN, PLATFORMS
from .coordinator import SunSightManager

_LOGGER = logging.getLogger(__name__)

type SunSightConfigEntry = ConfigEntry[SunSightManager]

_CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
_CARD_REGISTERED = f"{DOMAIN}_card_registered"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace cards and auto-load them on the frontend.

    Best-effort: any failure here only means the user adds the resource by
    hand, so it must never block integration setup.

    The file is served *with* cache headers and auto-loaded as
    ``?v=<CARD_VERSION>``. Caching is a reliability feature, not just a speed
    one: an uncached module is re-fetched on every page load, and if it has
    not defined its custom elements before Lovelace renders, the card shows
    "Configuration error" instead. The version string busts that cache
    whenever the card actually changes.
    """
    if hass.data.get(_CARD_REGISTERED):
        return

    card_path = os.path.join(os.path.dirname(__file__), "www", CARD_FILENAME)
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_URL, card_path, True)]
        )
    except Exception:  # noqa: BLE001 - fall back to the legacy sync API
        try:
            hass.http.register_static_path(_CARD_URL, card_path, True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Could not serve the SunSight cards (%s); add %s as a Lovelace "
                "resource manually",
                err,
                card_path,
            )
            return

    # Only mark this done once the file is genuinely being served, so a failed
    # attempt can still be retried by a later setup or reload.
    hass.data[_CARD_REGISTERED] = True
    versioned_url = f"{_CARD_URL}?v={CARD_VERSION}"
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, versioned_url)
        _LOGGER.debug("Registered SunSight Lovelace cards at %s", versioned_url)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not auto-load the SunSight cards (%s); add the resource %s "
            "(JavaScript module) under Settings > Dashboards > Resources",
            err,
            versioned_url,
        )


async def async_setup_entry(hass: HomeAssistant, entry: SunSightConfigEntry) -> bool:
    """Set up SunSight from a config entry."""
    await _async_register_card(hass)

    manager = SunSightManager(hass, entry)
    await manager.async_setup()
    entry.runtime_data = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SunSightConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: SunSightConfigEntry) -> None:
    """Reload when options change, so edits take effect immediately."""
    await hass.config_entries.async_reload(entry.entry_id)
