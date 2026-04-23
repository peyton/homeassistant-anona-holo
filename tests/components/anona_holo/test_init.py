"""Runtime lifecycle tests for the Anona Holo Home Assistant integration."""

# ruff: noqa: S101, S106

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anona_holo import (
    async_setup_entry as integration_async_setup_entry,
)
from custom_components.anona_holo.api import (
    AnonaApiError,
    AnonaAuthError,
    DeviceContext,
    DeviceInfoContext,
    DeviceSwitchSettings,
    FirmwareUpdateContext,
    HomeContext,
    LockStatus,
    LoginContext,
    OnlineStatus,
)
from custom_components.anona_holo.const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
    DEVICE_TYPE_LOCK,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

LOCK_DOMAIN = "lock"
LOCKED_STATE = "locked"


def _make_entry() -> MockConfigEntry:
    """Build a config entry fixture for runtime setup tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        version=2,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "super-secret",
            CONF_CLIENT_UUID: "12345678-1234-5678-1234-567812345678",
            CONF_USER_ID: "stale-user-id",
            CONF_HOME_ID: "home-123",
        },
    )


def _lock_device() -> DeviceContext:
    """Return a lock device context used by runtime tests."""
    return DeviceContext(
        device_id="device-123",
        device_type=DEVICE_TYPE_LOCK,
        device_module=76001,
        device_channel=76001001,
        nickname="Front Door Lock",
        serial_number="SN-LOCK-123",
        model="SL2001",
        raw={"deviceId": "device-123"},
    )


def _other_device() -> DeviceContext:
    """Return a non-lock device context to verify lock filtering."""
    return DeviceContext(
        device_id="device-999",
        device_type=42,
        device_module=42001,
        device_channel=42001001,
        nickname="Ignored Sensor",
        serial_number="SN-SENSOR-999",
        model="SENSOR42",
        raw={"deviceId": "device-999"},
    )


def _build_fake_api(
    *,
    login_error: Exception | None = None,
    online_error: Exception | None = None,
) -> Mock:
    """Create an API double with async methods used by integration runtime tests."""
    api = Mock()
    if login_error is None:
        api.login = AsyncMock(
            return_value=LoginContext(
                token="session-token",
                user_id="fresh-user-id",
                user_name="Peyton",
                channel=73001001,
            )
        )
    else:
        api.login = AsyncMock(side_effect=login_error)
    api.get_homes = AsyncMock(
        return_value=[
            HomeContext(
                home_id="home-123",
                name="Bay",
                is_default=True,
                raw={"homeId": "home-123"},
            )
        ]
    )
    api.home_id = "home-123"
    api.get_all_devices = AsyncMock(return_value=[_lock_device(), _other_device()])
    default_switch_settings = DeviceSwitchSettings(
        device_id="device-123",
        main_switch=True,
        ugent_notify_switch=True,
        important_notify_switch=True,
        normal_notify_switch=True,
        raw={},
    )
    api.get_device_switch_list_by_home = AsyncMock(
        return_value={"device-123": default_switch_settings}
    )
    if online_error is None:
        api.get_device_online_status = AsyncMock(
            return_value=OnlineStatus(
                online=True,
                create_ts=1775103001462,
                last_alive_ts=None,
                raw={"online": True},
            )
        )
    else:
        api.get_device_online_status = AsyncMock(side_effect=online_error)
    api.get_device_status = AsyncMock(
        return_value=LockStatus(
            locked=True,
            lock_status_code=1,
            battery_capacity=100,
            battery_voltage=None,
            charge_status_code=None,
            door_state_code=1,
            door_status_code=1,
            has_locking_fail=False,
            has_door_been_open_long_time=False,
            calibration_status_code=None,
            long_endurance_mode_status_code=0,
            keypad_connection_status_code=1,
            keypad_battery_capacity=1,
            keypad_status_code=2,
            data_hex_str="deadbeef",
            refresh_ts=1775103452000,
            start_type=48,
            raw_fields={"1": 1, "3": {"1": {"1": 100}}},
            auto_lock_enabled=True,
            auto_lock_delay_seconds=180,
            auto_lock_delay_label="3 minutes",
            sound_volume_code=2,
            sound_volume="High",
            low_power_mode_enabled=False,
        )
    )
    api.lock = AsyncMock()
    api.unlock = AsyncMock()
    api.get_device_info_context = AsyncMock(
        return_value=DeviceInfoContext(
            device_id="device-123",
            device_type=DEVICE_TYPE_LOCK,
            device_module=76001,
            device_channel=76001001,
            firmware_version="1.0.0",
            firmware_sub_version="0",
            ip_address=None,
            wifi_ap_ssid=None,
            wifi_mac=None,
            bt_mac=None,
            timezone_id=None,
            silent_ota_enabled=True,
            silent_ota_time="03:00-05:00",
            silent_ota_time_raw="03:00-05:00",
            last_online_ts=1775103452000,
            raw={},
        )
    )
    api.get_device_switch_settings = AsyncMock(return_value=default_switch_settings)
    api.get_firmware_update_context = AsyncMock(
        return_value=FirmwareUpdateContext(
            device_id="device-123",
            installed_version="1.0.0",
            latest_version="1.0.0",
            latest_sub_version=None,
            new_version=False,
            version_order=None,
            release_notes=None,
            release_url=None,
            release_ts=None,
            file_md5=None,
            file_size=None,
            is_forced=None,
            raw={},
        )
    )
    return api


@pytest.mark.asyncio
async def test_runtime_setup_creates_entity_and_routes_lock_services(
    hass: HomeAssistant,
) -> None:
    """A real config-entry setup should create one lock entity and route services."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    fake_api = _build_fake_api()
    lock_device = _lock_device()

    with patch("custom_components.anona_holo.AnonaApi", return_value=fake_api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_USER_ID] == "fresh-user-id"
    assert entry.runtime_data.api is fake_api
    assert entry.runtime_data.devices == {"device-123": lock_device}
    assert set(entry.runtime_data.coordinators) == {"device-123"}
    fake_api.login.assert_awaited_once_with("user@example.com", "super-secret")

    lock_states = hass.states.async_all(LOCK_DOMAIN)
    assert len(lock_states) == 1
    state = lock_states[0]
    entity_id = state.entity_id
    assert state.state == LOCKED_STATE
    assert state.attributes["device_id"] == "device-123"
    assert "battery_level" not in state.attributes
    assert hass.states.get("lock.ignored_sensor") is None

    await hass.services.async_call(
        LOCK_DOMAIN,
        "unlock",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.services.async_call(
        LOCK_DOMAIN,
        "lock",
        {"entity_id": entity_id},
        blocking=True,
    )

    fake_api.unlock.assert_awaited_once_with(lock_device)
    fake_api.lock.assert_awaited_once_with(lock_device)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(entry, "runtime_data")


@pytest.mark.asyncio
async def test_runtime_reload_keeps_one_device_and_stable_unique_ids(
    hass: HomeAssistant,
) -> None:
    """Reloading the entry should not duplicate the lock device or its entities."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    fake_api = _build_fake_api()

    with patch("custom_components.anona_holo.AnonaApi", return_value=fake_api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)

        def _entry_unique_ids() -> set[str]:
            return {
                entity.unique_id
                for entity in entity_registry.entities.values()
                if entity.config_entry_id == entry.entry_id
            }

        first_unique_ids = _entry_unique_ids()
        first_device_matches = [
            device
            for device in device_registry.devices.values()
            if (DOMAIN, "device-123") in device.identifiers
        ]

        assert first_device_matches
        assert len(first_device_matches) == 1

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not hasattr(entry, "runtime_data")

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        second_unique_ids = _entry_unique_ids()
        second_device_matches = [
            device
            for device in device_registry.devices.values()
            if (DOMAIN, "device-123") in device.identifiers
        ]

    assert second_unique_ids == first_unique_ids
    assert len(second_device_matches) == 1


@pytest.mark.asyncio
async def test_async_setup_entry_maps_auth_error_to_config_entry_auth_failed(
    hass: HomeAssistant,
) -> None:
    """Authentication failures should map to ConfigEntryAuthFailed."""
    entry = _make_entry()
    fake_api = _build_fake_api(login_error=AnonaAuthError("invalid credentials"))

    with (
        patch("custom_components.anona_holo.AnonaApi", return_value=fake_api),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await integration_async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_maps_api_error_to_config_entry_not_ready(
    hass: HomeAssistant,
) -> None:
    """Transient upstream API failures should map to ConfigEntryNotReady."""
    entry = _make_entry()
    fake_api = _build_fake_api(login_error=AnonaApiError("upstream unavailable"))

    with (
        patch("custom_components.anona_holo.AnonaApi", return_value=fake_api),
        pytest.raises(ConfigEntryNotReady),
    ):
        await integration_async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_maps_timeout_to_config_entry_not_ready(
    hass: HomeAssistant,
) -> None:
    """Timeouts during setup should map to ConfigEntryNotReady."""
    entry = _make_entry()
    fake_api = _build_fake_api(login_error=TimeoutError("request timed out"))

    with (
        patch("custom_components.anona_holo.AnonaApi", return_value=fake_api),
        pytest.raises(ConfigEntryNotReady),
    ):
        await integration_async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_setup_entry_maps_coordinator_auth_error_to_config_entry_auth_failed(
    hass: HomeAssistant,
) -> None:
    """Auth errors during the first coordinator refresh should trigger reauth."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    fake_api = _build_fake_api(online_error=AnonaAuthError("session expired"))

    with patch("custom_components.anona_holo.AnonaApi", return_value=fake_api):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    def _is_reauth_flow(flow: object) -> bool:
        if not isinstance(flow, dict):
            return False
        context = flow.get("context")
        return isinstance(context, dict) and (
            context.get("source") == SOURCE_REAUTH
            and context.get("entry_id") == entry.entry_id
        )

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        _is_reauth_flow(flow)
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )
