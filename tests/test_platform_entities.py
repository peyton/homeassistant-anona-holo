"""Tests for sensor/binary_sensor/switch/update entity mappings."""

# ruff: noqa: S101, PLR2004

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

from custom_components.anona_holo.api import (
    DeviceContext,
    DeviceInfoContext,
    DeviceSwitchSettings,
    FirmwareUpdateContext,
    LockStatus,
    OnlineStatus,
)
from custom_components.anona_holo.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    AnonaHoloBinarySensor,
)
from custom_components.anona_holo.coordinator import AnonaDeviceSnapshot
from custom_components.anona_holo.sensor import SENSOR_DESCRIPTIONS, AnonaHoloSensor
from custom_components.anona_holo.switch import (
    NOTIFICATION_SWITCHES,
    AnonaNotificationSwitch,
    AnonaSilentOTASwitch,
)
from custom_components.anona_holo.update import AnonaHoloFirmwareUpdate

LOCK_DEVICE = DeviceContext(
    device_id="device-123",
    device_type=76,
    device_module=76001,
    device_channel=76001001,
    nickname="Front Door Lock",
    serial_number="SN-LOCK-123",
    model="SL2001",
    raw={"deviceId": "device-123"},
)
ONLINE_STATUS = OnlineStatus(
    online=True,
    create_ts=1775103001462,
    last_alive_ts=1775103452000,
    raw={"online": True},
)
LOCK_STATUS = LockStatus(
    locked=True,
    lock_status_code=1,
    battery_capacity=95,
    battery_voltage=None,
    charge_status_code=None,
    door_state_code=1,
    door_status_code=1,
    has_locking_fail=False,
    has_door_been_open_long_time=True,
    calibration_status_code=None,
    long_endurance_mode_status_code=1,
    keypad_connection_status_code=1,
    keypad_battery_capacity=80,
    keypad_status_code=2,
    data_hex_str="deadbeef",
    refresh_ts=1775103452000,
    start_type=48,
    raw_fields={"1": 1},
    auto_lock_enabled=True,
    auto_lock_delay_seconds=180,
    auto_lock_delay_label="3 minutes",
    sound_volume_code=2,
    sound_volume="High",
    low_power_mode_enabled=True,
)
DEVICE_INFO = DeviceInfoContext(
    device_id="device-123",
    device_type=76,
    device_module=76001,
    device_channel=76001001,
    firmware_version="1.5.100",
    firmware_sub_version="a",
    ip_address="192.168.1.2",
    wifi_ap_ssid="MyWifi",
    wifi_mac="AA:BB:CC:DD:EE:FF",
    bt_mac="11:22:33:44:55:66",
    timezone_id="America/Los_Angeles",
    silent_ota_enabled=True,
    silent_ota_time="02:00-04:00",
    silent_ota_time_raw='{"beginHour":2,"beginMinute":0,"endHour":4,"endMinute":0}',
    last_online_ts=1775103452000,
    raw={},
)
SWITCH_SETTINGS = DeviceSwitchSettings(
    device_id="device-123",
    main_switch=True,
    ugent_notify_switch=True,
    important_notify_switch=False,
    normal_notify_switch=True,
    raw={},
)
FIRMWARE_CONTEXT = FirmwareUpdateContext(
    device_id="device-123",
    installed_version="1.5.100",
    latest_version="1.5.189",
    latest_sub_version="a",
    new_version=True,
    version_order=None,
    release_notes="notes",
    release_url="https://example.com/fw.bin",
    release_ts=1729132842000,
    file_md5="abc123",
    file_size=1024,
    is_forced=False,
    raw={},
)


@dataclass
class _FakeCoordinator:
    """Minimal coordinator object for entity mapping tests."""

    device: DeviceContext
    api: Any
    data: AnonaDeviceSnapshot
    last_update_success: bool = True

    def __post_init__(self) -> None:
        self.async_request_refresh = AsyncMock()
        self.async_request_details_refresh = AsyncMock()


def _coordinator() -> _FakeCoordinator:
    api = Mock()
    api.update_device_switch_settings = AsyncMock(return_value=SWITCH_SETTINGS)
    api.set_silent_ota = AsyncMock()
    return _FakeCoordinator(
        device=LOCK_DEVICE,
        api=api,
        data=AnonaDeviceSnapshot(
            device=LOCK_DEVICE,
            online_status=ONLINE_STATUS,
            lock_status=LOCK_STATUS,
            device_info_context=DEVICE_INFO,
            switch_settings=SWITCH_SETTINGS,
            firmware_update_context=FIRMWARE_CONTEXT,
        ),
    )


def test_sensor_and_binary_sensor_state_mapping() -> None:
    """New sensor and binary sensor entities should map coordinator snapshot values."""
    coordinator = _coordinator()

    auto_lock_delay_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "auto_lock_delay"
    )
    sound_volume_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "sound_volume"
    )
    keypad_battery_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "keypad_battery"
    )
    auto_lock_description = next(
        item for item in BINARY_SENSOR_DESCRIPTIONS if item.key == "auto_lock_enabled"
    )
    jam_description = next(
        item for item in BINARY_SENSOR_DESCRIPTIONS if item.key == "lock_jam"
    )
    low_power_description = next(
        item for item in BINARY_SENSOR_DESCRIPTIONS if item.key == "low_power_mode"
    )

    battery_sensor = AnonaHoloSensor(
        cast("Any", coordinator),
        SENSOR_DESCRIPTIONS[0],
    )
    auto_lock_delay_sensor = AnonaHoloSensor(
        cast("Any", coordinator),
        auto_lock_delay_description,
    )
    sound_volume_sensor = AnonaHoloSensor(
        cast("Any", coordinator),
        sound_volume_description,
    )
    keypad_sensor = AnonaHoloSensor(
        cast("Any", coordinator),
        keypad_battery_description,
    )
    auto_lock_sensor = AnonaHoloBinarySensor(
        cast("Any", coordinator),
        auto_lock_description,
    )
    jam_sensor = AnonaHoloBinarySensor(
        cast("Any", coordinator),
        jam_description,
    )
    low_power_sensor = AnonaHoloBinarySensor(
        cast("Any", coordinator),
        low_power_description,
    )

    assert battery_sensor.native_value == 95
    assert auto_lock_delay_sensor.native_value == 180
    assert sound_volume_sensor.native_value == "High"
    assert keypad_sensor.native_value == 80
    assert auto_lock_sensor.is_on is True
    assert jam_sensor.is_on is False
    assert low_power_sensor.is_on is True


def test_notification_switch_merges_payload_for_update_device_switch() -> None:
    """Switch writes should keep non-target settings unchanged in merged payload."""

    async def _run() -> None:
        coordinator = _coordinator()
        description = next(
            item for item in NOTIFICATION_SWITCHES if item.key == "event_notifications"
        )
        entity = AnonaNotificationSwitch(cast("Any", coordinator), description)

        await entity.async_turn_on()

        coordinator.api.update_device_switch_settings.assert_awaited_once_with(
            LOCK_DEVICE,
            main_switch=True,
            ugent_notify_switch=True,
            important_notify_switch=True,
            normal_notify_switch=True,
        )
        coordinator.async_request_details_refresh.assert_awaited_once()

    asyncio.run(_run())


def test_silent_ota_switch_writes_current_window() -> None:
    """Silent OTA switch should persist current window with enabled flag."""

    async def _run() -> None:
        coordinator = _coordinator()
        entity = AnonaSilentOTASwitch(cast("Any", coordinator))

        await entity.async_turn_off()

        coordinator.api.set_silent_ota.assert_awaited_once_with(
            LOCK_DEVICE,
            enabled=False,
            silent_ota_time="02:00-04:00",
        )
        coordinator.async_request_details_refresh.assert_awaited_once()

    asyncio.run(_run())


def test_update_entity_exposes_firmware_metadata() -> None:
    """Firmware update entity should report versions and availability."""
    coordinator = _coordinator()
    entity = AnonaHoloFirmwareUpdate(cast("Any", coordinator))

    assert entity.installed_version == "1.5.100"
    assert entity.latest_version == "1.5.189"
    assert entity.release_summary == "notes"
    assert entity.release_url == "https://example.com/fw.bin"
    assert entity.available is True
