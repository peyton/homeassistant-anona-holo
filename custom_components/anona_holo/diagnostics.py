"""Diagnostics support for the Anona Holo integration."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, cast

from .const import DATA_API, DATA_COORDINATORS, DATA_DEVICES, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_REDACTED = "**REDACTED**"

_SENSITIVE_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"email", re.IGNORECASE),
    re.compile(r"(?:^|[_-])user(?:[_-])?id$", re.IGNORECASE),
    re.compile(r"(?:^|[_-])home(?:[_-])?id$", re.IGNORECASE),
    re.compile(r"(?:^|[_-])device(?:[_-])?id$", re.IGNORECASE),
    re.compile(r"uuid", re.IGNORECASE),
    re.compile(r"(?:^|[_-])sn$", re.IGNORECASE),
    re.compile(r"serial", re.IGNORECASE),
    re.compile(r"imei", re.IGNORECASE),
    re.compile(r"(?:^|[_-])ip(?:[_-]|$)", re.IGNORECASE),
    re.compile(r"mac", re.IGNORECASE),
    re.compile(r"cert", re.IGNORECASE),
    re.compile(r"private", re.IGNORECASE),
    re.compile(r"(?:^|[_-])key(?:[_-]|$)", re.IGNORECASE),
)

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_IPV4_PATTERN = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_MAC_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_LONG_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{16,}$")
_PEM_PATTERN = re.compile(r"-----BEGIN [A-Z ]+-----")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics data for a config entry."""
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
            if (coordinator := coordinators.get(device_id)) is not None
        ],
    }
    return _redact(diagnostics)


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


def _redact(value: Any, *, key_name: str | None = None) -> Any:
    """Recursively redact sensitive values in diagnostics payloads."""
    if _is_sensitive_key(key_name):
        return _REDACTED

    if isinstance(value, dict):
        return {key: _redact(item, key_name=key) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key_name=key_name) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, key_name=key_name) for item in value]
    if isinstance(value, str) and _is_sensitive_string(value):
        return _REDACTED
    return value


def _is_sensitive_key(key_name: str | None) -> bool:
    """Return whether a diagnostics key should always be redacted."""
    if key_name is None:
        return False
    return any(pattern.search(key_name) for pattern in _SENSITIVE_KEY_PATTERNS)


def _is_sensitive_string(value: str) -> bool:
    """Return whether a raw string looks like sensitive account/device data."""
    stripped = value.strip()
    if not stripped:
        return False
    if any(
        (
            _EMAIL_PATTERN.fullmatch(stripped),
            _IPV4_PATTERN.fullmatch(stripped),
            _MAC_PATTERN.fullmatch(stripped),
            _UUID_PATTERN.fullmatch(stripped),
            _LONG_HEX_PATTERN.fullmatch(stripped),
        )
    ):
        return True
    return bool(_PEM_PATTERN.search(stripped))
