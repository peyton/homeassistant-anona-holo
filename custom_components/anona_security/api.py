"""Anona Security API client used by the lock-only integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_DEVICE_STATUS,
    ENDPOINT_HOME_LIST,
    ENDPOINT_LOGIN,
    ENDPOINT_WEBSOCKET_ADDRESS,
    LOCK_STATE_LOCKED,
    RESP_CODE,
    RESP_DATA,
    RESP_SUCCESS_CODE,
    WS_CMD_AUTH,
    WS_CMD_LOCK,
    WS_CMD_STATUS,
    WS_CMD_UNLOCK,
)


class AnonaApiError(Exception):
    """Base exception for Anona API errors."""

    @classmethod
    def from_http_status(cls, endpoint: str, status_code: int) -> AnonaApiError:
        """Build an error from an HTTP status code."""
        return cls(f"HTTP {status_code} from {endpoint}")

    @classmethod
    def from_api_response(cls, code: Any, message: str) -> AnonaApiError:
        """Build an error from an API response payload."""
        return cls(f"API error {code}: {message}")

    @classmethod
    def from_websocket_error(cls, error: Exception) -> AnonaApiError:
        """Build an error from a WebSocket failure."""
        return cls(f"WebSocket error: {error}")

    @classmethod
    def no_home_id(cls) -> AnonaApiError:
        """Build an error for a missing home identifier."""
        return cls("No home_id available; login first")

    @classmethod
    def no_websocket_address(cls) -> AnonaApiError:
        """Build an error for a missing WebSocket address."""
        return cls("No WebSocket address returned")


class AnonaAuthError(AnonaApiError):
    """Raised when authentication fails."""

    @classmethod
    def invalid_payload(cls) -> AnonaAuthError:
        """Build an error for an invalid login payload."""
        return cls("Invalid login payload returned from API")

    @classmethod
    def missing_token(cls) -> AnonaAuthError:
        """Build an error for a missing login token."""
        return cls("No accessToken in login response")


class AnonaApi:
    """Client for the Anona Security cloud API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session
        self._access_token: str | None = None
        self._user_id: str | None = None
        self._home_id: str | None = None

    def _headers(self) -> dict[str, str]:
        """Build request headers for the current auth state."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._access_token:
            headers["accessToken"] = self._access_token
        return headers

    async def _post(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a POST request against the Anona API."""
        http_ok = 200
        async with self._session.post(
            f"{API_BASE_URL}{endpoint}",
            json=payload or {},
            headers=self._headers(),
        ) as response:
            if response.status != http_ok:
                raise AnonaApiError.from_http_status(endpoint, response.status)

            data: dict[str, Any] = await response.json()
            if data.get(RESP_CODE) != RESP_SUCCESS_CODE:
                msg = data.get("message", "unknown error")
                code = data.get(RESP_CODE, -1)
                raise AnonaApiError.from_api_response(code, str(msg))

            return data

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate and cache the resulting token and identifiers."""
        password_hash = hashlib.md5(
            password.encode(),
            usedforsecurity=False,
        ).hexdigest()

        try:
            result = await self._post(
                ENDPOINT_LOGIN,
                {"loginName": email, "userLoginPwd": password_hash},
            )
        except AnonaApiError as err:
            raise AnonaAuthError(str(err)) from err

        data = result.get(RESP_DATA, {})
        if not isinstance(data, dict):
            raise AnonaAuthError.invalid_payload()

        self._access_token = _string_or_none(data.get("accessToken"))
        self._user_id = _string_or_none(data.get("userId"))
        self._home_id = _string_or_none(data.get("homeId"))

        if not self._access_token:
            raise AnonaAuthError.missing_token()

        return data

    @property
    def access_token(self) -> str | None:
        """Return the cached access token."""
        return self._access_token

    @property
    def user_id(self) -> str | None:
        """Return the cached user identifier."""
        return self._user_id

    @property
    def home_id(self) -> str | None:
        """Return the cached home identifier."""
        return self._home_id

    async def get_homes(self) -> list[dict[str, Any]]:
        """Return the homes visible to the logged-in user."""
        result = await self._post(ENDPOINT_HOME_LIST)
        data = result.get(RESP_DATA, [])
        return data if isinstance(data, list) else []

    async def get_devices(
        self,
        home_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return devices for the active or supplied home."""
        resolved_home_id = home_id or self._home_id
        if not resolved_home_id:
            raise AnonaApiError.no_home_id()

        result = await self._post(ENDPOINT_DEVICE_LIST, {"homeId": resolved_home_id})
        data = result.get(RESP_DATA, {})
        if not isinstance(data, dict):
            return []

        device_list = data.get("deviceList", [])
        return device_list if isinstance(device_list, list) else []

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Return the current device status for a device identifier."""
        result = await self._post(ENDPOINT_DEVICE_STATUS, {"deviceId": device_id})
        data = result.get(RESP_DATA, {})
        return data if isinstance(data, dict) else {}

    async def _get_ws_address(self) -> str:
        """Fetch the WebSocket endpoint used for lock commands."""
        result = await self._post(ENDPOINT_WEBSOCKET_ADDRESS)
        data = result.get(RESP_DATA, {})
        if not isinstance(data, dict):
            raise AnonaApiError.no_websocket_address()

        address = (
            _string_or_none(data.get("websocketAddress"))
            or _string_or_none(data.get("address"))
            or _string_or_none(data.get("url"))
        )
        if not address:
            raise AnonaApiError.no_websocket_address()
        if not address.startswith("ws"):
            address = f"wss://{address}"
        return address

    async def _ws_send_command(
        self,
        device_id: str,
        cmd_type: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Open a WebSocket, authenticate, and send a device command."""
        ws_url = await self._get_ws_address()

        try:
            async with self._session.ws_connect(ws_url) as websocket:
                await websocket.send_str(
                    json.dumps(
                        {
                            "cmdType": WS_CMD_AUTH,
                            "token": self._access_token,
                            "userId": self._user_id,
                        }
                    )
                )
                await asyncio.wait_for(websocket.receive_str(), timeout=10)

                command: dict[str, Any] = {
                    "cmdType": cmd_type,
                    "deviceId": device_id,
                    "token": self._access_token,
                }
                if extra:
                    command.update(extra)
                await websocket.send_str(json.dumps(command))

                response = await asyncio.wait_for(websocket.receive_str(), timeout=15)
                payload = json.loads(response)
                return payload if isinstance(payload, dict) else None
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise AnonaApiError.from_websocket_error(err) from err

    async def lock(self, device_id: str) -> None:
        """Send the lock command."""
        await self._ws_send_command(device_id, WS_CMD_LOCK)

    async def unlock(self, device_id: str) -> None:
        """Send the unlock command."""
        await self._ws_send_command(device_id, WS_CMD_UNLOCK)

    async def ws_get_status(self, device_id: str) -> dict[str, Any] | None:
        """Fetch status through the WebSocket control channel."""
        return await self._ws_send_command(device_id, WS_CMD_STATUS)

    def is_locked(self, status: dict[str, Any]) -> bool:
        """Map the device status payload into a Home Assistant lock state."""
        return status.get("lockState") == LOCK_STATE_LOCKED

    def is_online(self, status: dict[str, Any]) -> bool:
        """Map online state from the device status payload."""
        return bool(status.get("isOnline") or status.get("online"))

    def battery_level(self, status: dict[str, Any]) -> int | None:
        """Extract battery level from known response keys."""
        for key in ("battery", "batteryVoltage", "batteryLevel"):
            value = status.get(key)
            if value is not None:
                return int(value)
        return None


def _string_or_none(value: Any) -> str | None:
    """Normalize a value into a string when possible."""
    if value is None:
        return None
    return str(value)
