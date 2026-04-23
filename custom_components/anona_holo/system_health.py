"""Provide system health information for Anona Holo."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import API_BASE_URL, DOMAIN

if TYPE_CHECKING:
    from . import AnonaConfigEntry, AnonaHoloRuntimeData
    from .coordinator import AnonaDeviceCoordinator


@callback
def async_register(
    _hass: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return integration health details for the system information page."""
    configured_entries = cast(
        "list[AnonaConfigEntry]",
        hass.config_entries.async_entries(DOMAIN),
    )
    loaded_entries = [
        entry
        for entry in configured_entries
        if getattr(entry, "runtime_data", None) is not None
    ]

    devices_count = 0
    coordinators: list[AnonaDeviceCoordinator] = []
    for entry in loaded_entries:
        runtime_data = cast("AnonaHoloRuntimeData", entry.runtime_data)
        devices_count += len(runtime_data.devices)
        coordinators.extend(runtime_data.coordinators.values())

    successful_coordinators = sum(
        1 for coordinator in coordinators if coordinator.last_update_success
    )
    online_locks = sum(
        1
        for coordinator in coordinators
        if coordinator.data is not None
        and coordinator.data.online_status is not None
        and coordinator.data.online_status.online
    )

    return {
        "configured_entries": len(configured_entries),
        "loaded_entries": len(loaded_entries),
        "locks": devices_count,
        "coordinators": len(coordinators),
        "successful_coordinators": successful_coordinators,
        "online_locks": online_locks,
        "can_reach_server": system_health.async_check_can_reach_url(
            hass,
            API_BASE_URL,
        ),
    }
