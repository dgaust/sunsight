"""SunSight - infer sky conditions from the sensors you already have."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import SunSightManager

type SunSightConfigEntry = ConfigEntry[SunSightManager]


async def async_setup_entry(hass: HomeAssistant, entry: SunSightConfigEntry) -> bool:
    """Set up SunSight from a config entry."""
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
