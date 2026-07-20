"""Shared entity base for SunSight."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import SunSightManager


class SunSightEntity(Entity):
    """Base for every SunSight entity.

    All entities hang off one service device and repaint whenever the
    manager recomputes, rather than polling.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: SunSightManager, key: str, name: str) -> None:
        self.manager = manager
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{manager.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry.entry_id)},
            name=manager.entry.title,
            manufacturer="SunSight",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.register_listener(self.async_write_ha_state))
