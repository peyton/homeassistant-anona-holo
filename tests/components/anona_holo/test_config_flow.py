"""Tests for the Anona Holo config flow."""

# ruff: noqa: S101, S106

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anona_holo.api import (
    AnonaApiError,
    AnonaAuthError,
    HomeContext,
    LoginContext,
)
from custom_components.anona_holo.config_flow import AnonaHoloConfigFlow
from custom_components.anona_holo.const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
    DOMAIN,
)

CONFIG_FLOW_VERSION = 2
CONFIG_FLOW_MINOR_VERSION = 1


class _SuccessfulApi:
    """Test double for a successful Anona login and home lookup."""

    def __init__(self) -> None:
        """Initialize the fake API."""
        self.login = AsyncMock(
            return_value=LoginContext(
                token="session-token",
                user_id="user-123",
                user_name="Peyton",
                channel=73001001,
            )
        )
        self.get_homes = AsyncMock(
            return_value=[
                HomeContext(
                    home_id="home-123",
                    name="Bay",
                    is_default=True,
                    raw={"homeId": "home-123"},
                )
            ]
        )
        self.home_id = "home-123"


class _InvalidAuthApi:
    """Test double for an authentication failure."""

    def __init__(self) -> None:
        """Initialize the fake API."""
        self.login = AsyncMock(side_effect=AnonaAuthError("bad credentials"))
        self.get_homes = AsyncMock()
        self.home_id = None


class _GenericApiErrorApi:
    """Test double for a non-auth API failure."""

    def __init__(self) -> None:
        """Initialize the fake API."""
        self.login = AsyncMock(side_effect=AnonaApiError("unexpected upstream error"))
        self.get_homes = AsyncMock()
        self.home_id = None


def _return_session(*_: object) -> object:
    """Return a sentinel session object."""
    return object()


def _patch_api(monkeypatch: pytest.MonkeyPatch, api: object) -> None:
    """Patch config-flow dependencies to use the supplied API double."""
    monkeypatch.setattr(
        "custom_components.anona_holo.config_flow.AnonaApi",
        lambda *_args, **_kwargs: api,
    )
    monkeypatch.setattr(
        "custom_components.anona_holo.config_flow.async_get_clientsession",
        _return_session,
    )


def _make_entry() -> MockConfigEntry:
    """Create a config entry for reauth and reconfigure tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        title="Anona Holo (user@example.com)",
        version=2,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old-secret",
            CONF_CLIENT_UUID: "12345678-1234-5678-1234-567812345678",
            CONF_USER_ID: "old-user-id",
            CONF_HOME_ID: "old-home-id",
        },
    )


@pytest.mark.asyncio
async def test_user_flow_creates_entry_with_client_uuid(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user flow should create a config entry with discovered identifiers."""
    _patch_api(monkeypatch, _SuccessfulApi())
    monkeypatch.setattr(
        "custom_components.anona_holo.config_flow.uuid4",
        lambda: UUID("12345678-1234-5678-1234-567812345678"),
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "User@Example.com",
            CONF_PASSWORD: "secret-password",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Anona Holo (User@Example.com)"
    assert result["data"] == {
        CONF_EMAIL: "User@Example.com",
        CONF_PASSWORD: "secret-password",
        CONF_CLIENT_UUID: "12345678-1234-5678-1234-567812345678".upper(),
        CONF_USER_ID: "user-123",
        CONF_HOME_ID: "home-123",
    }

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "user@example.com"
    assert entry.title == "Anona Holo (User@Example.com)"


@pytest.mark.asyncio
async def test_user_flow_reports_invalid_auth(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid credentials should map to the config-flow auth error."""
    _patch_api(monkeypatch, _InvalidAuthApi())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "User@Example.com",
            CONF_PASSWORD: "secret-password",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_user_flow_reports_generic_api_error(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-auth API failure should surface the generic config-flow error."""
    _patch_api(monkeypatch, _GenericApiErrorApi())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "User@Example.com",
            CONF_PASSWORD: "secret-password",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_user_flow_aborts_when_email_is_already_configured(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flow should guard against duplicate normalized emails."""
    _patch_api(monkeypatch, _SuccessfulApi())
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "User@Example.com",
            CONF_PASSWORD: "secret-password",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_reauth_flow_updates_existing_entry(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reauth should update the saved credentials and schedule a reload."""
    _patch_api(monkeypatch, _SuccessfulApi())
    entry = _make_entry()
    entry.add_to_hass(hass)
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "title_placeholders": {"name": entry.title},
        },
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "new-secret",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
    assert entry.data[CONF_USER_ID] == "user-123"
    assert entry.data[CONF_HOME_ID] == "home-123"
    schedule_reload.assert_called_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_reauth_flow_aborts_for_a_different_account(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reauth should refuse credentials for a different normalized account."""
    _patch_api(monkeypatch, _SuccessfulApi())
    entry = _make_entry()
    entry.add_to_hass(hass)
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "title_placeholders": {"name": entry.title},
        },
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "other@example.com",
            CONF_PASSWORD: "new-secret",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_PASSWORD] == "old-secret"
    schedule_reload.assert_not_called()


@pytest.mark.asyncio
async def test_reconfigure_flow_updates_existing_entry(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure should update the saved credentials and schedule a reload."""
    _patch_api(monkeypatch, _SuccessfulApi())
    entry = _make_entry()
    entry.add_to_hass(hass)
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
            "title_placeholders": {"name": entry.title},
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "new-secret",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
    assert entry.data[CONF_USER_ID] == "user-123"
    assert entry.data[CONF_HOME_ID] == "home-123"
    schedule_reload.assert_called_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_reconfigure_flow_aborts_for_a_different_account(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure should refuse credentials for a different normalized account."""
    _patch_api(monkeypatch, _SuccessfulApi())
    entry = _make_entry()
    entry.add_to_hass(hass)
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
            "title_placeholders": {"name": entry.title},
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "other@example.com",
            CONF_PASSWORD: "new-secret",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_PASSWORD] == "old-secret"
    schedule_reload.assert_not_called()


@pytest.mark.asyncio
async def test_reconfigure_form_includes_current_email_placeholder(
    hass: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure should describe which account is being updated."""
    _patch_api(monkeypatch, _InvalidAuthApi())
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
            "title_placeholders": {"name": entry.title},
        },
    )

    assert result["description_placeholders"] == {"email": "user@example.com"}


def test_config_flow_minor_version_is_bumped() -> None:
    """The config flow should advertise the new minor version."""
    assert AnonaHoloConfigFlow.MINOR_VERSION == CONFIG_FLOW_MINOR_VERSION
    assert AnonaHoloConfigFlow.VERSION == CONFIG_FLOW_VERSION
