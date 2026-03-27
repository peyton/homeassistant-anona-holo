"""Tests for the integration config flow."""

# ruff: noqa: S101

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.integration_blueprint.api import AnonaAuthError
from custom_components.integration_blueprint.config_flow import (
    IntegrationBlueprintConfigFlow,
)
from custom_components.integration_blueprint.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import AbortFlow


class _SuccessfulApi:
    """Test double for a successful Anona login."""

    def __init__(self) -> None:
        """Initialize the fake API."""
        self.login = AsyncMock(return_value={})
        self.user_id = "user-123"
        self.home_id = "home-123"

    @property
    def access_token(self) -> str:
        """Return a deterministic token-like value for assertions."""
        return "session-opaque-id"


class _InvalidAuthApi:
    """Test double for an authentication failure."""

    def __init__(self) -> None:
        """Initialize the fake API."""
        self.login = AsyncMock(side_effect=AnonaAuthError("bad credentials"))


def _make_flow() -> IntegrationBlueprintConfigFlow:
    """Create a fresh flow instance for a test."""
    flow = IntegrationBlueprintConfigFlow()
    cast("Any", flow).hass = SimpleNamespace()
    return flow


def _return_api(*_: object, api: object) -> object:
    """Return a pre-built API test double."""
    return api


def _return_session(*_: object) -> object:
    """Return a sentinel session object."""
    return object()


def test_user_step_creates_entry_with_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flow should persist credentials and returned identifiers."""
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
    flow_any._abort_if_unique_id_configured = Mock()  # noqa: SLF001
    flow_any.async_create_entry = create_entry
    monkeypatch.setattr(
        "custom_components.integration_blueprint.config_flow.AnonaApi",
        lambda *args: _return_api(*args, api=api),
    )
    monkeypatch.setattr(
        "custom_components.integration_blueprint.config_flow.async_get_clientsession",
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

    assert unique_ids == ["user@example.com"]
    assert result["type"] == "create_entry"
    assert result["title"] == "Anona Holo (User@Example.com)"
    assert result["data"] == {
        CONF_EMAIL: "User@Example.com",
        CONF_PASSWORD: "secret-password",
        "access_token": "session-opaque-id",
        "user_id": "user-123",
        "home_id": "home-123",
    }
    api.login.assert_awaited_once_with("User@Example.com", "secret-password")


def test_user_step_reports_invalid_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flow should return the invalid-auth form error on login failure."""
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
    flow_any._abort_if_unique_id_configured = Mock()  # noqa: SLF001
    flow_any.async_show_form = show_form
    monkeypatch.setattr(
        "custom_components.integration_blueprint.config_flow.AnonaApi",
        lambda *args: _return_api(*args, api=api),
    )
    monkeypatch.setattr(
        "custom_components.integration_blueprint.config_flow.async_get_clientsession",
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
    flow_any._abort_if_unique_id_configured = abort_if_configured  # noqa: SLF001

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
