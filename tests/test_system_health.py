"""Tests for Anona Holo system health information."""

# ruff: noqa: S101

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock

from custom_components.anona_holo import system_health as anona_system_health
from custom_components.anona_holo.api import DeviceContext, OnlineStatus
from custom_components.anona_holo.const import (
    API_BASE_URL,
    DATA_COORDINATORS,
    DATA_DEVICES,
    DEVICE_TYPE_LOCK,
    DOMAIN,
)
from custom_components.anona_holo.coordinator import AnonaDeviceSnapshot

if TYPE_CHECKING:
    from collections.abc import Awaitable


def test_system_health_info_uses_aggregate_redaction_safe_values(
    monkeypatch: Any,
) -> None:
    """System health should expose aggregate health without raw identifiers."""

    async def _fake_reachability(_: Any, url: str) -> str:
        assert url == API_BASE_URL
        return "ok"

    device = DeviceContext(
        device_id="device-123",
        device_type=DEVICE_TYPE_LOCK,
        device_module=76001,
        device_channel=76001001,
        nickname="Front Door Lock",
        serial_number="SN-LOCK-123",
        model="SL2001",
        raw={"deviceId": "device-123"},
    )
    coordinator = SimpleNamespace(
        data=AnonaDeviceSnapshot(
            device=device,
            online_status=OnlineStatus(
                online=True,
                create_ts=1775103001462,
                last_alive_ts=1775103452000,
                raw={"online": True},
            ),
        ),
        last_update_success=True,
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=Mock(return_value=[SimpleNamespace(entry_id="entry-1")])
        ),
        data={
            DOMAIN: {
                "entry-1": {
                    DATA_DEVICES: {device.device_id: device},
                    DATA_COORDINATORS: {device.device_id: coordinator},
                }
            }
        },
    )
    monkeypatch.setattr(
        anona_system_health.system_health,
        "async_check_can_reach_url",
        _fake_reachability,
    )

    info = asyncio.run(anona_system_health.system_health_info(cast("Any", hass)))

    assert info["configured_entries"] == 1
    assert info["loaded_entries"] == 1
    assert info["locks"] == 1
    assert info["coordinators"] == 1
    assert info["successful_coordinators"] == 1
    assert info["online_locks"] == 1
    assert inspect.isawaitable(info["can_reach_server"])
    assert asyncio.run(_resolve(info["can_reach_server"])) == "ok"


def test_system_health_registers_info_callback() -> None:
    """The system health platform should register the info callback."""
    registration = SimpleNamespace(async_register_info=Mock())

    anona_system_health.async_register(cast("Any", object()), cast("Any", registration))

    registration.async_register_info.assert_called_once_with(
        anona_system_health.system_health_info
    )


async def _resolve(awaitable: Awaitable[Any]) -> Any:
    """Resolve an awaitable value for synchronous tests."""
    return await awaitable
