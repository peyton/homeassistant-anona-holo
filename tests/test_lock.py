"""Tests for the Anona Holo lock entity."""

# ruff: noqa: S101, PLR2004

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

from custom_components.anona_holo.api import DeviceContext, LockStatus, OnlineStatus
from custom_components.anona_holo.const import (
    DATA_COORDINATORS,
    DEVICE_TYPE_LOCK,
    DOMAIN,
)
from custom_components.anona_holo.coordinator import AnonaDeviceSnapshot
from custom_components.anona_holo.lock import AnonaHoloLock, async_setup_entry

LOCK_DEVICE = DeviceContext(
    device_id="device-123",
    device_type=DEVICE_TYPE_LOCK,
    device_module=76001,
    device_channel=76001001,
    nickname="Front Door Lock",
    serial_number="SN-LOCK-123",
    model="SL2001",
    raw={"deviceId": "device-123"},
)
OTHER_DEVICE = DeviceContext(
    device_id="device-999",
    device_type=42,
    device_module=42001,
    device_channel=42001001,
    nickname="Ignored Sensor",
    serial_number="SN-SENSOR-999",
    model="SENSOR42",
    raw={"deviceId": "device-999"},
)
ONLINE_STATUS = OnlineStatus(
    online=True,
    create_ts=1775103001462,
    last_alive_ts=None,
    raw={"online": True},
)
OFFLINE_STATUS = OnlineStatus(
    online=False,
    create_ts=1775103001462,
    last_alive_ts=None,
    raw={"online": False},
)
LOCK_STATUS = LockStatus(
    locked=True,
    lock_status_code=1,
    battery_capacity=100,
    battery_voltage=180,
    charge_status_code=1,
    door_state_code=1,
    door_status_code=1,
    has_locking_fail=False,
    has_door_been_open_long_time=False,
    calibration_status_code=2,
    long_endurance_mode_status_code=0,
    keypad_connection_status_code=1,
    keypad_battery_capacity=1,
    keypad_status_code=2,
    data_hex_str="deadbeef",
    refresh_ts=1775103452000,
    start_type=48,
    raw_fields={"1": 1, "3": {"1": {"1": 100}}},
)


@dataclass
class _FakeCoordinator:
    """Minimal coordinator object for coordinator-backed entity tests."""

    device: DeviceContext
    api: Any
    data: AnonaDeviceSnapshot
    last_update_success: bool = True

    def __post_init__(self) -> None:
        self.async_request_refresh = AsyncMock()


def _coordinator(
    *,
    online_status: OnlineStatus | None = ONLINE_STATUS,
    lock_status: LockStatus | None = LOCK_STATUS,
    device: DeviceContext = LOCK_DEVICE,
) -> _FakeCoordinator:
    api = Mock()
    api.lock = AsyncMock()
    api.unlock = AsyncMock()
    return _FakeCoordinator(
        device=device,
        api=api,
        data=AnonaDeviceSnapshot(
            device=device,
            online_status=online_status,
            lock_status=lock_status,
        ),
    )


def test_lock_entity_maps_snapshot_and_dispatches_commands() -> None:
    """The lock entity should map snapshot values and forward lock commands."""
    coordinator = _coordinator()
    entity = AnonaHoloLock(cast("Any", coordinator))

    asyncio.run(entity.async_unlock())
    asyncio.run(entity.async_lock())
    attrs = entity.extra_state_attributes or {}

    assert entity.is_locked is True
    assert entity.available is True
    assert attrs["battery_level"] == 100
    assert attrs["battery_voltage"] == 180
    assert attrs["charge_status_code"] == 1
    assert attrs["door_state_code"] == 1
    assert attrs["long_endurance_mode_status_code"] == 0
    assert attrs["raw_data_hex_str"] == "deadbeef"
    assert attrs["device_id"] == "device-123"

    coordinator.api.unlock.assert_awaited_once_with(LOCK_DEVICE)
    coordinator.api.lock.assert_awaited_once_with(LOCK_DEVICE)
    assert coordinator.async_request_refresh.await_count == 2


def test_lock_entity_available_is_false_when_offline() -> None:
    """Offline coordinator snapshots should mark the lock unavailable."""
    coordinator = _coordinator(online_status=OFFLINE_STATUS)
    entity = AnonaHoloLock(cast("Any", coordinator))

    assert entity.available is False


def test_async_setup_entry_only_adds_lock_devices() -> None:
    """Entity setup should filter coordinators to supported lock hardware only."""
    lock_coordinator = _coordinator(device=LOCK_DEVICE)
    other_coordinator = _coordinator(device=OTHER_DEVICE)
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry-1": {
                    DATA_COORDINATORS: {
                        "device-123": lock_coordinator,
                        "device-999": other_coordinator,
                    }
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry-1")
    added_entities: list[AnonaHoloLock] = []

    def add_entities(new_entities: list[AnonaHoloLock]) -> None:
        added_entities.extend(new_entities)

    asyncio.run(
        async_setup_entry(
            cast("Any", hass),
            cast("Any", entry),
            cast("Any", add_entities),
        )
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == "anona_holo_device-123_lock"
