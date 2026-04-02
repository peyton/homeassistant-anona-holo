"""Lock platform for the Anona Holo integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.helpers.device_registry import DeviceInfo

from .api import AnonaApi, AnonaApiError, DeviceContext, LockStatus, OnlineStatus
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
    entities = [
        AnonaHoloLock(api, device)
        for device in devices
        if device.device_type == DEVICE_TYPE_LOCK
    ]

    if not entities:
        _LOGGER.warning("No compatible lock devices found in device list")

    async_add_entities(entities, update_before_add=True)


class AnonaHoloLock(LockEntity):
    """Representation of a single Anona smart lock."""

    _attr_has_entity_name = True
    _attr_supported_features = LockEntityFeature(0)

    def __init__(self, api: AnonaApi, device: DeviceContext) -> None:
        """Initialize the lock entity."""
        self._api = api
        self._device = device
        self._attr_name = device.nickname
        self._attr_unique_id = f"{DOMAIN}_{device.device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            manufacturer="Anona Holo",
            model=self._device.model,
            name=self._device.nickname,
            serial_number=self._device.serial_number,
        )
        self._attr_is_locked: bool | None = None
        self._attr_available = False
        self._attr_extra_state_attributes = self._build_attrs(None, None)

    async def async_update(self) -> None:
        """Refresh online and lock-state information from the cloud API."""
        try:
            online_status = await self._api.get_device_online_status(self._device)
        except AnonaApiError as err:
            _LOGGER.debug("Online poll failed for %s: %s", self._device.device_id, err)
            self._attr_available = False
            return

        self._attr_available = online_status.online

        try:
            lock_status = await self._api.get_device_status(self._device)
        except AnonaApiError as err:
            _LOGGER.debug("Status poll failed for %s: %s", self._device.device_id, err)
            self._attr_extra_state_attributes = self._build_attrs(online_status, None)
            return

        self._attr_is_locked = lock_status.locked
        self._attr_extra_state_attributes = self._build_attrs(
            online_status, lock_status
        )

    async def async_lock(self, **_: Any) -> None:
        """Attempt to lock the device through the blocked command path."""
        await self._api.lock(self._device)

    async def async_unlock(self, **_: Any) -> None:
        """Attempt to unlock the device through the blocked command path."""
        await self._api.unlock(self._device)

    def _build_attrs(
        self,
        online_status: OnlineStatus | None,
        lock_status: LockStatus | None,
    ) -> dict[str, Any]:
        """Build the entity attribute mapping from the latest status objects."""
        attrs: dict[str, Any] = {
            "device_id": self._device.device_id,
            "device_type": self._device.device_type,
            "device_module": self._device.device_module,
            "device_channel": self._device.device_channel,
            "serial_number": self._device.serial_number,
            "model": self._device.model,
        }
        if online_status is not None:
            attrs["online"] = online_status.online
            attrs["create_ts"] = online_status.create_ts
            attrs["last_alive_ts"] = online_status.last_alive_ts
        if lock_status is not None:
            attrs["raw_data_hex_str"] = lock_status.data_hex_str
            attrs["raw_status_fields"] = lock_status.raw_fields
            attrs["lock_status_code"] = lock_status.lock_status_code
            attrs["door_state_code"] = lock_status.door_state_code
            attrs["door_status_code"] = lock_status.door_status_code
            attrs["has_locking_fail"] = lock_status.has_locking_fail
            attrs["has_door_been_open_long_time"] = (
                lock_status.has_door_been_open_long_time
            )
            attrs["calibration_status_code"] = lock_status.calibration_status_code
            attrs["charge_status_code"] = lock_status.charge_status_code
            attrs["long_endurance_mode_status_code"] = (
                lock_status.long_endurance_mode_status_code
            )
            attrs["keypad_connection_status_code"] = (
                lock_status.keypad_connection_status_code
            )
            attrs["keypad_battery_capacity"] = lock_status.keypad_battery_capacity
            attrs["keypad_status_code"] = lock_status.keypad_status_code
            attrs["refresh_ts"] = lock_status.refresh_ts
            attrs["start_type"] = lock_status.start_type
            if lock_status.battery_capacity is not None:
                attrs["battery_level"] = lock_status.battery_capacity
                attrs["lock_battery_capacity"] = lock_status.battery_capacity
            if lock_status.battery_voltage is not None:
                attrs["battery_voltage"] = lock_status.battery_voltage
        return attrs
