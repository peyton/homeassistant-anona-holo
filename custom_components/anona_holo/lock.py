"""Lock platform for the Anona Holo integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity, LockEntityFeature

from .const import DATA_COORDINATORS, DEVICE_TYPE_LOCK, DOMAIN
from .entity import AnonaHoloCoordinatorEntity

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import LockStatus, OnlineStatus
    from .coordinator import AnonaDeviceCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, AnonaDeviceCoordinator] = entry_data[DATA_COORDINATORS]

    entities = [
        AnonaHoloLock(coordinator)
        for coordinator in coordinators.values()
        if coordinator.device.device_type == DEVICE_TYPE_LOCK
    ]
    if not entities:
        _LOGGER.warning("No compatible lock devices found in device list")
    async_add_entities(entities)


class AnonaHoloLock(  # pyright: ignore[reportIncompatibleVariableOverride]
    AnonaHoloCoordinatorEntity,
    LockEntity,
):
    """Representation of a single Anona smart lock."""

    _attr_supported_features = LockEntityFeature(0)

    def __init__(self, coordinator: AnonaDeviceCoordinator) -> None:
        """Initialize the lock entity."""
        super().__init__(coordinator, unique_suffix="lock", name=None)
        self._apply_snapshot()

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and refresh Home Assistant attributes."""
        self._apply_snapshot()
        super()._handle_coordinator_update()

    def _apply_snapshot(self) -> None:
        """Apply latest coordinator snapshot fields to entity attributes."""
        snapshot = self.snapshot
        online_status = snapshot.online_status
        lock_status = snapshot.lock_status
        self._attr_available = bool(online_status and online_status.online)
        self._attr_is_locked = lock_status.locked if lock_status else None
        self._attr_extra_state_attributes = _build_attrs(
            snapshot.device,
            online_status,
            lock_status,
        )

    @property
    def available(  # pyright: ignore[reportIncompatibleVariableOverride]
        self,
    ) -> bool:
        """Combine coordinator success with lock online-state availability."""
        return super().available and bool(self._attr_available)

    async def async_lock(self, **_: Any) -> None:
        """Attempt to lock the device through the command path."""
        await self._api.lock(self._device)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **_: Any) -> None:
        """Attempt to unlock the device through the command path."""
        await self._api.unlock(self._device)
        await self.coordinator.async_request_refresh()


def _build_attrs(
    device: Any,
    online_status: OnlineStatus | None,
    lock_status: LockStatus | None,
) -> dict[str, Any]:
    """Build the lock attribute mapping from the latest status objects."""
    attrs: dict[str, Any] = {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "device_module": device.device_module,
        "device_channel": device.device_channel,
        "serial_number": device.serial_number,
        "model": device.model,
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
        attrs["has_door_been_open_long_time"] = lock_status.has_door_been_open_long_time
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
