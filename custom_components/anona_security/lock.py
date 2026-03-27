"""Lock platform for the Anona-backed integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity, LockEntityFeature

from .api import AnonaApi, AnonaApiError
from .const import DEVICE_TYPE_LOCK, DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

SCAN_INTERVAL = timedelta(seconds=UPDATE_INTERVAL_SECONDS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock entities from a config entry."""
    api: AnonaApi = hass.data[DOMAIN][entry.entry_id]
    devices = await api.get_devices()
    entities: list[IntegrationBlueprintLock] = []

    for device in devices:
        device_type = device.get("deviceType")
        if device_type is not None and int(device_type) != DEVICE_TYPE_LOCK:
            continue

        device_id = _device_identifier(device)
        if not device_id:
            _LOGGER.warning("Skipping lock device without an identifier: %s", device)
            continue

        name = str(device.get("deviceName") or "Anona Holo")
        entities.append(IntegrationBlueprintLock(api, device_id, name))

    if not entities:
        _LOGGER.warning("No compatible lock devices found in device list")

    async_add_entities(entities, update_before_add=True)


class IntegrationBlueprintLock(LockEntity):
    """Representation of an Anona Holo lock."""

    _attr_has_entity_name = True
    _attr_supported_features = LockEntityFeature(0)

    def __init__(self, api: AnonaApi, device_id: str, name: str) -> None:
        """Initialize the lock entity."""
        self._api = api
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_is_locked: bool | None = None
        self._attr_available = False
        self._attr_extra_state_attributes: dict[str, Any] = {"device_id": device_id}
        self._battery: int | None = None

    async def async_update(self) -> None:
        """Refresh the lock state from the cloud API."""
        try:
            status = await self._api.get_device_status(self._device_id)
        except AnonaApiError as err:
            _LOGGER.debug("Status poll failed for %s: %s", self._device_id, err)
            self._attr_available = False
            return

        self._attr_is_locked = self._api.is_locked(status)
        self._attr_available = self._api.is_online(status)
        self._battery = self._api.battery_level(status)
        self._attr_extra_state_attributes = {"device_id": self._device_id}
        if self._battery is not None:
            self._attr_extra_state_attributes["battery_level"] = self._battery

    async def async_lock(self, **_: Any) -> None:
        """Lock the device through the WebSocket command path."""
        await self._api.lock(self._device_id)
        self._attr_is_locked = True

    async def async_unlock(self, **_: Any) -> None:
        """Unlock the device through the WebSocket command path."""
        await self._api.unlock(self._device_id)
        self._attr_is_locked = False


def _device_identifier(device: dict[str, Any]) -> str | None:
    """Resolve the best identifier field from a device payload."""
    for key in ("deviceId", "sn", "did"):
        value = device.get(key)
        if value:
            return str(value)
    return None
