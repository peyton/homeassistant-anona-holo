"""Tests for config-entry diagnostics redaction."""

# ruff: noqa: S101

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

from custom_components.anona_holo import AnonaHoloRuntimeData
from custom_components.anona_holo.api import (
    DeviceContext,
    DeviceInfoContext,
    DeviceSwitchSettings,
    FirmwareUpdateContext,
    LockStatus,
    OnlineStatus,
)
from custom_components.anona_holo.const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
)
from custom_components.anona_holo.coordinator import AnonaDeviceSnapshot
from custom_components.anona_holo.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


@dataclass
class _FakeCoordinator:
    """Minimal coordinator shape for diagnostics tests."""

    data: AnonaDeviceSnapshot
    last_update_success: bool = True


def test_diagnostics_redacts_sensitive_fields() -> None:
    """Diagnostics export should redact IDs, credentials, and network identifiers."""
    device = DeviceContext(
        device_id="d3c03cf3fdf641dc90520940d26df688",
        device_type=76,
        device_module=76001,
        device_channel=76001001,
        nickname="Front Door Lock",
        serial_number="SN-LOCK-123",
        model="SL2001",
        raw={"deviceId": "d3c03cf3fdf641dc90520940d26df688"},
    )
    snapshot = AnonaDeviceSnapshot(
        device=device,
        online_status=OnlineStatus(
            online=True,
            create_ts=1775103001462,
            last_alive_ts=1775103452000,
            raw={"ip": "192.168.2.209"},
        ),
        lock_status=LockStatus(
            locked=True,
            lock_status_code=1,
            battery_capacity=95,
            battery_voltage=180,
            charge_status_code=1,
            door_state_code=1,
            door_status_code=1,
            has_locking_fail=False,
            has_door_been_open_long_time=False,
            calibration_status_code=2,
            long_endurance_mode_status_code=0,
            keypad_connection_status_code=1,
            keypad_battery_capacity=80,
            keypad_status_code=2,
            data_hex_str="deadbeef",
            refresh_ts=1775103452000,
            start_type=48,
            raw_fields={"1": 1},
        ),
        device_info_context=DeviceInfoContext(
            device_id=device.device_id,
            device_type=76,
            device_module=76001,
            device_channel=76001001,
            firmware_version="1.5.100",
            firmware_sub_version="a",
            ip_address="192.168.2.209",
            wifi_ap_ssid="MyWifi",
            wifi_mac="AA:BB:CC:DD:EE:FF",
            bt_mac="11:22:33:44:55:66",
            timezone_id="America/Los_Angeles",
            silent_ota_enabled=True,
            silent_ota_time="02:00-04:00",
            silent_ota_time_raw='{"beginHour":2,"beginMinute":0,"endHour":4,"endMinute":0}',
            last_online_ts=1775103452000,
            raw={
                "deviceNickName": "Front Door Lock",
                "timezoneId": "America/Los_Angeles",
                "wifiApSsid": "MyWifi",
                "userName": "me@peytn.com",
                "userCerts": "-----BEGIN CERTIFICATE-----",
            },
        ),
        switch_settings=DeviceSwitchSettings(
            device_id=device.device_id,
            main_switch=True,
            ugent_notify_switch=True,
            important_notify_switch=False,
            normal_notify_switch=True,
            raw={},
        ),
        firmware_update_context=FirmwareUpdateContext(
            device_id=device.device_id,
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
        ),
    )

    api = SimpleNamespace(
        home_id="home-123",
        user_id="533291",
        client_uuid="D15AF65C-BCF6-49B1-8A67-3A15793A11CE",
    )
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Anona Holo (me@peytn.com)",
        data={
            CONF_EMAIL: "me@peytn.com",
            CONF_PASSWORD: "secret",
            CONF_HOME_ID: "home-123",
            CONF_CLIENT_UUID: "D15AF65C-BCF6-49B1-8A67-3A15793A11CE",
        },
        options={},
        runtime_data=AnonaHoloRuntimeData(
            api=cast("Any", api),
            devices={device.device_id: device},
            coordinators=cast(
                "Any",
                {device.device_id: _FakeCoordinator(data=snapshot)},
            ),
        ),
    )
    hass = SimpleNamespace()

    diagnostics: dict[str, Any] = asyncio.run(
        async_get_config_entry_diagnostics(cast("Any", hass), cast("Any", entry))
    )

    assert diagnostics["entry"]["data"][CONF_EMAIL] == "**REDACTED**"
    assert diagnostics["entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["entry"]["title"] == "**REDACTED**"
    assert diagnostics["api"]["home_id"] == "**REDACTED**"
    assert diagnostics["api"]["user_id"] == "**REDACTED**"
    assert diagnostics["api"]["client_uuid"] == "**REDACTED**"

    exported_device = diagnostics["devices"][0]
    assert exported_device["device"]["device_id"] == "**REDACTED**"
    assert exported_device["device"]["nickname"] == "**REDACTED**"
    assert exported_device["device"]["serial_number"] == "**REDACTED**"
    assert (
        exported_device["snapshot"]["device_info_context"]["ip_address"]
        == "**REDACTED**"
    )
    assert (
        exported_device["snapshot"]["device_info_context"]["wifi_mac"] == "**REDACTED**"
    )
    assert (
        exported_device["snapshot"]["device_info_context"]["raw"]["wifiApSsid"]
        == "**REDACTED**"
    )
    assert (
        exported_device["snapshot"]["device_info_context"]["raw"]["timezoneId"]
        == "**REDACTED**"
    )
    serialized = json.dumps(diagnostics)
    assert "me@peytn.com" not in serialized
    assert "D15AF65C-BCF6-49B1-8A67-3A15793A11CE" not in serialized
    assert "192.168.2.209" not in serialized
    assert "AA:BB:CC:DD:EE:FF" not in serialized


def test_device_diagnostics_are_scoped_to_the_requested_device() -> None:
    """Device diagnostics should return the selected device payload only."""
    device = DeviceContext(
        device_id="device-123",
        device_type=76,
        device_module=76001,
        device_channel=76001001,
        nickname="Front Door Lock",
        serial_number="SN-LOCK-123",
        model="SL2001",
        raw={"deviceId": "device-123"},
    )
    other_device = DeviceContext(
        device_id="device-999",
        device_type=76,
        device_module=76001,
        device_channel=76001001,
        nickname="Back Door Lock",
        serial_number="SN-LOCK-999",
        model="SL2001",
        raw={"deviceId": "device-999"},
    )
    snapshot = AnonaDeviceSnapshot(device=device)
    other_snapshot = AnonaDeviceSnapshot(device=other_device)
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Anona Holo",
        data={},
        options={},
        runtime_data=AnonaHoloRuntimeData(
            api=cast("Any", None),
            devices={
                device.device_id: device,
                other_device.device_id: other_device,
            },
            coordinators=cast(
                "Any",
                {
                    device.device_id: _FakeCoordinator(data=snapshot),
                    other_device.device_id: _FakeCoordinator(data=other_snapshot),
                },
            ),
        ),
    )
    hass = SimpleNamespace()
    device_entry = SimpleNamespace(identifiers={("anona_holo", device.device_id)})

    diagnostics: dict[str, Any] = asyncio.run(
        async_get_device_diagnostics(
            cast("Any", hass),
            cast("Any", entry),
            cast("Any", device_entry),
        )
    )

    assert len(diagnostics["devices"]) == 1
    assert diagnostics["devices"][0]["device"]["model"] == "SL2001"
    assert diagnostics["devices"][0]["device"]["device_id"] == "**REDACTED**"
