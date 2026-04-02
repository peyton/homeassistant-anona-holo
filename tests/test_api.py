"""Tests for the captured Anona API helpers and client."""

# ruff: noqa: S101, S105, PLR2004, SLF001

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self, cast

from custom_components.anona_security.api import (
    AnonaApi,
    build_authenticated_signature,
    build_login_signature,
    decode_response_envelope,
    hash_password,
    normalize_device_context,
    parse_lock_status,
)
from custom_components.anona_security.const import (
    APP_CHANNEL,
    APP_DEVICE_TYPE,
    DEFAULT_LANG,
    STATUS_SMART_TYPE,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "anona_capture.json"
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

    def __init__(self, responses: list[_FakeResponse]) -> None:
        """Initialize the fake session with a response queue."""
        self._responses = responses
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        """Record the request and return the next canned response."""
        self.requests.append({"url": url, **kwargs})
        return self._responses.pop(0)


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
) -> tuple[AnonaApi, _FakeSession]:
    """Build an API client backed by the fake session."""
    session = _FakeSession(responses)
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
    assert status.charge_status_code == 1
    assert status.battery_voltage == 180
    assert status.door_state_code == 1
    assert status.door_status_code == 1
    assert status.long_endurance_mode_status_code == 0
    assert status.raw_fields["3"] == {"1": {"1": 100}}
    assert status.raw_fields["11"] == {"1": 1, "2": 180}


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
