"""Diagnostics support for the Anona Holo integration."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, cast

from .const import DATA_API, DATA_COORDINATORS, DATA_DEVICES, DOMAIN
from .privacy import redact_data

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics data for a config entry."""
    return _build_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics data for a device entry."""
    device_id = _device_identifier(device)
    return _build_diagnostics(
        hass,
        entry,
        device_ids={device_id} if device_id is not None else set(),
    )


def _build_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    device_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return redacted diagnostics for an entry or a subset of its devices."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinators = entry_data.get(DATA_COORDINATORS, {})
    api = entry_data.get(DATA_API)
    devices = entry_data.get(DATA_DEVICES, {})

    diagnostics: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "api": {
            "home_id": api.home_id if api is not None else None,
            "user_id": api.user_id if api is not None else None,
            "client_uuid": api.client_uuid if api is not None else None,
        },
        "devices": [
            {
                "device": _to_plain_data(device),
                "snapshot": _to_plain_data(coordinator.data),
                "last_update_success": coordinator.last_update_success,
            }
            for device_id, device in devices.items()
            if (device_ids is None or device_id in device_ids)
            if (coordinator := coordinators.get(device_id)) is not None
        ],
    }
    return redact_data(diagnostics)


def _to_plain_data(value: Any) -> Any:
    """Convert dataclasses and nested mappings into JSON-like primitives."""
    if is_dataclass(value):
        return _to_plain_data(asdict(cast("Any", value)))
    if isinstance(value, dict):
        return {key: _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_data(item) for item in value]
    return value


def _device_identifier(device: DeviceEntry) -> str | None:
    """Return the Anona device identifier from a Home Assistant device entry."""
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return identifier
    return None
