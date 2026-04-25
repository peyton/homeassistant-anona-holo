"""Tests for the captured Anona API helpers and client."""

# ruff: noqa: S101, S105, PLR2004, SLF001

from __future__ import annotations

import asyncio
import base64
import json
import logging
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

from aiohttp import WSMsgType

import custom_components.anona_holo.api as api_module
from custom_components.anona_holo.api import (
    AnonaApi,
    DeviceInfoContext,
    WebsocketMessage,
    build_authenticated_signature,
    build_command_content,
    build_login_signature,
    build_websocket_command_payload,
    decode_response_envelope,
    decode_websocket_message,
    deserialize_silent_ota_time_window,
    encrypt_websocket_payload,
    hash_password,
    is_firmware_update_available,
    normalize_device_context,
    normalize_device_info_context,
    normalize_device_switch_settings,
    normalize_firmware_update_context,
    parse_lock_status,
)
from custom_components.anona_holo.const import (
    APP_CHANNEL,
    APP_DEVICE_TYPE,
    COMMAND_ID_LOCK,
    COMMAND_ID_UNLOCK,
    DEFAULT_LANG,
    STATUS_SMART_TYPE,
)

if TYPE_CHECKING:
    import pytest

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "anona_capture.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text())


@dataclass(slots=True)
class _FakeResponse:
    """Minimal aiohttp-like response for the API tests."""

    body_text: str
    status: int = 200

    async def __aenter__(self) -> Self:
        """Enter the async response context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        """Exit the async response context manager."""
        return False

    async def text(self) -> str:
        """Return the canned body text."""
        return self.body_text


class _FakeSession:
    """Minimal session object that records POST calls."""

    def __init__(
        self,
        responses: list[_FakeResponse],
        *,
        websockets: list[_FakeWebsocket] | None = None,
    ) -> None:
        """Initialize the fake session with a response queue."""
        self._responses = responses
        self._websockets = websockets or []
        self.requests: list[dict[str, Any]] = []
        self.websocket_requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        """Record the request and return the next canned response."""
        self.requests.append({"url": url, **kwargs})
        return self._responses.pop(0)

    def ws_connect(self, url: str, **kwargs: Any) -> _FakeWebsocket:
        """Record a websocket connection and return the next canned socket."""
        self.websocket_requests.append({"url": url, **kwargs})
        return self._websockets.pop(0)


class _FakeWebsocket:
    """Minimal websocket object that records sent frames and replays responses."""

    def __init__(self, messages: list[Any]) -> None:
        """Initialize the fake websocket with a message queue."""
        self._messages = messages
        self.sent: list[str] = []

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        """Exit the async context manager."""
        return False

    async def send_str(self, data: str) -> None:
        """Record an outbound websocket text frame."""
        self.sent.append(data)

    async def receive(self) -> Any:
        """Return the next canned websocket message."""
        return self._messages.pop(0)

    def exception(self) -> None:
        """Match aiohttp's websocket error access API."""
        return


@dataclass(slots=True)
class _FakeWsMessage:
    """Minimal websocket frame shape used by the websocket command tests."""

    type: WSMsgType
    data: Any


def _ws_text(payload: str) -> _FakeWsMessage:
    """Create a text websocket frame for the fake websocket."""
    return _FakeWsMessage(type=WSMsgType.TEXT, data=payload)


def _encode_success(result_body_object: Any) -> str:
    """Encode a successful response envelope as base64 JSON."""
    payload = {
        "resultBodyObject": result_body_object,
        "error": False,
        "errorMessage": None,
        "errorCode": 0,
    }
    return base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()


def _make_api(
    responses: list[_FakeResponse],
    *,
    authed: bool = False,
    home_id: str | None = None,
    websockets: list[_FakeWebsocket] | None = None,
) -> tuple[AnonaApi, _FakeSession]:
    """Build an API client backed by the fake session."""
    session = _FakeSession(responses, websockets=websockets)
    api = AnonaApi(
        cast("Any", session),
        client_uuid=FIXTURE["signature_fixture"]["client_uuid"],
        home_id=home_id,
    )
    if authed:
        api._token = FIXTURE["login"]["response_object"]["token"]
        api._user_id = str(FIXTURE["login"]["response_object"]["userID"])
    return api, session


def test_decode_response_envelope_from_base64_fixture() -> None:
    """Base64-wrapped response envelopes should decode into JSON objects."""
    response_text = _encode_success(FIXTURE["homes"]["response_object"])

    decoded = decode_response_envelope(response_text)

    assert decoded["errorCode"] == 0
    assert decoded["resultBodyObject"]["defaultHome"]["homeId"] == "home-123"


def test_decode_response_envelope_from_plain_json_error() -> None:
    """Plain JSON error responses should decode without base64 handling."""
    response_text = json.dumps(FIXTURE["plain_error_response"])

    decoded = decode_response_envelope(response_text)

    assert decoded == FIXTURE["plain_error_response"]


def test_hash_password_uses_the_discovered_app_salt() -> None:
    """Password hashing should match the salted MD5 observed in the app binary."""
    assert (
        hash_password(FIXTURE["login"]["password"])
        == "0f76460c2c07b1e47b2f20787e9cbaf3"
    )


def test_signature_helpers_match_the_verified_signer_inputs() -> None:
    """Signature helpers should match the sanitized fixture inputs."""
    signature_fixture = FIXTURE["signature_fixture"]
    password_hash = hash_password(FIXTURE["login"]["password"])

    assert (
        build_login_signature(
            email=FIXTURE["login"]["email"],
            password_hash=password_hash,
            ts=signature_fixture["ts"],
        )
        == signature_fixture["login_sig"]
    )
    assert (
        build_authenticated_signature(
            token=signature_fixture["token"],
            client_uuid=signature_fixture["client_uuid"],
            channel=signature_fixture["channel"],
            ts=signature_fixture["ts"],
        )
        == signature_fixture["auth_sig"]
    )


def test_login_uses_the_captured_request_shape() -> None:
    """Login should send the captured mobile payload fields and decode the response."""
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["login"]["response_object"])),
        ],
    )

    login_context = asyncio.run(
        api.login(FIXTURE["login"]["email"], FIXTURE["login"]["password"])
    )

    assert login_context.token == "session-token"
    assert login_context.user_id == "533291"
    assert session.requests[0]["url"].endswith("/baseServiceApi/V2/getTs")
    assert session.requests[0]["json"] == {}
    assert session.requests[1]["json"] == {
        "email": FIXTURE["login"]["email"],
        "passWord": hash_password(FIXTURE["login"]["password"]),
        "deviceType": APP_DEVICE_TYPE,
        "lang": DEFAULT_LANG,
        "deviceToken": "",
        "uuid": FIXTURE["signature_fixture"]["client_uuid"],
        "channel": APP_CHANNEL,
        "ts": FIXTURE["server_ts"],
        "sig": FIXTURE["login"]["sig"],
    }


def test_get_homes_normalizes_the_default_home() -> None:
    """Home discovery should normalize the default home and persist its identifier."""
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["homes"]["response_object"])),
        ],
        authed=True,
    )

    homes = asyncio.run(api.get_homes())

    assert len(homes) == 1
    assert homes[0].home_id == "home-123"
    assert homes[0].is_default is True
    assert api.home_id == "home-123"
    assert session.requests[1]["json"] == {
        "uuid": FIXTURE["signature_fixture"]["client_uuid"],
        "channel": APP_CHANNEL,
        "ts": FIXTURE["server_ts"],
        "token": "session-token",
        "sig": FIXTURE["homes"]["sig"],
    }


def test_get_devices_normalizes_device_contexts() -> None:
    """Device discovery should normalize the lock metadata from the fixture."""
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["device_list"]["response_object"])),
        ],
        authed=True,
        home_id="home-123",
    )

    devices = asyncio.run(api.get_devices())

    assert [device.device_id for device in devices] == ["device-123", "device-999"]
    assert devices[0].nickname == "Front Door Lock"
    assert devices[0].device_type == 76
    assert session.requests[1]["json"] == {
        "homeId": "home-123",
        "pageCount": 500,
        "needRelation": True,
        "uuid": FIXTURE["signature_fixture"]["client_uuid"],
        "channel": APP_CHANNEL,
        "ts": FIXTURE["server_ts"],
        "token": "session-token",
        "sig": FIXTURE["device_list"]["sig"],
    }


def test_get_all_devices_aggregates_devices_across_homes() -> None:
    """Device discovery should include every household and avoid duplicate IDs."""
    shared_home_payload = {
        "homeId": "home-999",
        "homeName": "Shared Home",
        "defaultHome": 0,
        "homeType": 1,
        "homeWallpaperName": "https://assets.anonasecurity.com/cover.png",
        "homeWallpaperType": 0,
        "createHomeTimeStamp": 1738618925000,
        "acceptTimeStamp": None,
    }
    homes_response = {
        "userId": 533291,
        "defaultHome": {
            "homeId": "home-123",
            "homeName": "Bay",
            "defaultHome": 0,
            "homeType": 1,
            "homeWallpaperName": "https://assets.anonasecurity.com/anona/img_7.png",
            "homeWallpaperType": 0,
            "createHomeTimeStamp": 1738618925000,
            "acceptTimeStamp": None,
        },
        "actualHomeNameList": [
            {
                "homeId": "home-123",
                "homeName": "Bay",
                "defaultHome": 0,
                "homeType": 1,
                "homeWallpaperName": "https://assets.anonasecurity.com/anona/img_7.png",
                "homeWallpaperType": 0,
                "createHomeTimeStamp": 1738618925000,
                "acceptTimeStamp": None,
            },
            shared_home_payload,
        ],
        "virtualSharedHomeId": "virtual-home-456",
        "virtualSharedHomeDeviceIdList": [],
    }
    shared_device_list = {
        "sig": FIXTURE["device_list"]["sig"],
        "response_object": [
            {
                "type": 76,
                "module": 76001,
                "channel": 76001001,
                "deviceId": "shared-device-001",
                "deviceNickName": "Shared Home Lock",
                "sn": "SHARED-LOCK",
                "model": "SL2001",
            },
        ],
    }

    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(homes_response)),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success([])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(shared_device_list["response_object"])),
        ],
        authed=True,
    )

    devices = asyncio.run(api.get_all_devices())

    assert [device.device_id for device in devices] == ["shared-device-001"]
    assert [
        request["json"]["homeId"]
        for request in session.requests
        if request["url"].endswith("/anona/device/api/getDeviceListByHomeId")
    ] == ["home-123", "home-999"]


def test_integration_discovery_includes_shared_devices_for_member_style_flow() -> None:
    """A login-to-homes-to-all-devices flow should expose shared-home devices."""
    homes_payload = {
        "userId": 533291,
        "defaultHome": {
            "homeId": "home-123",
            "homeName": "ha.anona's Home",
            "defaultHome": 0,
            "homeType": 1,
            "homeWallpaperName": "https://assets.anonasecurity.com/anona/img_7.png",
            "homeWallpaperType": 0,
            "createHomeTimeStamp": 1738618925000,
            "acceptTimeStamp": None,
        },
        "actualHomeNameList": [
            {
                "homeId": "home-123",
                "homeName": "ha.anona's Home",
                "defaultHome": 0,
                "homeType": 1,
                "homeWallpaperName": "https://assets.anonasecurity.com/anona/img_7.png",
                "homeWallpaperType": 0,
                "createHomeTimeStamp": 1738618925000,
                "acceptTimeStamp": None,
            },
            {
                "homeId": "home-999",
                "homeName": "Bay",
                "defaultHome": 0,
                "homeType": 1,
                "homeWallpaperName": "https://assets.anonasecurity.com/anona/img_7.png",
                "homeWallpaperType": 0,
                "createHomeTimeStamp": 1738618925000,
                "acceptTimeStamp": None,
            },
        ],
        "virtualSharedHomeId": "virtual-home-456",
        "virtualSharedHomeDeviceIdList": [],
    }
    shared_device = {
        "type": 76,
        "module": 76001,
        "channel": 76001001,
        "deviceId": "shared-device-001",
        "deviceNickName": "Shared Home Lock",
        "sn": "SHARED-LOCK",
        "model": "SL2001",
    }

    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["login"]["response_object"])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(homes_payload)),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(homes_payload)),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success([])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success([shared_device])),
        ],
        home_id="home-123",
    )

    login_context = asyncio.run(
        api.login(FIXTURE["login"]["email"], FIXTURE["login"]["password"])
    )
    asyncio.run(api.get_homes())
    devices = asyncio.run(api.get_all_devices())

    assert login_context.user_id == "533291"
    assert [device.device_id for device in devices] == ["shared-device-001"]
    assert (
        len(
            [
                req
                for req in session.requests
                if req["url"].endswith("/AnonaHomeApi/getAnonaHomeNameList")
            ]
        )
        == 2
    )


def test_get_device_online_status_normalizes_online_state() -> None:
    """Online-state polling should map the captured online payload."""
    api, _ = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["online_status"]["response_object"])),
        ],
        authed=True,
    )

    online_status = asyncio.run(api.get_device_online_status("device-123"))

    assert online_status.online is True
    assert online_status.create_ts == 1775103001462
    assert online_status.last_alive_ts is None


def test_parse_lock_status_decodes_the_captured_hex_payload() -> None:
    """The lock-status parser should expose the inferred HA fields from dataHexStr."""
    status = parse_lock_status(
        FIXTURE["device_status"]["response_object"]["dataHexStr"]
    )

    assert status.locked is True
    assert status.lock_status_code == 1
    assert status.battery_capacity == 100
    assert status.auto_lock_enabled is True
    assert status.auto_lock_delay_seconds == 180
    assert status.auto_lock_delay_label == "3 minutes"
    assert status.door_state_code == 1
    assert status.door_status_code == 1
    assert status.sound_volume_code == 2
    assert status.sound_volume == "high"
    assert status.low_power_mode_enabled is False
    assert status.long_endurance_mode_status_code == 0
    assert status.raw_fields["3"] == {"1": {"1": 100}}
    assert status.raw_fields["11"] == {"1": 1, "2": 180}


def test_parse_lock_status_decodes_live_5_second_auto_lock_payload() -> None:
    """The parser should expose the shorter auto-lock delay seen in live testing."""
    status = parse_lock_status(
        "080110011A040A0208642001280030003A100A0010001A040A02080020002A00320040004800520208025A04080110056202080068007A0208018001008A01020802"
    )

    assert status.locked is True
    assert status.auto_lock_enabled is True
    assert status.auto_lock_delay_seconds == 5
    assert status.auto_lock_delay_label == "5 seconds"
    assert status.sound_volume_code == 2
    assert status.sound_volume == "high"
    assert status.low_power_mode_enabled is False
    assert status.raw_fields["11"] == {"1": 1, "2": 5}


def test_get_device_status_uses_explicit_device_context() -> None:
    """Status polling should require and use the normalized device context fields."""
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["device_status"]["response_object"])),
        ],
        authed=True,
    )
    device = normalize_device_context(FIXTURE["device_list"]["response_object"][0])

    status = asyncio.run(api.get_device_status(device))

    assert status.locked is True
    assert session.requests[1]["json"] == {
        "smartType": STATUS_SMART_TYPE,
        "deviceId": "device-123",
        "deviceModule": 76001,
        "deviceType": 76,
        "deviceChannel": 76001001,
        "uuid": FIXTURE["signature_fixture"]["client_uuid"],
        "channel": APP_CHANNEL,
        "ts": FIXTURE["server_ts"],
        "token": "session-token",
        "sig": FIXTURE["device_status"]["sig"],
    }


def test_get_device_status_logs_summary_without_raw_identifiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug lock-status logs should not include raw device identifiers or payloads."""
    api, _ = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["device_status"]["response_object"])),
        ],
        authed=True,
    )
    device = normalize_device_context(FIXTURE["device_list"]["response_object"][0])

    caplog.set_level(logging.DEBUG, logger=api_module.__name__)
    asyncio.run(api.get_device_status(device))

    assert "Decoded Anona lock status" in caplog.text
    assert "device-123" not in caplog.text
    assert FIXTURE["device_status"]["response_object"]["dataHexStr"] not in caplog.text


def test_get_device_certs_and_websocket_context_normalize_payloads() -> None:
    """Cert and websocket bootstrap endpoints should normalize the fixtures."""
    api, _ = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["device_certs"]["response_object"])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["websocket"]["response_object"])),
        ],
        authed=True,
    )

    certs = asyncio.run(api.get_device_certs_for_owner("device-123"))
    websocket_context = asyncio.run(api.get_websocket_address())

    assert certs.device_id == "device-123"
    assert certs.device_certs is not None
    assert (
        websocket_context.address
        == FIXTURE["websocket"]["response_object"]["websocketAddress"]
    )
    assert websocket_context.websocket_token == "ws-session-token"


def test_build_command_content_matches_the_captured_lock_and_unlock_payloads() -> None:
    """The protobuf command builder should reproduce the captured content hex."""
    assert (
        build_command_content(
            COMMAND_ID_LOCK,
            FIXTURE["login"]["response_object"]["userID"],
        )
        == FIXTURE["websocket_commands"]["lock"]["content"]
    )
    assert (
        build_command_content(
            COMMAND_ID_UNLOCK,
            FIXTURE["login"]["response_object"]["userID"],
        )
        == FIXTURE["websocket_commands"]["unlock"]["content"]
    )


def test_build_websocket_command_payload_uses_app_device_type() -> None:
    """Websocket command JSON should identify the mobile client as deviceType 73."""
    device = normalize_device_context(FIXTURE["device_list"]["response_object"][0])

    payload = build_websocket_command_payload(
        device=device,
        content=FIXTURE["websocket_commands"]["lock"]["content"],
        operate_id=FIXTURE["websocket_commands"]["lock"]["operate_id"],
        ts=FIXTURE["websocket_commands"]["lock"]["ts"],
        target=2,
    )

    assert payload["deviceId"] == "device-123"
    assert payload["deviceType"] == APP_DEVICE_TYPE


def test_decode_websocket_message_handles_plain_and_secure_frames() -> None:
    """Websocket decoding should support plaintext acks and CRC32-suffixed frames."""
    handshake_ack = json.dumps(FIXTURE["websocket_commands"]["handshake"]["ack"])
    encrypted_result = encrypt_websocket_payload(
        FIXTURE["websocket_commands"]["lock"]["result"],
        FIXTURE["websocket"]["response_object"]["websocketAesKey"],
    )

    decoded_handshake = decode_websocket_message(
        handshake_ack,
        websocket_aes_key=None,
    )
    decoded_result = decode_websocket_message(
        encrypted_result,
        websocket_aes_key=FIXTURE["websocket"]["response_object"]["websocketAesKey"],
    )

    assert decoded_handshake == WebsocketMessage(
        operate_id="1775128161513",
        ts=1775128161607,
        device_id=None,
        source=None,
        target=None,
        content=None,
        ack_code=200,
        is_ack=True,
        raw=FIXTURE["websocket_commands"]["handshake"]["ack"],
    )
    assert decoded_result.operate_id == "1775128212237501"
    assert decoded_result.device_id == "device-123"
    assert decoded_result.content == "083010079203043A020800"
    assert decoded_result.is_ack is False


def test_captured_secure_frames_end_with_little_endian_crc32() -> None:
    """Captured app frames should carry a CRC32 suffix after the ciphertext."""
    for payload_hex in FIXTURE["websocket_commands"]["captured_secure_frames"].values():
        secure_frame = bytes.fromhex(payload_hex)
        ciphertext = secure_frame[:-4]
        expected_crc = zlib.crc32(ciphertext) & 0xFFFFFFFF

        assert len(ciphertext) % 16 == 0
        assert secure_frame[-4:] == expected_crc.to_bytes(4, "little")


def test_lock_and_unlock_send_live_compatible_websocket_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public lock control should send the verified websocket command flow."""
    time_values = iter(
        [
            FIXTURE["websocket_commands"]["handshake"]["ts"] * 1_000_000,
            int(FIXTURE["websocket_commands"]["lock"]["operate_id"]) * 1_000,
            FIXTURE["websocket_commands"]["handshake"]["ts"] * 1_000_000,
            int(FIXTURE["websocket_commands"]["unlock"]["operate_id"]) * 1_000,
        ]
    )
    monkeypatch.setattr(api_module.time, "time_ns", lambda: next(time_values))
    websocket_lock = _FakeWebsocket(
        [
            _ws_text(json.dumps(FIXTURE["websocket_commands"]["handshake"]["ack"])),
            _ws_text(
                encrypt_websocket_payload(
                    FIXTURE["websocket_commands"]["lock"]["ack"],
                    FIXTURE["websocket"]["response_object"]["websocketAesKey"],
                )
            ),
            _ws_text(
                encrypt_websocket_payload(
                    FIXTURE["websocket_commands"]["lock"]["result"],
                    FIXTURE["websocket"]["response_object"]["websocketAesKey"],
                )
            ),
        ]
    )
    websocket_unlock = _FakeWebsocket(
        [
            _ws_text(json.dumps(FIXTURE["websocket_commands"]["handshake"]["ack"])),
            _ws_text(
                encrypt_websocket_payload(
                    FIXTURE["websocket_commands"]["unlock"]["ack"],
                    FIXTURE["websocket"]["response_object"]["websocketAesKey"],
                )
            ),
            _ws_text(
                encrypt_websocket_payload(
                    FIXTURE["websocket_commands"]["unlock"]["result"],
                    FIXTURE["websocket"]["response_object"]["websocketAesKey"],
                )
            ),
        ]
    )
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["device_certs"]["response_object"])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["websocket"]["response_object"])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["device_certs"]["response_object"])),
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success(FIXTURE["websocket"]["response_object"])),
        ],
        authed=True,
        websockets=[websocket_lock, websocket_unlock],
    )
    device = normalize_device_context(FIXTURE["device_list"]["response_object"][0])

    asyncio.run(api.lock(device))
    asyncio.run(api.unlock(device))

    assert len(session.websocket_requests) == 2
    assert json.loads(websocket_lock.sent[0]) == {
        "operateId": FIXTURE["websocket_commands"]["handshake"]["operate_id"],
        "ts": FIXTURE["websocket_commands"]["handshake"]["ts"],
        "handshakeToken": FIXTURE["websocket_commands"]["handshake"]["token"],
    }
    assert json.loads(websocket_unlock.sent[0]) == {
        "operateId": FIXTURE["websocket_commands"]["handshake"]["operate_id"],
        "ts": FIXTURE["websocket_commands"]["handshake"]["ts"],
        "handshakeToken": FIXTURE["websocket_commands"]["handshake"]["token"],
    }
    assert decode_websocket_message(
        websocket_lock.sent[1],
        websocket_aes_key=FIXTURE["websocket"]["response_object"]["websocketAesKey"],
    ).raw == {
        "content": FIXTURE["websocket_commands"]["lock"]["content"],
        "deviceId": "device-123",
        "deviceType": APP_DEVICE_TYPE,
        "operateId": FIXTURE["websocket_commands"]["lock"]["operate_id"],
        "target": 2,
        "ts": FIXTURE["websocket_commands"]["lock"]["ts"],
    }
    assert decode_websocket_message(
        websocket_unlock.sent[1],
        websocket_aes_key=FIXTURE["websocket"]["response_object"]["websocketAesKey"],
    ).raw == {
        "content": FIXTURE["websocket_commands"]["unlock"]["content"],
        "deviceId": "device-123",
        "deviceType": APP_DEVICE_TYPE,
        "operateId": FIXTURE["websocket_commands"]["unlock"]["operate_id"],
        "target": 2,
        "ts": FIXTURE["websocket_commands"]["unlock"]["ts"],
    }


def test_normalize_device_info_switch_and_firmware_payloads() -> None:
    """New context normalizers should map raw payloads into typed fields."""
    info_context = normalize_device_info_context(
        {
            "deviceId": "device-123",
            "type": 76,
            "module": 76001,
            "channel": 76001001,
            "softwareVersionNumber": "1.5.100",
            "softwareSubVersion": "a",
            "ip": "192.168.2.209",
            "wifiApSsid": "MyWifi",
            "wifiMac": "AA:BB:CC:DD:EE:FF",
            "btMac": "11:22:33:44:55:66",
            "timezoneId": "America/Los_Angeles",
            "silentOTA": True,
            "silentOTATime": (
                '{"beginHour":2,"beginMinute":0,"endHour":4,"endMinute":0}'
            ),
            "lastOnlineTs": 1775103001462,
        }
    )
    switch_settings = normalize_device_switch_settings(
        {
            "deviceId": "device-123",
            "mainSwitch": True,
            "ugentNotifySwitch": True,
            "importantNotifySwitch": False,
            "normalNotifySwitch": True,
        }
    )
    firmware_context = normalize_firmware_update_context(
        {
            "version": "1.5.189",
            "subVersion": "a",
            "newVersion": True,
            "desc": "Firmware release notes",
            "fileUrl": "https://example.com/firmware.bin",
            "releaseTime": 1729132842000,
            "fileMd5": "abc123",
            "fileSize": 1024,
            "forced": False,
        },
        device_id="device-123",
        installed_version="1.5.100",
    )

    assert info_context.silent_ota_time == "02:00-04:00"
    assert info_context.firmware_version == "1.5.100"
    assert switch_settings.important_notify_switch is False
    assert firmware_context.installed_version == "1.5.100"
    assert firmware_context.latest_version == "1.5.189"
    assert firmware_context.new_version is True


def test_update_device_switch_settings_uses_expected_payload_shape() -> None:
    """Switch writes should include all four switch fields with captured key names."""
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success({"success": True})),
        ],
        authed=True,
    )

    settings = asyncio.run(
        api.update_device_switch_settings(
            "device-123",
            main_switch=True,
            ugent_notify_switch=False,
            important_notify_switch=True,
            normal_notify_switch=False,
        )
    )

    assert settings.device_id == "device-123"
    assert session.requests[1]["json"] == {
        "deviceId": "device-123",
        "mainSwitch": True,
        "ugentNotifySwitch": False,
        "importantNotifySwitch": True,
        "normalNotifySwitch": False,
        "uuid": FIXTURE["signature_fixture"]["client_uuid"],
        "channel": APP_CHANNEL,
        "ts": FIXTURE["server_ts"],
        "token": "session-token",
        "sig": FIXTURE["signature_fixture"]["auth_sig"],
    }


def test_set_silent_ota_uses_expected_payload_shape() -> None:
    """Silent OTA writes should serialize the OTA window into app JSON format."""
    api, session = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(_encode_success({"success": True})),
        ],
        authed=True,
    )

    asyncio.run(
        api.set_silent_ota(
            "device-123",
            enabled=True,
            silent_ota_time="02:00-04:00",
        )
    )

    assert session.requests[1]["json"] == {
        "deviceId": "device-123",
        "silentOTA": True,
        "silentOTATime": ('{"beginHour":2,"beginMinute":0,"endHour":4,"endMinute":0}'),
        "uuid": FIXTURE["signature_fixture"]["client_uuid"],
        "channel": APP_CHANNEL,
        "ts": FIXTURE["server_ts"],
        "token": "session-token",
        "sig": FIXTURE["signature_fixture"]["auth_sig"],
    }
    assert (
        deserialize_silent_ota_time_window(
            '{"beginHour":2,"beginMinute":0,"endHour":4,"endMinute":0}'
        )
        == "02:00-04:00"
    )


def test_get_firmware_update_context_uses_info_version_fallback() -> None:
    """Firmware normalization should fall back to getDeviceInfo installed version."""
    api, _ = _make_api(
        [
            _FakeResponse(_encode_success(FIXTURE["server_ts"])),
            _FakeResponse(
                _encode_success(
                    {
                        "version": "1.5.189",
                        "newVersion": True,
                        "desc": "Firmware release notes",
                    }
                )
            ),
        ],
        authed=True,
    )
    api._device_info_by_id["device-123"] = DeviceInfoContext(
        device_id="device-123",
        device_type=76,
        device_module=76001,
        device_channel=76001001,
        firmware_version="1.5.100",
        firmware_sub_version=None,
        ip_address=None,
        wifi_ap_ssid=None,
        wifi_mac=None,
        bt_mac=None,
        timezone_id=None,
        silent_ota_enabled=None,
        silent_ota_time=None,
        silent_ota_time_raw=None,
        last_online_ts=None,
        raw={},
    )
    device = normalize_device_context(FIXTURE["device_list"]["response_object"][0])

    context = asyncio.run(api.get_firmware_update_context(device))

    assert context.installed_version == "1.5.100"
    assert context.latest_version == "1.5.189"
    assert context.new_version is True


def test_update_availability_prefers_version_compare_then_flag_fallback() -> None:
    """Firmware availability should compare version ordering before fallback checks."""
    assert (
        is_firmware_update_available(
            installed_version="1.5.100",
            latest_version="1.5.189",
            new_version=False,
        )
        is True
    )
    assert (
        is_firmware_update_available(
            installed_version="1.5.189",
            latest_version="1.5.189",
            new_version=True,
        )
        is False
    )
    assert (
        is_firmware_update_available(
            installed_version="x",
            latest_version="y",
            new_version=True,
        )
        is True
    )
