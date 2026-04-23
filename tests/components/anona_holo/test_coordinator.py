"""Tests for the Anona per-device coordinator."""

# ruff: noqa: S101, PLR2004, SLF001

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.anona_holo.api import (
    AnonaApiError,
    DeviceContext,
    DeviceInfoContext,
    DeviceSwitchSettings,
    FirmwareUpdateContext,
    LockStatus,
    OnlineStatus,
)
from custom_components.anona_holo.coordinator import AnonaDeviceCoordinator

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
    raw_fields={"1": 1},
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


def _coordinator(api: Any) -> AnonaDeviceCoordinator:
    hass = SimpleNamespace(loop=asyncio.get_running_loop())
    return AnonaDeviceCoordinator(cast("Any", hass), api=api, device=LOCK_DEVICE)


def test_coordinator_refreshes_fast_each_cycle_and_details_on_interval() -> None:
    """Fast endpoints should poll every cycle, detail endpoints less frequently."""

    async def _run() -> None:
        api = Mock()
        api.get_device_online_status = AsyncMock(return_value=ONLINE_STATUS)
        api.get_device_status = AsyncMock(return_value=LOCK_STATUS)
        api.get_device_info_context = AsyncMock(return_value=DEVICE_INFO)
        api.get_device_switch_settings = AsyncMock(return_value=SWITCH_SETTINGS)
        api.get_device_switch_list_by_home = AsyncMock(return_value={})
        api.get_firmware_update_context = AsyncMock(return_value=FIRMWARE_CONTEXT)

        coordinator = _coordinator(api)

        first = await coordinator._async_update_data()
        coordinator.async_set_updated_data(first)
        second = await coordinator._async_update_data()

        assert first.device_info_context == DEVICE_INFO
        assert second.device_info_context == DEVICE_INFO
        assert api.get_device_online_status.await_count == 2
        assert api.get_device_status.await_count == 2
        assert api.get_device_info_context.await_count == 1
        assert api.get_device_switch_settings.await_count == 1
        assert api.get_firmware_update_context.await_count == 1

    asyncio.run(_run())


def test_coordinator_keeps_stale_details_when_detail_refresh_fails() -> None:
    """Stale detail data should be preserved when slower calls fail."""

    async def _run() -> None:
        api = Mock()
        api.get_device_online_status = AsyncMock(return_value=ONLINE_STATUS)
        api.get_device_status = AsyncMock(return_value=LOCK_STATUS)
        api.get_device_info_context = AsyncMock(return_value=DEVICE_INFO)
        api.get_device_switch_settings = AsyncMock(return_value=SWITCH_SETTINGS)
        api.get_device_switch_list_by_home = AsyncMock(return_value={})
        api.get_firmware_update_context = AsyncMock(return_value=FIRMWARE_CONTEXT)

        coordinator = _coordinator(api)

        baseline = await coordinator._async_update_data()
        coordinator.async_set_updated_data(baseline)

        api.get_device_info_context = AsyncMock(side_effect=AnonaApiError("boom"))
        api.get_device_switch_settings = AsyncMock(side_effect=AnonaApiError("boom"))
        api.get_firmware_update_context = AsyncMock(side_effect=AnonaApiError("boom"))
        api.get_device_switch_list_by_home = AsyncMock(
            return_value={"device-123": SWITCH_SETTINGS}
        )

        coordinator._force_details_refresh = True
        updated = await coordinator._async_update_data()

        assert updated.device_info_context == DEVICE_INFO
        assert updated.switch_settings == SWITCH_SETTINGS
        assert updated.firmware_update_context == FIRMWARE_CONTEXT
        api.get_device_switch_list_by_home.assert_awaited_once()

    asyncio.run(_run())


def test_coordinator_raises_redacted_update_failed_when_fast_polls_fail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unavailable coordinator updates should not expose device identifiers."""

    async def _run() -> None:
        api = Mock()
        api.get_device_online_status = AsyncMock(
            side_effect=AnonaApiError("device-123 is offline")
        )
        api.get_device_status = AsyncMock(side_effect=TimeoutError("device-123"))

        coordinator = _coordinator(api)

        caplog.set_level(
            logging.DEBUG,
            logger="custom_components.anona_holo.coordinator",
        )
        with pytest.raises(UpdateFailed) as err:
            await coordinator._async_update_data()

        assert str(err.value) == "Unable to fetch Anona lock status"
        assert "device-123" not in caplog.text
        assert "**REDACTED** is offline" in caplog.text

    asyncio.run(_run())
