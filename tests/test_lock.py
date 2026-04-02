"""Tests for the Anona Holo lock entity."""

# ruff: noqa: S101, PLR2004

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

from custom_components.anona_holo.api import (
    AnonaApiError,
    DeviceContext,
    LockStatus,
    OnlineStatus,
)
from custom_components.anona_holo.const import DEVICE_TYPE_LOCK, DOMAIN
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


def test_lock_entity_maps_status_objects_and_dispatches_commands() -> None:
    """The entity should map typed status models and forward lock commands."""
    api = Mock()
    api.get_device_online_status = AsyncMock(return_value=ONLINE_STATUS)
    api.get_device_status = AsyncMock(return_value=LOCK_STATUS)
    api.lock = AsyncMock()
    api.unlock = AsyncMock()

    entity = AnonaHoloLock(api, LOCK_DEVICE)

    asyncio.run(entity.async_update())
    asyncio.run(entity.async_unlock())
    asyncio.run(entity.async_lock())
    attrs = entity.extra_state_attributes or {}

    assert entity.is_locked is True
    assert entity.available is True
    assert attrs["battery_level"] == 100
    assert attrs["lock_battery_capacity"] == 100
    assert attrs["battery_voltage"] == 180
    assert attrs["charge_status_code"] == 1
    assert attrs["door_state_code"] == 1
    assert attrs["long_endurance_mode_status_code"] == 0
    assert attrs["raw_data_hex_str"] == "deadbeef"
    assert attrs["device_id"] == "device-123"
    api.get_device_online_status.assert_awaited_once_with(LOCK_DEVICE)
    api.get_device_status.assert_awaited_once_with(LOCK_DEVICE)
    api.unlock.assert_awaited_once_with(LOCK_DEVICE)
    api.lock.assert_awaited_once_with(LOCK_DEVICE)


def test_lock_entity_marks_itself_unavailable_after_online_error() -> None:
    """A polling error should mark the entity unavailable without crashing."""
    api = Mock()
    api.get_device_online_status = AsyncMock(side_effect=AnonaApiError("boom"))

    entity = AnonaHoloLock(api, LOCK_DEVICE)

    asyncio.run(entity.async_update())

    assert entity.available is False
    assert entity.is_locked is None


def test_async_setup_entry_only_adds_lock_devices() -> None:
    """Entity setup should filter the device list to lock hardware only."""
    api = Mock()
    api.get_devices = AsyncMock(return_value=[LOCK_DEVICE, OTHER_DEVICE])
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": api}})
    entry = SimpleNamespace(entry_id="entry-1")
    added_entities: list[AnonaHoloLock] = []
    update_before_add_flags: list[bool] = []

    def add_entities(
        new_entities: list[AnonaHoloLock],
        update_before_add: object | None = None,
    ) -> None:
        added_entities.extend(new_entities)
        update_before_add_flags.append(bool(update_before_add))

    asyncio.run(
        async_setup_entry(
            cast("Any", hass),
            cast("Any", entry),
            cast("Any", add_entities),
        )
    )

    assert len(added_entities) == 1
    assert added_entities[0].unique_id == f"{DOMAIN}_device-123"
    assert added_entities[0].name == "Front Door Lock"
    assert update_before_add_flags == [True]
