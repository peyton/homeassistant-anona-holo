"""Runtime lifecycle tests for the Anona Holo Home Assistant integration."""

# ruff: noqa: S101, S106, PLR2004

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anona_holo import (
    async_setup_entry as integration_async_setup_entry,
)
from custom_components.anona_holo.api import (
    AnonaApiError,
    AnonaAuthError,
    DeviceContext,
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
    api.get_device_online_status = AsyncMock(
        return_value=OnlineStatus(
            online=True,
            create_ts=1775103001462,
            last_alive_ts=None,
            raw={"online": True},
        )
    )
    api.get_device_status = AsyncMock(
        return_value=LockStatus(
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
    )
    api.lock = AsyncMock()
    api.unlock = AsyncMock()
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
    assert hass.data[DOMAIN][entry.entry_id] is fake_api
    fake_api.login.assert_awaited_once_with("user@example.com", "super-secret")

    lock_states = hass.states.async_all(LOCK_DOMAIN)
    assert len(lock_states) == 1
    state = lock_states[0]
    entity_id = state.entity_id
    assert state.state == LOCKED_STATE
    assert state.attributes["device_id"] == "device-123"
    assert state.attributes["battery_level"] == 100
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
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


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
