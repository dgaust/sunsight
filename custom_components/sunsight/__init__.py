"""SunSight - infer sky conditions from the sensors you already have."""

from __future__ import annotations

import logging
import os

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, CARD_VERSION, DOMAIN, PLATFORMS
from .coordinator import SunSightManager
from .frontend import async_register_card_resource, async_remove_card_resource

_LOGGER = logging.getLogger(__name__)

type SunSightConfigEntry = ConfigEntry[SunSightManager]

CARD_PATH = f"/{DOMAIN}/{CARD_FILENAME}"
_CARD_SERVED = f"{DOMAIN}_card_served"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace cards and register them as a dashboard resource.

    Best-effort: a failure only costs the auto-registration (the log says what
    to add by hand), so it never blocks setup. The file is served with cache
    headers and the resource URL carries ``?v=<CARD_VERSION>``, so browsers
    keep the module until the cards actually change. See frontend.py for why
    this is a dashboard resource rather than an extra module.
    """
    try:
        if not hass.data.get(_CARD_SERVED):
            card_path = os.path.join(os.path.dirname(__file__), "www", CARD_FILENAME)
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_PATH, card_path, True)]
            )
            hass.data[_CARD_SERVED] = True
        await async_register_card_resource(hass, CARD_PATH, CARD_VERSION)
    except Exception:  # noqa: BLE001 - never block setup over the cards
        _LOGGER.warning(
            "Could not register the SunSight cards; add %s?v=%s as a dashboard "
            "resource (JavaScript module)",
            CARD_PATH,
            CARD_VERSION,
            exc_info=True,
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the card's dashboard resource with the integration's last entry."""
    others = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]
    if not others:
        await async_remove_card_resource(hass, CARD_PATH)
