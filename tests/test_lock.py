"""Tests for the lock entity behavior."""

# ruff: noqa: S101, PLR2004

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

from custom_components.integration_blueprint.api import AnonaApiError
from custom_components.integration_blueprint.const import DEVICE_TYPE_LOCK, DOMAIN
from custom_components.integration_blueprint.lock import (
    IntegrationBlueprintLock,
    async_setup_entry,
)


def test_lock_entity_maps_state_and_dispatches_commands() -> None:
    """The lock entity should map status payloads and call the API commands."""
    api = Mock()
    api.get_device_status = AsyncMock(
        return_value={"lockState": 0, "isOnline": True, "battery": 81}
    )
    api.is_locked = Mock(return_value=True)
    api.is_online = Mock(return_value=True)
    api.battery_level = Mock(return_value=81)
    api.lock = AsyncMock()
    api.unlock = AsyncMock()

    entity = IntegrationBlueprintLock(api, "device-123", "Front Door")

    asyncio.run(entity.async_update())
    asyncio.run(entity.async_unlock())
    asyncio.run(entity.async_lock())
    attrs = entity.extra_state_attributes or {}

    assert entity.is_locked
    assert entity.available
    assert attrs["battery_level"] == 81
    assert attrs["device_id"] == "device-123"
    api.get_device_status.assert_awaited_once_with("device-123")
    api.unlock.assert_awaited_once_with("device-123")
    api.lock.assert_awaited_once_with("device-123")


def test_lock_entity_marks_itself_unavailable_after_status_error() -> None:
    """A polling error should only affect availability, not crash the entity."""
    api = Mock()
    api.get_device_status = AsyncMock(side_effect=AnonaApiError("boom"))

    entity = IntegrationBlueprintLock(api, "device-123", "Front Door")

    asyncio.run(entity.async_update())

    assert not entity.available
    assert entity.is_locked is None


def test_async_setup_entry_only_adds_lock_devices() -> None:
    """Entity setup should filter the device list to lock hardware only."""
    api = Mock()
    api.get_devices = AsyncMock(
        return_value=[
            {
                "deviceType": DEVICE_TYPE_LOCK,
                "deviceId": "lock-1",
                "deviceName": "Front",
            },
            {"deviceType": 999, "deviceId": "other-1", "deviceName": "Ignored"},
        ]
    )
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": api}})
    entry = SimpleNamespace(entry_id="entry-1")
    added_entities: list[IntegrationBlueprintLock] = []
    update_before_add_flags: list[bool] = []

    def add_entities(
        new_entities: list[IntegrationBlueprintLock],
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
    assert added_entities[0].unique_id == f"{DOMAIN}_lock-1"
    assert added_entities[0].name == "Front"
    assert update_before_add_flags == [True]
