"""Tests for the Anona Security config flow."""

# ruff: noqa: S101, S106, SLF001

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.anona_security.api import (
    AnonaApiError,
    AnonaAuthError,
    HomeContext,
    LoginContext,
)
from custom_components.anona_security.config_flow import AnonaSecurityConfigFlow
from custom_components.anona_security.const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
)


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


def _make_flow() -> AnonaSecurityConfigFlow:
    """Create a fresh flow instance for a test."""
    flow = AnonaSecurityConfigFlow()
    cast("Any", flow).hass = SimpleNamespace()
    return flow


def _return_session(*_: object) -> object:
    """Return a sentinel session object."""
    return object()


def test_user_step_creates_entry_with_client_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flow should persist credentials and the discovered identifiers."""
    flow = _make_flow()
    flow_any = cast("Any", flow)
    api = _SuccessfulApi()
    create_entry = Mock(
        side_effect=lambda *, title, data: {
            "type": "create_entry",
            "title": title,
            "data": data,
        }
    )
    unique_ids: list[str] = []

    async def set_unique_id(unique_id: str) -> None:
        unique_ids.append(unique_id)

    flow_any.async_set_unique_id = set_unique_id
    flow_any._abort_if_unique_id_configured = Mock()
    flow_any.async_create_entry = create_entry
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.AnonaApi",
        lambda *_args, **_kwargs: api,
    )
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.async_get_clientsession",
        _return_session,
    )
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.uuid4",
        lambda: UUID("12345678-1234-5678-1234-567812345678"),
    )

    result = cast(
        "dict[str, Any]",
        asyncio.run(
            flow.async_step_user(
                {
                    CONF_EMAIL: "User@Example.com",
                    CONF_PASSWORD: "secret-password",
                }
            )
        ),
    )

    assert unique_ids == ["user@example.com"]
    assert result["type"] == "create_entry"
    assert result["title"] == "Anona Security (User@Example.com)"
    assert result["data"] == {
        CONF_EMAIL: "User@Example.com",
        CONF_PASSWORD: "secret-password",
        CONF_CLIENT_UUID: "12345678-1234-5678-1234-567812345678".upper(),
        CONF_USER_ID: "user-123",
        CONF_HOME_ID: "home-123",
    }
    api.login.assert_awaited_once_with("User@Example.com", "secret-password")
    api.get_homes.assert_awaited_once()


def test_user_step_reports_invalid_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid credentials should map to the config-flow auth error."""
    flow = _make_flow()
    flow_any = cast("Any", flow)
    api = _InvalidAuthApi()
    show_form = Mock(
        side_effect=lambda *, step_id, data_schema, errors: {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors,
        }
    )

    async def set_unique_id(unique_id: str) -> None:
        assert unique_id == "user@example.com"

    flow_any.async_set_unique_id = set_unique_id
    flow_any._abort_if_unique_id_configured = Mock()
    flow_any.async_show_form = show_form
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.AnonaApi",
        lambda *_args, **_kwargs: api,
    )
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.async_get_clientsession",
        _return_session,
    )

    result = cast(
        "dict[str, Any]",
        asyncio.run(
            flow.async_step_user(
                {
                    CONF_EMAIL: "User@Example.com",
                    CONF_PASSWORD: "secret-password",
                }
            )
        ),
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


def test_user_step_reports_generic_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-auth API failure should surface the generic config-flow error."""
    flow = _make_flow()
    flow_any = cast("Any", flow)
    api = _GenericApiErrorApi()
    show_form = Mock(
        side_effect=lambda *, step_id, data_schema, errors: {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors,
        }
    )

    async def set_unique_id(unique_id: str) -> None:
        assert unique_id == "user@example.com"

    flow_any.async_set_unique_id = set_unique_id
    flow_any._abort_if_unique_id_configured = Mock()
    flow_any.async_show_form = show_form
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.AnonaApi",
        lambda *_args, **_kwargs: api,
    )
    monkeypatch.setattr(
        "custom_components.anona_security.config_flow.async_get_clientsession",
        _return_session,
    )

    result = cast(
        "dict[str, Any]",
        asyncio.run(
            flow.async_step_user(
                {
                    CONF_EMAIL: "User@Example.com",
                    CONF_PASSWORD: "secret-password",
                }
            )
        ),
    )

    assert result["errors"] == {"base": "unknown"}


def test_user_step_aborts_when_email_is_already_configured() -> None:
    """The flow should guard against duplicate normalized emails."""
    flow = _make_flow()
    flow_any = cast("Any", flow)
    unique_ids: list[str] = []

    async def set_unique_id(unique_id: str) -> None:
        unique_ids.append(unique_id)

    def abort_if_configured() -> None:
        reason = "already_configured"
        raise AbortFlow(reason)

    flow_any.async_set_unique_id = set_unique_id
    flow_any._abort_if_unique_id_configured = abort_if_configured

    with pytest.raises(AbortFlow) as context:
        asyncio.run(
            flow.async_step_user(
                {
                    CONF_EMAIL: "User@Example.com",
                    CONF_PASSWORD: "secret-password",
                }
            )
        )

    assert unique_ids == ["user@example.com"]
    assert context.value.reason == "already_configured"
