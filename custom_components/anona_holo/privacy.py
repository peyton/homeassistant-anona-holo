"""Privacy helpers for diagnostics and log-safe messages."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data

from .const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
)

TO_REDACT = frozenset(
    {
        CONF_EMAIL,
        CONF_PASSWORD,
        CONF_CLIENT_UUID,
        CONF_USER_ID,
        CONF_HOME_ID,
        "accessToken",
        "access_token",
        "address",
        "btMac",
        "bt_mac",
        "clientUUID",
        "clientUuid",
        "client_uuid",
        "deviceCerts",
        "deviceId",
        "deviceName",
        "deviceNickName",
        "device_id",
        "email",
        "handshakeToken",
        "homeId",
        "homeName",
        "home_id",
        "ip",
        "ip_address",
        "mac",
        "mobile",
        "nickname",
        "passWord",
        "password",
        "privateKey",
        "refreshToken",
        "refresh_token",
        "serial_number",
        "sig",
        "sn",
        "timezoneId",
        "timezone_id",
        "title",
        "token",
        "userCerts",
        "userCertsPriKey",
        "userID",
        "userId",
        "userName",
        "user_id",
        "user_name",
        "uuid",
        "websocketAesKey",
        "websocketAddress",
        "websocketToken",
        "wifiApSsid",
        "wifiName",
        "wifiMac",
        "wifi_ap_ssid",
        "wifi_mac",
    }
)

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
    re.compile(r"(?:^|[_-])ip(?:[_-]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_-])mac(?:[_-]|$)", re.IGNORECASE),
    re.compile(r"cert", re.IGNORECASE),
    re.compile(r"private", re.IGNORECASE),
    re.compile(r"(?:^|[_-])key(?:[_-]|$)", re.IGNORECASE),
    re.compile(r"ssid", re.IGNORECASE),
    re.compile(r"timezone", re.IGNORECASE),
)

_EMAIL_PATTERN = re.compile(r"[^@\s<>()]+@[^@\s<>()]+\.[^@\s<>()]+")
_IPV4_PATTERN = re.compile(r"(?:\b\d{1,3}\.){3}\d{1,3}\b")
_MAC_PATTERN = re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b")
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_LONG_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{16,}$")
_PEM_PATTERN = re.compile(r"-----BEGIN [A-Z ]+-----")


def redact_data(value: Any) -> Any:
    """Redact diagnostics data with Home Assistant's helper and local safeguards."""
    return _redact_sensitive_values(async_redact_data(value, TO_REDACT))


def redact_log_value(
    value: object,
    *,
    extra_values: tuple[str | None, ...] = (),
) -> object:
    """Return a value safe to interpolate into logs or exception messages."""
    if isinstance(value, str):
        return _redact_sensitive_string(value, extra_values=extra_values)
    return _redact_sensitive_values(value)


def _redact_sensitive_values(value: Any, *, key_name: str | None = None) -> Any:
    """Recursively redact sensitive values by key and value shape."""
    if _is_sensitive_key(key_name):
        return REDACTED

    if isinstance(value, dict):
        return {
            key: _redact_sensitive_values(item, key_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_values(item, key_name=key_name) for item in value]
    if isinstance(value, tuple):
        return [_redact_sensitive_values(item, key_name=key_name) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_string(value)
    return value


def _is_sensitive_key(key_name: str | None) -> bool:
    """Return whether a diagnostics or payload key should always be redacted."""
    if key_name is None:
        return False
    return key_name in TO_REDACT or any(
        pattern.search(key_name) for pattern in _SENSITIVE_KEY_PATTERNS
    )


def _redact_sensitive_string(
    value: str,
    *,
    extra_values: tuple[str | None, ...] = (),
) -> str:
    """Redact strings that look like account, device, network, or key material."""
    stripped = value.strip()
    if not stripped:
        return value
    if any(
        pattern.search(stripped)
        for pattern in (
            _EMAIL_PATTERN,
            _IPV4_PATTERN,
            _MAC_PATTERN,
            _UUID_PATTERN,
            _PEM_PATTERN,
        )
    ):
        return REDACTED
    if _LONG_HEX_PATTERN.fullmatch(stripped):
        return REDACTED

    redacted_value = value
    for extra_value in extra_values:
        if extra_value:
            redacted_value = redacted_value.replace(extra_value, REDACTED)
    return redacted_value
