"""Anona Holo API client aligned with the captured mobile app traffic."""

# ruff: noqa: ERA001

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import re
import time
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from aiohttp import ClientError, WSMsgType
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from .const import (
    API_BASE_URL,
    APP_CHANNEL,
    APP_DEVICE_TYPE,
    COMMAND_ID_LOCK,
    COMMAND_ID_UNLOCK,
    DEFAULT_LANG,
    DEFAULT_SILENT_OTA_TIME_WINDOW,
    DEVICE_TYPE_LOCK,
    ENDPOINT_DEVICE_CERTS,
    ENDPOINT_DEVICE_INFO,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_DEVICE_ONLINE,
    ENDPOINT_DEVICE_STATUS,
    ENDPOINT_DEVICE_SWITCH,
    ENDPOINT_DEVICE_SWITCH_LIST_BY_HOME,
    ENDPOINT_GET_TS,
    ENDPOINT_HOME_LIST,
    ENDPOINT_LOGIN,
    ENDPOINT_SET_SILENT_OTA,
    ENDPOINT_UPDATE_DEVICE_SWITCH,
    ENDPOINT_VERSION_CHECK,
    ENDPOINT_WEBSOCKET_ADDRESS,
    PASSWORD_SIGN_SALT,
    STATUS_SMART_TYPE,
    WEBSOCKET_COMMAND_TARGET,
    WEBSOCKET_TIMEOUT_SECONDS,
)
from .privacy import redact_log_value

if TYPE_CHECKING:
    import aiohttp

_LOGGER = logging.getLogger(__name__)
HTTP_STATUS_OK = 200
PROTOBUF_WIRE_VARINT = 0
PROTOBUF_WIRE_LENGTH_DELIMITED = 2
PROTOBUF_VARINT_MASK = 0x7F
AES_BLOCK_SIZE_BITS = 128
AES_BLOCK_SIZE_BYTES = 16
WEBSOCKET_AES_KEY_LENGTH = 16
WEBSOCKET_FRAME_CRC_SIZE_BYTES = 4
SILENT_OTA_MAX_HOUR = 23
SILENT_OTA_MAX_MINUTE = 59
SILENT_OTA_WINDOW_PATTERN = re.compile(
    r"^(?P<begin_hour>\d{1,2}):(?P<begin_minute>\d{2})-(?P<end_hour>\d{1,2}):(?P<end_minute>\d{2})$"
)
VERSION_TOKEN_PATTERN = re.compile(r"[A-Za-z]+|\d+")
AUTO_LOCK_DELAY_LABELS: dict[int, str] = {
    0: "No delay",
    5: "5 seconds",
    10: "10 seconds",
    15: "15 seconds",
    30: "30 seconds",
    60: "1 minute",
    180: "3 minutes",
}
SOUND_VOLUME_LABELS: dict[int, str] = {
    1: "Low",
    2: "High",
}

type DecodedProtoValue = int | dict[str, DecodedProtoValue] | list[DecodedProtoValue]


class AnonaApiError(Exception):
    """Base exception for Anona API failures."""


class AnonaAuthError(AnonaApiError):
    """Raised when authentication fails."""


class AnonaConnectionError(AnonaApiError):
    """Raised when the Anona API cannot be reached."""


class AnonaSignatureError(AnonaApiError):
    """Raised when a request signature cannot be produced or is rejected."""


class AnonaUnsupportedCommandError(AnonaApiError):
    """Raised when lock control remains blocked by missing protocol evidence."""


class AnonaCommandError(AnonaApiError):
    """Raised when websocket command delivery fails."""


@dataclass(slots=True, frozen=True)
class LoginContext:
    """Authenticated session information returned by login."""

    token: str
    user_id: str
    user_name: str | None
    channel: int | None


@dataclass(slots=True, frozen=True)
class HomeContext:
    """Normalized home information from the Anona API."""

    home_id: str
    name: str
    is_default: bool
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class DeviceContext:
    """Normalized per-device metadata used for later requests."""

    device_id: str
    device_type: int
    device_module: int
    device_channel: int
    nickname: str
    serial_number: str | None
    model: str | None
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class OnlineStatus:
    """Online-state information for a device."""

    online: bool
    create_ts: int | None
    last_alive_ts: int | None
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class LockStatus:
    """Decoded lock status derived from the `dataHexStr` payload."""

    locked: bool | None
    lock_status_code: int | None
    battery_capacity: int | None
    battery_voltage: int | None
    charge_status_code: int | None
    door_state_code: int | None
    door_status_code: int | None
    has_locking_fail: bool | None
    has_door_been_open_long_time: bool | None
    calibration_status_code: int | None
    long_endurance_mode_status_code: int | None
    keypad_connection_status_code: int | None
    keypad_battery_capacity: int | None
    keypad_status_code: int | None
    data_hex_str: str
    refresh_ts: int | None
    start_type: int | None
    raw_fields: dict[str, DecodedProtoValue]
    auto_lock_enabled: bool | None = None
    auto_lock_delay_seconds: int | None = None
    auto_lock_delay_label: str | None = None
    sound_volume_code: int | None = None
    sound_volume: str | None = None
    low_power_mode_enabled: bool | None = None


@dataclass(slots=True, frozen=True)
class DeviceInfoContext:
    """Normalized device info details from getDeviceInfo."""

    device_id: str
    device_type: int | None
    device_module: int | None
    device_channel: int | None
    firmware_version: str | None
    firmware_sub_version: str | None
    ip_address: str | None
    wifi_ap_ssid: str | None
    wifi_mac: str | None
    bt_mac: str | None
    timezone_id: str | None
    silent_ota_enabled: bool | None
    silent_ota_time: str | None
    silent_ota_time_raw: str | None
    last_online_ts: int | None
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class DeviceSwitchSettings:
    """Normalized notification switch settings for a device."""

    device_id: str
    main_switch: bool
    ugent_notify_switch: bool
    important_notify_switch: bool
    normal_notify_switch: bool
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class FirmwareUpdateContext:
    """Firmware version and release metadata returned by checkNewRomFromApp."""

    device_id: str
    installed_version: str | None
    latest_version: str | None
    latest_sub_version: str | None
    new_version: bool | None
    version_order: int | None
    release_notes: str | None
    release_url: str | None
    release_ts: int | None
    file_md5: str | None
    file_size: int | None
    is_forced: bool | None
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class DeviceCerts:
    """Certificate material returned before websocket control."""

    device_id: str
    device_certs: str | None
    user_certs: str | None
    user_certs_private_key: str | None
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class WebsocketContext:
    """Websocket bootstrap information for command delivery."""

    address: str
    websocket_token: str | None
    websocket_aes_key: str | None
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class WebsocketMessage:
    """Normalized websocket message payload."""

    operate_id: str | None
    ts: int | None
    device_id: str | None
    source: int | None
    target: int | None
    content: str | None
    ack_code: int | None
    is_ack: bool
    raw: dict[str, Any]


@dataclass(slots=True, frozen=True)
class SignedRequest:
    """Request context passed to the signature provider."""

    endpoint: str
    payload: Mapping[str, Any]
    ts: int
    uuid: str
    channel: int
    token: str | None


class SignatureProvider(Protocol):
    """Protocol for pluggable request-signature providers."""

    async def async_get_signature(self, request: SignedRequest) -> str:
        """Return the signature for a request."""
        ...


class NativeSignatureProvider:
    """Signature provider verified against the live mobile API."""

    async def async_get_signature(self, request: SignedRequest) -> str:
        """Return a signature compatible with the native mobile client."""
        if request.endpoint == ENDPOINT_LOGIN or request.token is None:
            email = _require_string(request.payload.get("email"), "login email")
            password_hash = _require_string(
                request.payload.get("passWord"),
                "login passWord",
            )
            device_type = (
                _coerce_int(request.payload.get("deviceType")) or APP_DEVICE_TYPE
            )
            return build_login_signature(
                email=email,
                password_hash=password_hash,
                ts=request.ts,
                mobile=_coerce_string(request.payload.get("mobile")),
                device_type=device_type,
            )
        return build_authenticated_signature(
            token=request.token,
            client_uuid=request.uuid,
            channel=request.channel,
            ts=request.ts,
        )


@dataclass(slots=True)
class StaticSignatureProvider:
    """Simple signature provider for tests and fixture-backed flows."""

    signatures: Mapping[str, str]
    default_signature: str | None = None

    async def async_get_signature(self, request: SignedRequest) -> str:
        """Return a precomputed signature for the given endpoint."""
        endpoint_signature = self.signatures.get(request.endpoint)
        if endpoint_signature is not None:
            return endpoint_signature
        if self.default_signature is not None:
            return self.default_signature
        message = f"No precomputed signature provided for endpoint {request.endpoint}"
        raise AnonaSignatureError(message)


class AnonaApi:
    """Stateful client for the captured Anona mobile API."""

    def __init__(  # noqa: PLR0913
        self,
        session: aiohttp.ClientSession,
        *,
        client_uuid: str,
        base_url: str = API_BASE_URL,
        home_id: str | None = None,
        user_id: str | None = None,
        signature_provider: SignatureProvider | None = None,
    ) -> None:
        """Initialize the client with a stable per-entry UUID."""
        self._session = session
        self._base_url = base_url
        self._client_uuid = client_uuid
        self._home_id = home_id
        self._token: str | None = None
        self._user_id = user_id
        self._signature_provider = signature_provider or NativeSignatureProvider()
        self._devices_by_id: dict[str, DeviceContext] = {}
        self._device_info_by_id: dict[str, DeviceInfoContext] = {}
        self._device_switch_settings_by_id: dict[str, DeviceSwitchSettings] = {}
        self._firmware_update_by_id: dict[str, FirmwareUpdateContext] = {}

    @property
    def client_uuid(self) -> str:
        """Return the persistent client UUID used for signed requests."""
        return self._client_uuid

    @property
    def token(self) -> str | None:
        """Return the cached API token, if available."""
        return self._token

    @property
    def user_id(self) -> str | None:
        """Return the authenticated user identifier, if available."""
        return self._user_id

    @property
    def home_id(self) -> str | None:
        """Return the active home identifier, if available."""
        return self._home_id

    def set_home_id(self, home_id: str | None) -> None:
        """Set the active home identifier after discovery."""
        self._home_id = home_id

    async def login(self, email: str, password: str) -> LoginContext:
        """Authenticate with the captured login flow and cache the session."""
        payload = {
            "email": email,
            "passWord": hash_password(password),
            "deviceType": APP_DEVICE_TYPE,
            "lang": DEFAULT_LANG,
            "deviceToken": "",
        }
        result = await self._post_signed(ENDPOINT_LOGIN, payload, include_token=False)
        result_map = _require_mapping(result, "login response")
        token = _require_string(result_map.get("token"), "login token")
        user_id = _require_string(
            result_map.get("userID") or result_map.get("userId"),
            "login userID",
        )
        login_context = LoginContext(
            token=token,
            user_id=user_id,
            user_name=_coerce_string(result_map.get("userName")),
            channel=_coerce_int(result_map.get("channel")),
        )
        self._token = login_context.token
        self._user_id = login_context.user_id
        return login_context

    async def get_server_ts(self) -> int:
        """Fetch the server timestamp required for signed requests."""
        result = await self._post_enveloped(ENDPOINT_GET_TS, payload={})
        timestamp = result.get("resultBodyObject")
        timestamp_int = _coerce_int(timestamp)
        if timestamp_int is None:
            message = "Server timestamp response did not contain an integer"
            raise AnonaApiError(message)
        return timestamp_int

    async def get_homes(self) -> list[HomeContext]:
        """Return the normalized homes visible to the logged-in user."""
        result = await self._post_signed(ENDPOINT_HOME_LIST, {})
        result_map = _require_mapping(result, "home list response")
        default_home_payload = _optional_mapping(result_map.get("defaultHome"))
        default_home_id = (
            _coerce_string(default_home_payload.get("homeId"))
            if default_home_payload
            else None
        )
        homes_payload = result_map.get("actualHomeNameList", [])
        homes_list = homes_payload if isinstance(homes_payload, list) else []

        homes: list[HomeContext] = [
            normalize_home_context(item, default_home_id)
            for item in homes_list
            if isinstance(item, Mapping)
        ]
        if default_home_payload is not None and default_home_id not in {
            home.home_id for home in homes
        }:
            homes.append(normalize_home_context(default_home_payload, default_home_id))

        if self._user_id is None:
            self._user_id = _coerce_string(result_map.get("userId"))

        selected_home = select_home_id(homes)
        if selected_home is not None:
            self._home_id = selected_home
        return homes

    async def get_devices(self, home_id: str | None = None) -> list[DeviceContext]:
        """Return devices for the active or supplied home."""
        resolved_home_id = home_id or self._home_id
        if resolved_home_id is None:
            message = "No home_id available; login and fetch homes first"
            raise AnonaApiError(message)

        result = await self._post_signed(
            ENDPOINT_DEVICE_LIST,
            {
                "homeId": resolved_home_id,
                "pageCount": 500,
                "needRelation": True,
            },
        )
        devices_payload = (
            result
            if isinstance(result, list)
            else _require_mapping(result, "device list response").get(
                "deviceList",
                [],
            )
        )
        if not isinstance(devices_payload, list):
            message = "Device list response was not a list"
            raise AnonaApiError(message)

        devices = [
            normalize_device_context(item)
            for item in devices_payload
            if isinstance(item, Mapping)
        ]
        self._devices_by_id.update({device.device_id: device for device in devices})
        return devices

    async def get_all_devices(self) -> list[DeviceContext]:
        """Return devices from all homes visible to the authenticated user."""
        homes = await self.get_homes()
        all_devices: list[DeviceContext] = []
        for home in homes:
            devices = await self.get_devices(home.home_id)
            all_devices.extend(devices)

        unique_devices: list[DeviceContext] = []
        seen_device_ids: set[str] = set()
        for device in all_devices:
            if device.device_id in seen_device_ids:
                continue
            unique_devices.append(device)
            seen_device_ids.add(device.device_id)
        return unique_devices

    async def get_device_info(self, device_id: str) -> DeviceContext:
        """Fetch a single device payload and normalize it."""
        result = await self._post_signed(ENDPOINT_DEVICE_INFO, {"deviceId": device_id})
        result_map = _require_mapping(result, "device info response")
        device = normalize_device_context(result_map)
        self._devices_by_id[device.device_id] = device
        return device

    async def get_device_online_status(
        self, device: DeviceContext | str
    ) -> OnlineStatus:
        """Return the current online state for a device."""
        device_id = device.device_id if isinstance(device, DeviceContext) else device
        result = await self._post_signed(
            ENDPOINT_DEVICE_ONLINE, {"deviceId": device_id}
        )
        result_map = _require_mapping(result, "device online response")
        return OnlineStatus(
            online=bool(result_map.get("online")),
            create_ts=_coerce_int(result_map.get("createTs")),
            last_alive_ts=_coerce_int(result_map.get("lastAliveTs")),
            raw=dict(result_map),
        )

    async def get_device_status(self, device: DeviceContext | str) -> LockStatus:
        """Return the decoded lock status for a device."""
        device_context = self._resolve_device_context(device)
        result = await self._post_signed(
            ENDPOINT_DEVICE_STATUS,
            {
                "smartType": STATUS_SMART_TYPE,
                "deviceId": device_context.device_id,
                "deviceModule": device_context.device_module,
                "deviceType": device_context.device_type,
                "deviceChannel": device_context.device_channel,
            },
        )
        result_map = _require_mapping(result, "device status response")
        data_hex_str = _require_string(
            result_map.get("dataHexStr"), "device status dataHexStr"
        )
        status = parse_lock_status(
            data_hex_str,
            refresh_ts=_coerce_int(result_map.get("refreshTs")),
            start_type=_coerce_int(result_map.get("startType")),
        )
        _LOGGER.debug(
            "Decoded Anona lock status: locked=%s battery=%s door=%s auto_lock=%s",
            status.locked,
            status.battery_capacity,
            status.door_state_code,
            status.auto_lock_enabled,
        )
        return status

    async def get_device_info_context(
        self,
        device: DeviceContext | str,
    ) -> DeviceInfoContext:
        """Fetch and normalize detailed device metadata."""
        device_id = self._resolve_device_id(device)
        result = await self._post_signed(ENDPOINT_DEVICE_INFO, {"deviceId": device_id})
        result_map = _require_mapping(result, "device info response")
        context = normalize_device_info_context(result_map)
        self._device_info_by_id[device_id] = context

        try:
            normalized_device = normalize_device_context(result_map)
        except AnonaApiError:
            pass
        else:
            self._devices_by_id[normalized_device.device_id] = normalized_device
        return context

    async def get_device_switch_settings(
        self,
        device: DeviceContext | str,
    ) -> DeviceSwitchSettings:
        """Fetch and normalize the notification switch settings for a device."""
        device_id = self._resolve_device_id(device)
        result = await self._post_signed(
            ENDPOINT_DEVICE_SWITCH, {"deviceId": device_id}
        )
        result_map = _require_mapping(result, "device switch response")
        settings = normalize_device_switch_settings(result_map, device_id=device_id)
        self._device_switch_settings_by_id[device_id] = settings
        return settings

    async def get_device_switch_list_by_home(
        self,
        home_id: str | None = None,
    ) -> dict[str, DeviceSwitchSettings]:
        """Return switch settings for devices in a home via list-by-home endpoint."""
        resolved_home_id = home_id or self._home_id
        if resolved_home_id is None:
            message = "No home_id available; login and fetch homes first"
            raise AnonaApiError(message)
        result = await self._post_signed(
            ENDPOINT_DEVICE_SWITCH_LIST_BY_HOME,
            {"homeId": resolved_home_id},
        )
        payload: list[Mapping[str, Any]]
        if isinstance(result, list):
            payload = [item for item in result if isinstance(item, Mapping)]
        else:
            result_map = _require_mapping(result, "device switch list response")
            raw_list = result_map.get("deviceSwitchList", [])
            if not isinstance(raw_list, list):
                message = "Device switch list response was not a list"
                raise AnonaApiError(message)
            payload = [item for item in raw_list if isinstance(item, Mapping)]

        settings_by_device_id: dict[str, DeviceSwitchSettings] = {}
        for item in payload:
            settings = normalize_device_switch_settings(item)
            settings_by_device_id[settings.device_id] = settings
            self._device_switch_settings_by_id[settings.device_id] = settings
        return settings_by_device_id

    async def update_device_switch_settings(
        self,
        device: DeviceContext | str,
        *,
        main_switch: bool,
        ugent_notify_switch: bool,
        important_notify_switch: bool,
        normal_notify_switch: bool,
    ) -> DeviceSwitchSettings:
        """Persist notification switch settings and return the normalized result."""
        device_id = self._resolve_device_id(device)
        payload = {
            "deviceId": device_id,
            "mainSwitch": bool(main_switch),
            "ugentNotifySwitch": bool(ugent_notify_switch),
            "importantNotifySwitch": bool(important_notify_switch),
            "normalNotifySwitch": bool(normal_notify_switch),
        }
        result = await self._post_signed(ENDPOINT_UPDATE_DEVICE_SWITCH, payload)
        result_map = _optional_mapping(result) or {}
        merged_payload = {**payload, **result_map}
        settings = normalize_device_switch_settings(merged_payload, device_id=device_id)
        self._device_switch_settings_by_id[device_id] = settings
        return settings

    async def get_firmware_update_context(
        self,
        device: DeviceContext | str,
    ) -> FirmwareUpdateContext:
        """Fetch and normalize firmware update metadata for a device."""
        device_context = self._resolve_device_context(device)
        result = await self._post_signed(
            ENDPOINT_VERSION_CHECK,
            {
                "deviceId": device_context.device_id,
                "deviceType": device_context.device_type,
                "deviceModule": device_context.device_module,
                "deviceChannel": device_context.device_channel,
            },
        )
        result_map = _require_mapping(result, "firmware version response")
        info_context = self._device_info_by_id.get(device_context.device_id)
        firmware_context = normalize_firmware_update_context(
            result_map,
            device_id=device_context.device_id,
            installed_version=info_context.firmware_version if info_context else None,
        )
        self._firmware_update_by_id[device_context.device_id] = firmware_context
        return firmware_context

    async def set_silent_ota(
        self,
        device: DeviceContext | str,
        *,
        enabled: bool,
        silent_ota_time: str,
    ) -> None:
        """Update the silent OTA window for a device."""
        device_id = self._resolve_device_id(device)
        window = silent_ota_time.strip() or DEFAULT_SILENT_OTA_TIME_WINDOW
        serialized_window = serialize_silent_ota_time_window(window)
        await self._post_signed(
            ENDPOINT_SET_SILENT_OTA,
            {
                "deviceId": device_id,
                "silentOTA": bool(enabled),
                "silentOTATime": serialized_window,
            },
        )

        existing_context = self._device_info_by_id.get(device_id)
        if existing_context is None:
            return
        updated_raw = dict(existing_context.raw)
        updated_raw["silentOTA"] = bool(enabled)
        updated_raw["silentOTATime"] = serialized_window
        self._device_info_by_id[device_id] = DeviceInfoContext(
            device_id=existing_context.device_id,
            device_type=existing_context.device_type,
            device_module=existing_context.device_module,
            device_channel=existing_context.device_channel,
            firmware_version=existing_context.firmware_version,
            firmware_sub_version=existing_context.firmware_sub_version,
            ip_address=existing_context.ip_address,
            wifi_ap_ssid=existing_context.wifi_ap_ssid,
            wifi_mac=existing_context.wifi_mac,
            bt_mac=existing_context.bt_mac,
            timezone_id=existing_context.timezone_id,
            silent_ota_enabled=bool(enabled),
            silent_ota_time=deserialize_silent_ota_time_window(serialized_window),
            silent_ota_time_raw=serialized_window,
            last_online_ts=existing_context.last_online_ts,
            raw=updated_raw,
        )

    async def get_device_certs_for_owner(
        self, device: DeviceContext | str
    ) -> DeviceCerts:
        """Fetch the owner certificate material required before websocket auth."""
        device_id = device.device_id if isinstance(device, DeviceContext) else device
        result = await self._post_signed(
            ENDPOINT_DEVICE_CERTS,
            {"deviceId": device_id},
        )
        result_map = _require_mapping(result, "device cert response")
        return DeviceCerts(
            device_id=_require_string(
                result_map.get("deviceId"), "device cert deviceId"
            ),
            device_certs=_coerce_string(result_map.get("deviceCerts")),
            user_certs=_coerce_string(result_map.get("userCerts")),
            user_certs_private_key=_coerce_string(result_map.get("userCertsPriKey")),
            raw=dict(result_map),
        )

    async def get_websocket_address(self) -> WebsocketContext:
        """Fetch the websocket bootstrap payload for device commands."""
        result = await self._post_signed(ENDPOINT_WEBSOCKET_ADDRESS, {})
        result_map = _require_mapping(result, "websocket response")
        address = _require_string(
            result_map.get("websocketAddress")
            or result_map.get("address")
            or result_map.get("url"),
            "websocket address",
        )
        return WebsocketContext(
            address=address,
            websocket_token=_coerce_string(result_map.get("websocketToken")),
            websocket_aes_key=_coerce_string(result_map.get("websocketAesKey")),
            raw=dict(result_map),
        )

    async def lock(self, device: DeviceContext | str) -> None:
        """Lock a device through the captured websocket command flow."""
        await self._execute_websocket_command(device, send_id=COMMAND_ID_LOCK)

    async def unlock(self, device: DeviceContext | str) -> None:
        """Unlock a device through the captured websocket command flow."""
        await self._execute_websocket_command(device, send_id=COMMAND_ID_UNLOCK)

    async def _execute_websocket_command(
        self,
        device: DeviceContext | str,
        *,
        send_id: int,
    ) -> None:
        """Send a websocket device command and wait for its completion callback."""
        device_context = self._resolve_device_context(device)
        if device_context.device_type != DEVICE_TYPE_LOCK:
            message = (
                "Only captured lock devices are supported for websocket commands; "
                f"got device type {device_context.device_type}"
            )
            raise AnonaUnsupportedCommandError(message)

        if self._user_id is None:
            message = "No user_id available; login first"
            raise AnonaAuthError(message)

        await self.get_device_certs_for_owner(device_context)
        websocket_context = await self.get_websocket_address()
        handshake_token = _require_string(
            websocket_context.websocket_token,
            "websocket token",
        )
        websocket_aes_key = _require_string(
            websocket_context.websocket_aes_key,
            "websocket aes key",
        )

        try:
            async with self._session.ws_connect(websocket_context.address) as websocket:
                await self._send_websocket_handshake(websocket, handshake_token)
                operation = build_websocket_operation()
                command_content = build_command_content(send_id, self._user_id)
                encrypted_payload = encrypt_websocket_payload(
                    build_websocket_command_payload(
                        device=device_context,
                        content=command_content,
                        operate_id=operation["operateId"],
                        ts=_require_int(operation["ts"], "websocket command ts"),
                        target=WEBSOCKET_COMMAND_TARGET,
                    ),
                    websocket_aes_key,
                )
                await websocket.send_str(encrypted_payload)
                _LOGGER.debug(
                    "Sent Anona websocket command %s and waiting for acknowledgement",
                    send_id,
                )
                await self._await_websocket_command_result(
                    websocket,
                    websocket_aes_key=websocket_aes_key,
                    operate_id=_require_string(
                        operation["operateId"], "websocket command operateId"
                    ),
                    device_id=device_context.device_id,
                )
        except ClientError as err:
            message = "Cannot connect to the Anona websocket service"
            raise AnonaCommandError(message) from err

    async def _send_websocket_handshake(
        self,
        websocket: aiohttp.ClientWebSocketResponse,
        handshake_token: str,
    ) -> None:
        """Send the plaintext websocket handshake and require an ack."""
        operation = build_websocket_handshake_payload(handshake_token)
        await websocket.send_str(serialize_websocket_payload(operation))
        handshake_ack = await self._receive_websocket_message(
            websocket,
            websocket_aes_key=None,
            timeout_seconds=WEBSOCKET_TIMEOUT_SECONDS,
        )
        operate_id = _require_string(operation["operateId"], "handshake operateId")
        if (
            not handshake_ack.is_ack
            or handshake_ack.ack_code != HTTP_STATUS_OK
            or handshake_ack.operate_id != operate_id
        ):
            message = (
                f"Websocket handshake failed with ack_code={handshake_ack.ack_code!r}"
            )
            raise AnonaCommandError(message)

    async def _await_websocket_command_result(
        self,
        websocket: aiohttp.ClientWebSocketResponse,
        *,
        websocket_aes_key: str,
        operate_id: str,
        device_id: str,
    ) -> WebsocketMessage:
        """Wait for the ack and completion callback for a websocket device command."""
        ack_received = False
        while True:
            message = await self._receive_websocket_message(
                websocket,
                websocket_aes_key=websocket_aes_key,
                timeout_seconds=WEBSOCKET_TIMEOUT_SECONDS,
            )
            if message.is_ack:
                if message.operate_id == operate_id:
                    if message.ack_code != HTTP_STATUS_OK:
                        error_message = (
                            "Websocket command ack failed with "
                            f"ack_code={message.ack_code!r}"
                        )
                        raise AnonaCommandError(error_message)
                    ack_received = True
                continue
            if message.operate_id != operate_id:
                _LOGGER.debug(
                    "Ignoring unrelated Anona websocket push while waiting for "
                    "command result"
                )
                continue
            if message.device_id not in {None, device_id}:
                error_message = (
                    "Websocket command returned a result for a different device"
                )
                raise AnonaCommandError(error_message)
            if not ack_received:
                _LOGGER.debug(
                    "Received websocket command result before explicit ack for %s",
                    operate_id,
                )
            return message

    async def _receive_websocket_message(
        self,
        websocket: aiohttp.ClientWebSocketResponse,
        *,
        websocket_aes_key: str | None,
        timeout_seconds: int,
    ) -> WebsocketMessage:
        """Receive and decode the next websocket text frame."""
        try:
            async with asyncio.timeout(timeout_seconds):
                frame = await websocket.receive()
        except TimeoutError as err:
            message = "Timed out waiting for websocket message"
            raise AnonaCommandError(message) from err

        if frame.type is WSMsgType.TEXT:
            return decode_websocket_message(
                _require_string(frame.data, "websocket text frame"),
                websocket_aes_key=websocket_aes_key,
            )
        if frame.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING}:
            message = "Websocket closed before the command completed"
            raise AnonaCommandError(message)
        if frame.type is WSMsgType.ERROR:
            error = websocket.exception()
            message = f"Websocket error while waiting for command result: {error}"
            raise AnonaCommandError(message)
        message = f"Unexpected websocket frame type: {frame.type!s}"
        raise AnonaCommandError(message)

    async def _post_signed(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        *,
        include_token: bool = True,
    ) -> Any:
        """POST a signed payload and return the unwrapped result body."""
        request_payload = dict(payload)
        timestamp = await self.get_server_ts()
        request_payload.update(
            {
                "uuid": self._client_uuid,
                "channel": APP_CHANNEL,
                "ts": timestamp,
            }
        )
        token = self._token if include_token else None
        if include_token:
            if token is None:
                message = "No token available; login first"
                raise AnonaAuthError(message)
            request_payload["token"] = token
        signature = await self._signature_provider.async_get_signature(
            SignedRequest(
                endpoint=endpoint,
                payload=request_payload,
                ts=timestamp,
                uuid=self._client_uuid,
                channel=APP_CHANNEL,
                token=token,
            )
        )
        request_payload["sig"] = signature
        result = await self._post_enveloped(endpoint, payload=request_payload)
        return result.get("resultBodyObject")

    async def _post_enveloped(
        self,
        endpoint: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST to the API and decode the returned response envelope."""
        request_kwargs: dict[str, Any] = {
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        }
        if payload is not None:
            request_kwargs["json"] = payload

        try:
            async with self._session.post(
                f"{self._base_url}{endpoint}",
                **request_kwargs,
            ) as response:
                if response.status != HTTP_STATUS_OK:
                    message = f"HTTP {response.status} from {endpoint}"
                    raise AnonaApiError(message)
                body_text = await response.text()
        except (ClientError, TimeoutError) as err:
            message = "Cannot connect to the Anona API"
            raise AnonaConnectionError(message) from err

        envelope = decode_response_envelope(body_text)
        error_code = _coerce_int(envelope.get("errorCode")) or 0
        error_message = _coerce_string(envelope.get("errorMessage")) or "unknown error"
        safe_error_message = str(redact_log_value(error_message))
        if envelope.get("error") or error_code != 0:
            lowered_message = error_message.lower()
            if "sig" in lowered_message:
                raise AnonaSignatureError(safe_error_message)
            if endpoint == ENDPOINT_LOGIN:
                raise AnonaAuthError(safe_error_message)
            if "token" in lowered_message:
                raise AnonaAuthError(safe_error_message)
            message = f"API error {error_code}: {safe_error_message}"
            raise AnonaApiError(message)
        return envelope

    def _resolve_device_context(self, device: DeviceContext | str) -> DeviceContext:
        """Resolve a full device context from an object or cached identifier."""
        if isinstance(device, DeviceContext):
            self._devices_by_id[device.device_id] = device
            return device
        try:
            return self._devices_by_id[device]
        except KeyError as err:
            message = "No cached device context; fetch devices before status requests"
            raise AnonaApiError(message) from err

    def _resolve_device_id(self, device: DeviceContext | str) -> str:
        """Resolve a device identifier from a context object or string."""
        if isinstance(device, DeviceContext):
            self._devices_by_id[device.device_id] = device
            return device.device_id
        return device


def hash_password(password: str) -> str:
    """Hash a password with the app's discovered static salt."""
    return _md5_hex(f"{password}{PASSWORD_SIGN_SALT}")


def _md5_hex(value: str) -> str:
    """Return the lowercase MD5 hex digest for a string value."""
    # The upstream Anona mobile API requires MD5 for login and request signatures.

    # codeql[py/weak-sensitive-data-hashing]
    return hashlib.md5(
        value.encode(),
        usedforsecurity=False,
    ).hexdigest()


def build_login_signature(
    *,
    email: str,
    password_hash: str,
    ts: int,
    mobile: str | None = None,
    device_type: int = APP_DEVICE_TYPE,
) -> str:
    """Return the login signature used by the mobile app."""
    mobile_component = mobile or "null"
    need_sign = f"{device_type}{email}{mobile_component}{password_hash}"
    return _md5_hex(f"{need_sign}{ts}{PASSWORD_SIGN_SALT}")


def build_authenticated_signature(
    *,
    token: str,
    client_uuid: str,
    channel: int,
    ts: int,
) -> str:
    """Return the shared authenticated-request signature."""
    need_sign = f"{token}{client_uuid}{channel}"
    return _md5_hex(f"{need_sign}{ts}{PASSWORD_SIGN_SALT}")


def build_command_content(send_id: int, user_id: str | int) -> str:
    """Build the captured protobuf payload for a lock or unlock command."""
    if send_id not in {COMMAND_ID_UNLOCK, COMMAND_ID_LOCK}:
        message = f"Unsupported websocket sendID {send_id}"
        raise AnonaApiError(message)
    user_id_int = _coerce_int(user_id)
    if user_id_int is None:
        message = "Expected websocket user_id to be an integer-compatible value"
        raise AnonaApiError(message)
    payload = b"".join(
        (
            _encode_protobuf_varint_field(1, STATUS_SMART_TYPE),
            _encode_protobuf_varint_field(2, send_id),
            _encode_protobuf_length_delimited_field(
                50,
                _encode_protobuf_length_delimited_field(
                    5,
                    _encode_protobuf_varint_field(1, user_id_int),
                ),
            ),
        )
    )
    return payload.hex().upper()


def build_websocket_handshake_payload(handshake_token: str) -> dict[str, Any]:
    """Build the plaintext websocket handshake payload."""
    timestamp_ms = time.time_ns() // 1_000_000
    return {
        "operateId": str(timestamp_ms),
        "ts": timestamp_ms,
        "handshakeToken": handshake_token,
    }


def build_websocket_operation() -> dict[str, Any]:
    """Build the timestamp fields used by a websocket command."""
    timestamp_ns = time.time_ns()
    return {
        "operateId": str(timestamp_ns // 1_000),
        "ts": timestamp_ns // 1_000_000,
    }


def build_websocket_command_payload(
    *,
    device: DeviceContext,
    content: str,
    operate_id: str,
    ts: int,
    target: int,
) -> dict[str, Any]:
    """Build the JSON payload that is AES-encrypted for device commands."""
    return {
        "content": content,
        "deviceId": device.device_id,
        # The websocket transport identifies the mobile client, not the lock family.
        "deviceType": APP_DEVICE_TYPE,
        "operateId": operate_id,
        "target": target,
        "ts": ts,
    }


def serialize_websocket_payload(payload: Mapping[str, Any]) -> str:
    """Serialize a websocket payload with the app's compact JSON style."""
    return json.dumps(payload, separators=(",", ":"))


def encrypt_websocket_payload(
    payload: Mapping[str, Any],
    websocket_aes_key: str,
) -> str:
    """AES-CBC encrypt a websocket payload and add the app's CRC32 suffix."""
    key = _decode_websocket_aes_key(websocket_aes_key)
    padder = PKCS7(AES_BLOCK_SIZE_BITS).padder()
    plaintext = serialize_websocket_payload(payload).encode()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(_websocket_aes_iv())).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    secure_frame = _append_websocket_crc(ciphertext)
    return secure_frame.hex().upper()


def decrypt_websocket_payload(
    ciphertext_hex: str,
    websocket_aes_key: str,
) -> dict[str, Any]:
    """Decrypt a CRC32-suffixed websocket payload encoded as hexadecimal text."""
    key = _decode_websocket_aes_key(websocket_aes_key)
    try:
        secure_frame = bytes.fromhex(ciphertext_hex)
    except ValueError as err:
        message = "Websocket payload was not valid hexadecimal"
        raise AnonaApiError(message) from err
    ciphertext = _strip_websocket_crc(secure_frame)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(_websocket_aes_iv())).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = PKCS7(AES_BLOCK_SIZE_BITS).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    try:
        payload = json.loads(plaintext.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        message = "Decrypted websocket payload was not valid JSON"
        raise AnonaApiError(message) from err
    return _require_mapping(payload, "websocket payload")


def decode_websocket_message(
    payload_text: str,
    *,
    websocket_aes_key: str | None,
) -> WebsocketMessage:
    """Decode a websocket text frame into the normalized message model."""
    stripped = payload_text.strip()
    if stripped.startswith("{"):
        try:
            direct_payload = json.loads(stripped)
        except json.JSONDecodeError as err:
            message = "Websocket payload was not valid JSON"
            raise AnonaApiError(message) from err
        payload = _require_mapping(direct_payload, "websocket payload")
    else:
        if websocket_aes_key is None:
            message = "Encrypted websocket payload received before an AES key was set"
            raise AnonaApiError(message)
        payload = decrypt_websocket_payload(stripped, websocket_aes_key)
    return normalize_websocket_message(payload)


def normalize_websocket_message(payload: Mapping[str, Any]) -> WebsocketMessage:
    """Normalize a websocket JSON payload into the typed message model."""
    return WebsocketMessage(
        operate_id=_coerce_string(payload.get("operateId")),
        ts=_coerce_int(payload.get("ts")),
        device_id=_coerce_string(payload.get("deviceId")),
        source=_coerce_int(payload.get("source")),
        target=_coerce_int(payload.get("target")),
        content=_coerce_string(payload.get("content")),
        ack_code=_coerce_int(payload.get("ackCode")),
        is_ack=bool(payload.get("isAck")),
        raw=dict(payload),
    )


def decode_response_envelope(text: str) -> dict[str, Any]:
    """Decode either the base64-wrapped envelope or a plain JSON error payload."""
    stripped_text = text.strip()
    try:
        direct_payload = json.loads(stripped_text)
    except json.JSONDecodeError:
        direct_payload = None

    if isinstance(direct_payload, str):
        return _decode_base64_json(direct_payload)
    if isinstance(direct_payload, Mapping):
        return dict(direct_payload)
    return _decode_base64_json(stripped_text)


def normalize_home_context(
    payload: Mapping[str, Any],
    default_home_id: str | None = None,
) -> HomeContext:
    """Normalize a raw home payload into a typed context."""
    home_id = _require_string(payload.get("homeId"), "homeId")
    return HomeContext(
        home_id=home_id,
        name=_require_string(payload.get("homeName"), "homeName"),
        is_default=home_id == default_home_id,
        raw=dict(payload),
    )


def normalize_device_context(payload: Mapping[str, Any]) -> DeviceContext:
    """Normalize a raw device payload into a typed context."""
    return DeviceContext(
        device_id=_require_string(payload.get("deviceId"), "deviceId"),
        device_type=_require_int(
            payload.get("type") or payload.get("deviceType"), "device type"
        ),
        device_module=_require_int(
            payload.get("module") or payload.get("deviceModule"), "device module"
        ),
        device_channel=_require_int(
            payload.get("channel") or payload.get("deviceChannel"), "device channel"
        ),
        nickname=_require_string(
            payload.get("deviceNickName") or payload.get("deviceName"),
            "device nickname",
        ),
        serial_number=_coerce_string(payload.get("sn")),
        model=_coerce_string(payload.get("model")),
        raw=dict(payload),
    )


def normalize_device_info_context(payload: Mapping[str, Any]) -> DeviceInfoContext:
    """Normalize a raw getDeviceInfo payload into a typed context."""
    device_id = _require_string(payload.get("deviceId"), "deviceId")
    silent_ota_time_raw = _coerce_string(payload.get("silentOTATime"))
    return DeviceInfoContext(
        device_id=device_id,
        device_type=_coerce_int(payload.get("type") or payload.get("deviceType")),
        device_module=_coerce_int(payload.get("module") or payload.get("deviceModule")),
        device_channel=_coerce_int(
            payload.get("channel") or payload.get("deviceChannel")
        ),
        firmware_version=_coerce_string(
            payload.get("softwareVersionNumber")
            or payload.get("versionNum")
            or payload.get("deviceVersionNum")
        ),
        firmware_sub_version=_coerce_string(payload.get("softwareSubVersion")),
        ip_address=_coerce_string(payload.get("ip")),
        wifi_ap_ssid=_coerce_string(
            payload.get("wifiApSsid") or payload.get("wifiName")
        ),
        wifi_mac=_coerce_string(payload.get("wifiMac") or payload.get("mac")),
        bt_mac=_coerce_string(payload.get("btMac")),
        timezone_id=_coerce_string(payload.get("timezoneId")),
        silent_ota_enabled=_coerce_bool(payload.get("silentOTA")),
        silent_ota_time=deserialize_silent_ota_time_window(silent_ota_time_raw),
        silent_ota_time_raw=silent_ota_time_raw,
        last_online_ts=_coerce_int(payload.get("lastOnlineTs")),
        raw=dict(payload),
    )


def normalize_device_switch_settings(
    payload: Mapping[str, Any],
    *,
    device_id: str | None = None,
) -> DeviceSwitchSettings:
    """Normalize a raw switch payload into typed notification switches."""
    resolved_device_id = device_id or _coerce_string(payload.get("deviceId"))
    if resolved_device_id is None:
        message = "Expected device switch payload to include deviceId"
        raise AnonaApiError(message)
    return DeviceSwitchSettings(
        device_id=resolved_device_id,
        main_switch=bool(_coerce_bool(payload.get("mainSwitch"))),
        ugent_notify_switch=bool(_coerce_bool(payload.get("ugentNotifySwitch"))),
        important_notify_switch=bool(
            _coerce_bool(payload.get("importantNotifySwitch"))
        ),
        normal_notify_switch=bool(_coerce_bool(payload.get("normalNotifySwitch"))),
        raw=dict(payload),
    )


def normalize_firmware_update_context(
    payload: Mapping[str, Any],
    *,
    device_id: str,
    installed_version: str | None,
) -> FirmwareUpdateContext:
    """Normalize a firmware update payload into a typed context."""
    latest_version = _coerce_string(
        payload.get("version")
        or payload.get("newVerNum")
        or payload.get("targetVersionNum")
    )
    resolved_installed_version = (
        _coerce_string(payload.get("deviceVersionNum"))
        or _coerce_string(payload.get("versionNum"))
        or installed_version
    )
    return FirmwareUpdateContext(
        device_id=device_id,
        installed_version=resolved_installed_version,
        latest_version=latest_version,
        latest_sub_version=_coerce_string(payload.get("subVersion")),
        new_version=_coerce_bool(payload.get("newVersion")),
        version_order=_coerce_int(payload.get("versionOrder")),
        release_notes=_coerce_string(
            payload.get("desc") or payload.get("newVersionDesc")
        ),
        release_url=_coerce_string(
            payload.get("fileUrl") or payload.get("newVersionUrl")
        ),
        release_ts=_coerce_int(payload.get("releaseTime")),
        file_md5=_coerce_string(payload.get("fileMd5")),
        file_size=_coerce_int(payload.get("fileSize")),
        is_forced=_coerce_bool(payload.get("forced")),
        raw=dict(payload),
    )


def is_firmware_update_available(
    installed_version: str | None,
    latest_version: str | None,
    *,
    new_version: bool | None,
) -> bool:
    """Determine whether firmware update metadata indicates an available update."""
    if installed_version and latest_version:
        comparison = compare_versions(latest_version, installed_version)
        if comparison is not None:
            return comparison > 0
        return bool(new_version and latest_version != installed_version)
    return bool(new_version)


def compare_versions(left: str, right: str) -> int | None:
    """Compare two dotted-ish version strings, returning -1/0/1 when comparable."""
    left_parts = _normalize_version_parts(left)
    right_parts = _normalize_version_parts(right)
    if left_parts is None or right_parts is None:
        return None

    max_len = max(len(left_parts), len(right_parts))
    padded_left = left_parts + [(0, 0)] * (max_len - len(left_parts))
    padded_right = right_parts + [(0, 0)] * (max_len - len(right_parts))
    for left_part, right_part in zip(padded_left, padded_right, strict=False):
        if left_part == right_part:
            continue
        if left_part > right_part:
            return 1
        return -1
    return 0


def deserialize_silent_ota_time_window(value: str | None) -> str | None:
    """Normalize a silent OTA window string into `HH:MM-HH:MM` when possible."""
    if value is None:
        return None
    matched_window = SILENT_OTA_WINDOW_PATTERN.fullmatch(value.strip())
    if matched_window:
        begin_hour = int(matched_window.group("begin_hour"))
        begin_minute = int(matched_window.group("begin_minute"))
        end_hour = int(matched_window.group("end_hour"))
        end_minute = int(matched_window.group("end_minute"))
        return _format_silent_ota_window(
            begin_hour,
            begin_minute,
            end_hour,
            end_minute,
        )

    mapping = _decode_json_mapping(value)
    if mapping is None:
        return None
    begin_hour = _coerce_int(mapping.get("beginHour"))
    begin_minute = _coerce_int(mapping.get("beginMinute"))
    end_hour = _coerce_int(mapping.get("endHour"))
    end_minute = _coerce_int(mapping.get("endMinute"))
    if (
        begin_hour is None
        or begin_minute is None
        or end_hour is None
        or end_minute is None
    ):
        return None
    return _format_silent_ota_window(
        begin_hour=begin_hour,
        begin_minute=begin_minute,
        end_hour=end_hour,
        end_minute=end_minute,
    )


def serialize_silent_ota_time_window(value: str) -> str:
    """Serialize a silent OTA window value into the app's JSON string format."""
    normalized_window = deserialize_silent_ota_time_window(value)
    if normalized_window is None:
        message = f"Invalid silent OTA time window {value!r}"
        raise AnonaApiError(message)
    matched_window = SILENT_OTA_WINDOW_PATTERN.fullmatch(normalized_window)
    if matched_window is None:
        message = f"Invalid normalized silent OTA time window {normalized_window!r}"
        raise AnonaApiError(message)
    begin_hour = int(matched_window.group("begin_hour"))
    begin_minute = int(matched_window.group("begin_minute"))
    end_hour = int(matched_window.group("end_hour"))
    end_minute = int(matched_window.group("end_minute"))
    return json.dumps(
        {
            "beginHour": begin_hour,
            "beginMinute": begin_minute,
            "endHour": end_hour,
            "endMinute": end_minute,
        },
        separators=(",", ":"),
    )


def select_home_id(homes: list[HomeContext]) -> str | None:
    """Choose the default home or the first visible home."""
    for home in homes:
        if home.is_default:
            return home.home_id
    if homes:
        return homes[0].home_id
    return None


def parse_lock_status(
    data_hex_str: str,
    *,
    refresh_ts: int | None = None,
    start_type: int | None = None,
) -> LockStatus:
    """Decode the captured lock protobuf payload into a smaller status model."""
    raw_bytes = bytes.fromhex(data_hex_str)
    raw_fields = _decode_protobuf_message(raw_bytes)
    lock_status_code = _nested_int(raw_fields, "1")
    battery_capacity = _nested_int(raw_fields, "3", "1", "1")
    door_state_code = _nested_int(raw_fields, "2")
    door_status_code = _nested_int(raw_fields, "4")
    has_locking_fail = _optional_bool(_nested_int(raw_fields, "5"))
    has_door_been_open_long_time = _optional_bool(_nested_int(raw_fields, "6"))
    long_endurance_mode_status_code = _nested_int(raw_fields, "12", "1")
    keypad_connection_status_code = _nested_int(raw_fields, "15", "1")
    keypad_battery_capacity = _nested_int(raw_fields, "14", "2")
    keypad_status_code = _nested_int(raw_fields, "17", "1")
    sound_volume_code = _nested_int(raw_fields, "10", "1")
    auto_lock_enabled = _optional_bool(_nested_int(raw_fields, "11", "1"))
    auto_lock_delay_seconds = _nested_int(raw_fields, "11", "2")
    low_power_mode_enabled = _optional_bool(long_endurance_mode_status_code)

    locked: bool | None = None
    if lock_status_code == 1:
        locked = True
    elif lock_status_code in {0, 2}:
        locked = False

    return LockStatus(
        locked=locked,
        lock_status_code=lock_status_code,
        battery_capacity=battery_capacity,
        battery_voltage=None,
        charge_status_code=None,
        door_state_code=door_state_code,
        door_status_code=door_status_code,
        has_locking_fail=has_locking_fail,
        has_door_been_open_long_time=has_door_been_open_long_time,
        calibration_status_code=None,
        long_endurance_mode_status_code=long_endurance_mode_status_code,
        keypad_connection_status_code=keypad_connection_status_code,
        keypad_battery_capacity=keypad_battery_capacity,
        keypad_status_code=keypad_status_code,
        data_hex_str=data_hex_str,
        refresh_ts=refresh_ts,
        start_type=start_type,
        raw_fields=raw_fields,
        auto_lock_enabled=auto_lock_enabled,
        auto_lock_delay_seconds=auto_lock_delay_seconds,
        auto_lock_delay_label=describe_auto_lock_delay(auto_lock_delay_seconds),
        sound_volume_code=sound_volume_code,
        sound_volume=describe_sound_volume(sound_volume_code),
        low_power_mode_enabled=low_power_mode_enabled,
    )


def describe_auto_lock_delay(value: int | None) -> str | None:
    """Return a human-readable auto-lock delay label for a raw seconds value."""
    if value is None:
        return None
    return AUTO_LOCK_DELAY_LABELS.get(value, f"{value} seconds")


def describe_sound_volume(code: int | None) -> str | None:
    """Return a human-readable sound volume label for a raw enum code."""
    if code is None:
        return None
    return SOUND_VOLUME_LABELS.get(code)


def _decode_base64_json(base64_text: str) -> dict[str, Any]:
    """Decode a base64 string containing a JSON document."""
    padding = "=" * (-len(base64_text) % 4)
    try:
        decoded_bytes = base64.b64decode(f"{base64_text}{padding}", validate=True)
    except binascii.Error as err:
        message = "Response body was neither JSON nor base64 JSON"
        raise AnonaApiError(message) from err

    try:
        decoded_payload = json.loads(decoded_bytes.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        message = "Decoded response body was not valid JSON"
        raise AnonaApiError(message) from err

    if not isinstance(decoded_payload, Mapping):
        message = "Decoded response body was not a JSON object"
        raise AnonaApiError(message)
    return dict(decoded_payload)


def _decode_protobuf_message(raw_bytes: bytes) -> dict[str, DecodedProtoValue]:
    """Decode a minimal protobuf-wire message into nested Python structures."""
    fields: dict[str, DecodedProtoValue] = {}
    offset = 0
    while offset < len(raw_bytes):
        key, offset = _read_varint(raw_bytes, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        field_key = str(field_number)
        if wire_type == PROTOBUF_WIRE_VARINT:
            value, offset = _read_varint(raw_bytes, offset)
            _merge_proto_value(fields, field_key, value)
            continue
        if wire_type == PROTOBUF_WIRE_LENGTH_DELIMITED:
            length, offset = _read_varint(raw_bytes, offset)
            chunk = raw_bytes[offset : offset + length]
            offset += length
            if len(chunk) != length:
                message = "Truncated protobuf length-delimited field"
                raise AnonaApiError(message)
            nested_value: DecodedProtoValue
            try:
                nested_value = _decode_protobuf_message(chunk)
            except AnonaApiError:
                nested_value = list(chunk)
            _merge_proto_value(fields, field_key, nested_value)
            continue
        message = f"Unsupported protobuf wire type: {wire_type}"
        raise AnonaApiError(message)
    return fields


def _encode_protobuf_varint(value: int) -> bytes:
    """Encode an integer using protobuf varint encoding."""
    encoded = bytearray()
    remaining = value
    while remaining > PROTOBUF_VARINT_MASK:
        encoded.append((remaining & PROTOBUF_VARINT_MASK) | 0x80)
        remaining >>= 7
    encoded.append(remaining)
    return bytes(encoded)


def _encode_protobuf_varint_field(field_number: int, value: int) -> bytes:
    """Encode a protobuf varint field."""
    key = (field_number << 3) | PROTOBUF_WIRE_VARINT
    return _encode_protobuf_varint(key) + _encode_protobuf_varint(value)


def _encode_protobuf_length_delimited_field(field_number: int, chunk: bytes) -> bytes:
    """Encode a protobuf length-delimited field."""
    key = (field_number << 3) | PROTOBUF_WIRE_LENGTH_DELIMITED
    return _encode_protobuf_varint(key) + _encode_protobuf_varint(len(chunk)) + chunk


def _read_varint(raw_bytes: bytes, offset: int) -> tuple[int, int]:
    """Read a protobuf varint from a byte buffer."""
    value = 0
    shift = 0
    position = offset
    while position < len(raw_bytes):
        byte = raw_bytes[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, position
        shift += 7
    message = "Unterminated protobuf varint"
    raise AnonaApiError(message)


def _merge_proto_value(
    fields: dict[str, DecodedProtoValue],
    key: str,
    value: DecodedProtoValue,
) -> None:
    """Merge a decoded protobuf field into the output mapping."""
    existing = fields.get(key)
    if existing is None:
        fields[key] = value
        return
    if isinstance(existing, list):
        existing.append(value)
        return
    fields[key] = [existing, value]


def _nested_int(
    value: Mapping[str, DecodedProtoValue] | DecodedProtoValue | None,
    *path: str,
) -> int | None:
    """Traverse a decoded protobuf mapping and return an integer when present."""
    current: Mapping[str, DecodedProtoValue] | DecodedProtoValue | None = value
    for segment in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(segment)
    if isinstance(current, list):
        current = current[0] if current else None
    if isinstance(current, int):
        return current
    return None


def _optional_bool(value: int | None) -> bool | None:
    """Convert a numeric flag into a boolean while preserving unknown values."""
    if value is None:
        return None
    return bool(value)


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    """Return a mapping value when possible."""
    if isinstance(value, Mapping):
        return value
    return None


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    """Return a mapping or raise a descriptive API error."""
    if not isinstance(value, Mapping):
        message = f"Expected {label} to be an object"
        raise AnonaApiError(message)
    return dict(value)


def _require_int(value: Any, label: str) -> int:
    """Return an integer or raise a descriptive API error."""
    coerced = _coerce_int(value)
    if coerced is None:
        message = f"Expected {label} to be an integer"
        raise AnonaApiError(message)
    return coerced


def _require_string(value: Any, label: str) -> str:
    """Return a string or raise a descriptive API error."""
    coerced = _coerce_string(value)
    if coerced is None:
        message = f"Expected {label} to be a string"
        raise AnonaApiError(message)
    return coerced


def _coerce_int(value: Any) -> int | None:
    """Coerce an arbitrary scalar into an integer when possible."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any) -> bool | None:
    """Coerce a scalar into a boolean when possible."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _coerce_string(value: Any) -> str | None:
    """Coerce an arbitrary scalar into a string when possible."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return None


def _decode_json_mapping(value: str) -> Mapping[str, Any] | None:
    """Parse a JSON object string and return it as a mapping when valid."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    return parsed


def _format_silent_ota_window(
    begin_hour: int,
    begin_minute: int,
    end_hour: int,
    end_minute: int,
) -> str:
    """Format and validate a silent OTA time window."""
    if not (
        0 <= begin_hour <= SILENT_OTA_MAX_HOUR and 0 <= end_hour <= SILENT_OTA_MAX_HOUR
    ):
        message = "Silent OTA hour must be in 0..23"
        raise AnonaApiError(message)
    if not (
        0 <= begin_minute <= SILENT_OTA_MAX_MINUTE
        and 0 <= end_minute <= SILENT_OTA_MAX_MINUTE
    ):
        message = "Silent OTA minute must be in 0..59"
        raise AnonaApiError(message)
    return f"{begin_hour:02d}:{begin_minute:02d}-{end_hour:02d}:{end_minute:02d}"


def _normalize_version_parts(version: str) -> list[tuple[int, int | str]] | None:
    """Normalize a version string into comparable numeric/string parts."""
    stripped = version.strip()
    if not stripped:
        return None
    tokens = VERSION_TOKEN_PATTERN.findall(stripped)
    if not tokens:
        return None

    normalized: list[tuple[int, int | str]] = []
    for token in tokens:
        if token.isdigit():
            normalized.append((0, int(token)))
            continue
        normalized.append((1, token.lower()))
    return normalized


def _decode_websocket_aes_key(websocket_aes_key: str) -> bytes:
    """Decode and validate the websocket AES session key."""
    try:
        key = bytes.fromhex(websocket_aes_key)
    except ValueError as err:
        message = "Websocket AES key was not valid hexadecimal"
        raise AnonaApiError(message) from err
    if len(key) != WEBSOCKET_AES_KEY_LENGTH:
        message = "Websocket AES key must decode to 16 bytes"
        raise AnonaApiError(message)
    return key


def _websocket_aes_iv() -> bytes:
    """Return the fixed IV used by the captured websocket protocol."""
    return bytes(range(16))


def _append_websocket_crc(ciphertext: bytes) -> bytes:
    """Append the app's little-endian CRC32 suffix to an AES ciphertext."""
    crc32 = zlib.crc32(ciphertext) & 0xFFFFFFFF
    return ciphertext + crc32.to_bytes(WEBSOCKET_FRAME_CRC_SIZE_BYTES, "little")


def _strip_websocket_crc(secure_frame: bytes) -> bytes:
    """Validate and remove the CRC32 suffix from a secure websocket frame."""
    if len(secure_frame) <= WEBSOCKET_FRAME_CRC_SIZE_BYTES:
        message = "Encrypted websocket payload was too short"
        raise AnonaApiError(message)
    ciphertext = secure_frame[:-WEBSOCKET_FRAME_CRC_SIZE_BYTES]
    if len(ciphertext) % AES_BLOCK_SIZE_BYTES != 0:
        message = "Encrypted websocket payload length was invalid"
        raise AnonaApiError(message)
    expected_crc = zlib.crc32(ciphertext) & 0xFFFFFFFF
    actual_crc = int.from_bytes(
        secure_frame[-WEBSOCKET_FRAME_CRC_SIZE_BYTES:],
        "little",
    )
    if actual_crc != expected_crc:
        message = "Encrypted websocket payload CRC32 suffix was invalid"
        raise AnonaApiError(message)
    return ciphertext
