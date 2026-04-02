"""Anona Security API client aligned with the captured mobile app traffic."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .const import (
    API_BASE_URL,
    APP_CHANNEL,
    APP_DEVICE_TYPE,
    DEFAULT_LANG,
    ENDPOINT_DEVICE_CERTS,
    ENDPOINT_DEVICE_INFO,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_DEVICE_ONLINE,
    ENDPOINT_DEVICE_STATUS,
    ENDPOINT_GET_TS,
    ENDPOINT_HOME_LIST,
    ENDPOINT_LOGIN,
    ENDPOINT_WEBSOCKET_ADDRESS,
    PASSWORD_SIGN_SALT,
    STATUS_SMART_TYPE,
)

if TYPE_CHECKING:
    import aiohttp

_LOGGER = logging.getLogger(__name__)
HTTP_STATUS_OK = 200
PROTOBUF_WIRE_VARINT = 0
PROTOBUF_WIRE_LENGTH_DELIMITED = 2

type DecodedProtoValue = int | dict[str, DecodedProtoValue] | list[DecodedProtoValue]


class AnonaApiError(Exception):
    """Base exception for Anona API failures."""


class AnonaAuthError(AnonaApiError):
    """Raised when authentication fails."""


class AnonaSignatureError(AnonaApiError):
    """Raised when a request signature cannot be produced or is rejected."""


class AnonaUnsupportedCommandError(AnonaApiError):
    """Raised when lock control remains blocked by missing protocol evidence."""


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


class UnavailableSignatureProvider:
    """Signature provider that documents the unresolved signer blocker."""

    async def async_get_signature(self, request: SignedRequest) -> str:
        """Raise the current signer blocker with concrete guidance."""
        lookup_key = build_signature_lookup_key(
            request.ts, request.uuid, request.channel
        )
        migration_key = None
        if request.token:
            migration_key = build_signature_migration_key(request.ts, request.token)
        raise AnonaSignatureError(
            "Anona request signing is still blocked. The app reads signatures from "
            f"a cache keyed by {lookup_key!r}"
            + (
                f" with migration fallback {migration_key!r}."
                if migration_key is not None
                else "."
            )
            + " Capture the native requestSign producer before attempting live auth."
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
        self._signature_provider = signature_provider or UnavailableSignatureProvider()
        self._devices_by_id: dict[str, DeviceContext] = {}

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
        result = await self._post_enveloped(ENDPOINT_GET_TS)
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
            "Decoded lock status for %s from dataHexStr=%s into %s",
            device_context.device_id,
            data_hex_str,
            status.raw_fields,
        )
        return status

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
        """Block the lock command until websocket frames are captured."""
        await self.get_device_certs_for_owner(device)
        await self.get_websocket_address()
        message = (
            "Lock and unlock remain blocked until a capture includes "
            "websocket authSync, "
            "lockDoor, and unLockDoor frames."
        )
        raise AnonaUnsupportedCommandError(message)

    async def unlock(self, device: DeviceContext | str) -> None:
        """Block the unlock command until websocket frames are captured."""
        await self.lock(device)

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

        async with self._session.post(
            f"{self._base_url}{endpoint}",
            **request_kwargs,
        ) as response:
            if response.status != HTTP_STATUS_OK:
                message = f"HTTP {response.status} from {endpoint}"
                raise AnonaApiError(message)
            body_text = await response.text()

        envelope = decode_response_envelope(body_text)
        error_code = _coerce_int(envelope.get("errorCode")) or 0
        error_message = _coerce_string(envelope.get("errorMessage")) or "unknown error"
        if envelope.get("error") or error_code != 0:
            lowered_message = error_message.lower()
            if "sig" in lowered_message:
                raise AnonaSignatureError(error_message)
            if endpoint == ENDPOINT_LOGIN:
                raise AnonaAuthError(error_message)
            message = f"API error {error_code}: {error_message}"
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
            message = (
                "No cached device context for "
                f"{device}; fetch devices before status requests"
            )
            raise AnonaApiError(message) from err


def hash_password(password: str) -> str:
    """Hash a password with the app's discovered static salt."""
    salted_password = f"{password}{PASSWORD_SIGN_SALT}".encode()
    return hashlib.md5(salted_password, usedforsecurity=False).hexdigest()


def build_signature_lookup_key(ts: int, client_uuid: str, channel: int) -> str:
    """Return the MD5 key used by the app's signature cache."""
    key_source = f"{ts}_{client_uuid.lower()}_{channel}".encode()
    return hashlib.md5(key_source, usedforsecurity=False).hexdigest()


def build_signature_migration_key(ts: int, token: str) -> str:
    """Return the temporary migration key used by the app's signer cache."""
    return f"{ts}_{token}"


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
    charge_status_code = _nested_int(raw_fields, "11", "1")
    battery_voltage = _nested_int(raw_fields, "11", "2")
    door_state_code = _nested_int(raw_fields, "2")
    door_status_code = _nested_int(raw_fields, "4")
    has_locking_fail = _optional_bool(_nested_int(raw_fields, "5"))
    has_door_been_open_long_time = _optional_bool(_nested_int(raw_fields, "6"))
    calibration_status_code = _nested_int(raw_fields, "10", "1")
    long_endurance_mode_status_code = _nested_int(raw_fields, "12", "1")
    keypad_connection_status_code = _nested_int(raw_fields, "15", "1")
    keypad_battery_capacity = _nested_int(raw_fields, "14", "2")
    keypad_status_code = _nested_int(raw_fields, "17", "1")

    locked: bool | None = None
    if lock_status_code == 1:
        locked = True
    elif lock_status_code in {0, 2}:
        locked = False

    return LockStatus(
        locked=locked,
        lock_status_code=lock_status_code,
        battery_capacity=battery_capacity,
        battery_voltage=battery_voltage,
        charge_status_code=charge_status_code,
        door_state_code=door_state_code,
        door_status_code=door_status_code,
        has_locking_fail=has_locking_fail,
        has_door_been_open_long_time=has_door_been_open_long_time,
        calibration_status_code=calibration_status_code,
        long_endurance_mode_status_code=long_endurance_mode_status_code,
        keypad_connection_status_code=keypad_connection_status_code,
        keypad_battery_capacity=keypad_battery_capacity,
        keypad_status_code=keypad_status_code,
        data_hex_str=data_hex_str,
        refresh_ts=refresh_ts,
        start_type=start_type,
        raw_fields=raw_fields,
    )


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


def _coerce_string(value: Any) -> str | None:
    """Coerce an arbitrary scalar into a string when possible."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return None
