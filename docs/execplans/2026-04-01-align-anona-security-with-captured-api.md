# Align `anona_security` With the captured Anona API

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows [AGENTS.md](/Users/peyton/ghq/github.com/peyton/homeassistant-anona-security/AGENTS.md). The repo instruction points at `~/.agent/PLANS.md`, but the actual plan guidance on disk is `/Users/peyton/.agents/PLANS.md`, and this document is maintained to that standard.

## Purpose / Big Picture

After this change, `custom_components/anona_security` matches the captured Anona cloud API shape instead of the earlier placeholder implementation. The integration code understands the base64 envelope, the home and device models, the explicit lock device context, the online-status endpoint, and the `dataHexStr` status payload. The observable proof is that the repository contains a migrated API client, updated Home Assistant wiring, focused fixture-backed tests, and passing local validation.

The HTTP signer is now solved and verified live against the production API. Home Assistant can log in, discover homes and devices, poll online state, fetch lock status, and bootstrap websocket prerequisites without relying on the app bundle. The remaining blocker is narrower: lock and unlock still require a websocket-frame capture that includes `authSync`, `lockDoor`, and `unLockDoor` so the command channel can be implemented safely.

## Progress

- [x] (2026-04-01 22:04Z) Re-read the current `anona_security` integration, the stale tests, the existing execplan pattern, and the plan requirements from `/Users/peyton/.agents/PLANS.md`.
- [x] (2026-04-01 22:13Z) Confirmed the captured API contract from `/Users/peyton/Desktop/us-api.anonasecurity.com_04-01-2026-21-25-18.har`, including base64 envelopes, `getTs`, login fields, home/device/status endpoints, device certs, and websocket address responses.
- [x] (2026-04-01 22:19Z) Confirmed from the app bundle that the lock family uses `type=76`, `module=76001`, `channel=76001001`, while app requests use `deviceType=73` and `channel=73001001`.
- [x] (2026-04-01 22:31Z) Reversed the password hash implementation enough to prove it is `md5(password + "329he3wihfeibfk3209(&*^%dehsi3)*&").lower()`.
- [x] (2026-04-01 22:46Z) Reversed the request-sign lookup flow enough to prove the app reads signatures from a cache keyed by `md5("{ts}_{uuid.lower()}_{channel}")`, with a migration fallback keyed by `"{ts}_{token}"`.
- [x] (2026-04-01 22:56Z) Verified against the live API that the backend enforces `sig`; a bad login request returns `errorCode=-1` and `errorMessage="sig not passed"`.
- [x] (2026-04-01 23:58Z) Rewrote `custom_components/anona_security/api.py`, `const.py`, `config_flow.py`, `__init__.py`, and `lock.py` around the captured API contract with typed models, base64 envelope decoding, request bootstrap, inferred `dataHexStr` parsing, and explicit signer/websocket blockers.
- [x] (2026-04-02 00:06Z) Replaced the stale tests with sanitized fixture-backed `anona_security` coverage for login, homes, devices, online state, websocket bootstrap, cert parsing, config flow wiring, and lock entity behavior.
- [x] (2026-04-02 00:09Z) Updated the root README and manifest to describe the real integration, the current signer/websocket prerequisites, and the repo-local validation commands.
- [x] (2026-04-02 00:20Z) Ran `ruff`, `pytest`, and `pyright` successfully from the repo toolchain; all checks passed after fixing the final typing and entity metadata issues.
- [x] (2026-04-02 07:58Z) Tightened the `dataHexStr` mapping with conservative battery, door-state, and long-endurance diagnostics derived from the app’s native lock-status vocabulary, then re-ran `ruff`, `pytest`, and `pyright`.
- [x] (2026-04-02 07:58Z) Narrowed the unresolved H5 signer ownership to `PubBaseWebController` plus the native `PubH5Request` and `PubH5ProxyResponse` models compiled alongside `PubDataNetwork+H5.swift`.
- [x] (2026-04-02 10:14Z) Verified live that login succeeds with `deviceToken=""` and a random UUID, and that every required authenticated HTTP endpoint accepts `sig = md5(token + uuid + channel + ts + salt)`.
- [x] (2026-04-02 10:33Z) Replaced the temporary signer blocker with the verified login and authenticated signature helpers, fixed `getTs` to POST `{}`, updated the config flow and docs, and rewrote the tests to assert the real signer behavior.
- [x] (2026-04-02 10:44Z) Re-ran repo-local validation after the live-signer patch set: `ruff` passed, `uvx pyright --pythonpath ./.venv/bin/python` passed with 0 errors, and `pytest` passed with 18 tests green.

## Surprises & Discoveries

- Observation: The repo plan pointer in `AGENTS.md` is stale.
  Evidence: `sed -n '1,260p' ~/.agent/PLANS.md` failed with “No such file or directory”, while `find ~/ -maxdepth 3 -name 'PLANS.md'` returned `/Users/peyton/.agents/PLANS.md`.

- Observation: The API wraps successful responses in base64-encoded JSON but may return plain JSON for signature failures.
  Evidence: the HAR responses decode from base64 into objects with `resultBodyObject`, `error`, and `errorCode`; a live bad-signature login request returned plain JSON `{"resultBodyObject":null,"error":true,"errorMessage":"sig not passed","errorCode":-1}`.

- Observation: Request signing is a direct MD5 over stable field concatenations; the earlier keychain interpretation was incomplete.
  Evidence: live requests now succeed with `login sig = md5(deviceType + email + "null" + passWordMd5 + ts + salt)` and `authenticated sig = md5(token + uuid + channel + ts + salt)`. The same authenticated formula validated live for `getAllUserInfo`, `getAnonaHomeNameList`, `getDeviceListByHomeId`, `getDeviceOnlineStatus`, `getAnonaDeviceStatus`, `getWebsocketAddress`, and `getDeviceCertsForOwner`.

- Observation: `getTs` requires a `POST` with an empty JSON object rather than a bodyless `POST` or a `GET`.
  Evidence: live probes on 2026-04-02 returned `405 Method Not Allowed` for `GET /baseServiceApi/V2/getTs` and for a bodyless `POST`, while `POST {}` returned `200` with an integer `resultBodyObject`.

- Observation: The HAR does not include websocket frames, so live lock and unlock traffic still cannot be reproduced safely.
  Evidence: the HAR entries include HTTP requests for `getDeviceCertsForOwner` and `getWebsocketAddress`, but there are no captured websocket frame payloads to reconstruct `authSync`, `lockDoor`, or `unLockDoor`.

- Observation: The H5 signer surface is owned by `PubBaseWebController`, while the proxy request and response models are native Swift types in the same module.
  Evidence: `xcrun otool -ov .../Anona | sed -n '142244,142430p;178247,178340p;183322,183350p'` shows `_TtC11PublicUIKit20PubBaseWebController` with ivars `deviceType`, `deviceModule`, `channel`, `deviceId`, `messageHandlers`, and `jsBridge`, plus `_TtC11PublicUIKit12PubH5Request.data` and `_TtC11PublicUIKit18PubH5ProxyResponse.{error,errorCode,resultBodyObject}`. `strings -a .../Anona | rg 'requestSign|performHttpRequest|checkRegisterHandler|PubBaseWebController.swift|PubDataNetwork\\+H5.swift'` places those bridge commands and both source paths in the same binary.

- Observation: The lock-status payload supports more diagnostics than the original HA entity exposed, but only some field mappings are proven by the current fixture.
  Evidence: the binary contains lock-status names such as `door_state`, `battery_voltage`, `keypad_connection_status`, and long-endurance mode fields; the captured `dataHexStr` decodes into stable numeric fields where `11.1`, `11.2`, `2`, and `12.1` can be surfaced conservatively as charge status, battery voltage, door state, and long-endurance status.

## Decision Log

- Decision: Replace the temporary signer blocker with the verified local signer and keep only websocket lock control gated.
  Rationale: the signer formula is now proven live. Leaving the HTTP path behind a blocker would be less correct than implementing the verified contract, while websocket command payloads still lack the necessary evidence.
  Date/Author: 2026-04-02 / Codex

- Decision: Sanitize test fixtures instead of copying raw HAR bodies with the user’s email, token, device identifiers, or certificates.
  Rationale: the repo should capture shapes and semantics, not sensitive account data.
  Date/Author: 2026-04-01 / Codex

- Decision: Keep websocket commands deliberately unavailable even after cert and websocket-address parsing is implemented.
  Rationale: the plan already requires a second capture with websocket frames before reproducing the command channel. The correct interim behavior is a clear runtime error, not a best-effort JSON guess.
  Date/Author: 2026-04-01 / Codex

- Decision: Treat the `dataHexStr` parser as an inferred protobuf-wire decoder and expose uncertain diagnostics as numeric codes and raw fields.
  Rationale: the app metadata confirms the response model fields, but the provided capture does not prove every field-number-to-property mapping. Returning explicit codes and raw state keeps the integration debuggable without inventing false semantics.
  Date/Author: 2026-04-01 / Codex

## Outcomes & Retrospective

This plan started as a full API migration and remains that in structure, but the implementation boundary has moved forward. The captured and proven parts now include the HTTP signer, login, home discovery, device discovery, online polling, lock-status polling, device-cert fetch, websocket bootstrap fetch, and the Home Assistant wiring around those flows. The only blocked part is the websocket command channel for `lockDoor` and `unLockDoor`.

The repository is now in the right state for shipping the read-only and polling parts of the integration. The HA entity exposes a conservative diagnostic surface from `dataHexStr`, logs in live with a stable generated UUID, and fetches the same HTTP resources as the native app. The final remaining work after this plan is to capture websocket auth plus one lock and one unlock exchange and then implement the command channel deliberately.

## Context and Orientation

The integration code lives in `custom_components/anona_security`. The important modules are `api.py`, which contains the cloud client and response parsing, `config_flow.py`, which drives Home Assistant setup from email and password, `__init__.py`, which logs in and stores the API client in `hass.data`, `lock.py`, which creates lock entities from the API client, and `const.py`, which contains the shared constants.

The current runtime is still the legacy implementation that assumes flat JSON responses, stores `accessToken`, reads `lockState` directly from HTTP JSON, and sends guessed JSON over a websocket. The current tests under `tests/` are also stale: `tests/test_config_flow.py` still imports `custom_components.integration_blueprint`, and the README still describes a generic Home Assistant template instead of this integration.

The captured HTTP archive is `/Users/peyton/Desktop/us-api.anonasecurity.com_04-01-2026-21-25-18.har`. It shows that successful API responses are base64-encoded JSON envelopes. The login endpoint is `/accountApi/V3/userLoginPwd`; the API bootstrap endpoint is `/baseServiceApi/V2/getTs`; the home list endpoint is `/AnonaHomeApi/getAnonaHomeNameList`; the device list endpoint is `/anona/device/api/getDeviceListByHomeId`; the device online endpoint is `/anona/device/api/getDeviceOnlineStatus`; the lock status endpoint is `/anona/device/status/api/getAnonaDeviceStatus`; the device-cert and websocket-address endpoints are `/anona/device/api/getDeviceCertsForOwner` and `/anonaWebsocketApi/getWebsocketAddress`.

A “config entry” is Home Assistant’s stored integration record. A “device context” in this plan means the normalized per-device data needed for later requests: device type, module, channel, device ID, nickname, serial number, and model. A “status parser” in this plan means code that decodes `resultBodyObject.dataHexStr` into a smaller lock-state model for Home Assistant.

## Plan of Work

First, replace `custom_components/anona_security/const.py` with constants that match the captured API. The new constants must include the request channel and device type, the lock device identifiers, the base URL and endpoint paths, the password-sign salt, config-entry keys for `email`, `password`, `client_uuid`, `user_id`, and `home_id`, and a fixed scan interval for polling.

Next, rewrite `custom_components/anona_security/api.py` around three responsibilities: request construction, response decoding, and model normalization. The request layer must fetch server time from `getTs`, add `uuid`, `channel`, and `ts`, decode either base64 envelopes or plain JSON error payloads, and raise typed errors for auth failures, signature failures, and command-path blockers. The signature provider must compute the verified login and authenticated HTTP formulas locally so Home Assistant can log in and poll without the app bundle. The response layer must normalize homes, devices, online status, device certs, websocket address responses, and `dataHexStr` lock status into Python dataclasses with type hints.

Then, update `custom_components/anona_security/config_flow.py` so it validates with the new API shape and persists `client_uuid`, `user_id`, and `home_id`. Because login no longer yields a home ID directly, the flow must call the home-list endpoint after login and select the default home or the first returned home. Generic upstream failures should surface as normal config-flow errors; only websocket command attempts remain specially blocked.

After that, update `custom_components/anona_security/__init__.py` and `custom_components/anona_security/lock.py`. Setup must create the API client with the stored `client_uuid`, re-login on setup, refresh the stored `user_id` and `home_id` when newer values are discovered, and load only the `lock` platform. The lock platform must work from normalized `DeviceContext` objects, filter devices to `type == 76`, derive availability from the online endpoint, derive lock state and battery from the decoded `dataHexStr`, and preserve raw diagnostic fields as extra attributes. The `lock` and `unlock` methods must fetch cert and websocket prerequisites and then raise a clear command-path blocker until websocket frames are captured.

Finally, replace the stale tests and update the README. The test surface must cover the sanitized response fixtures, the password hash helper, the verified login and authenticated signature helpers, status decoding, config flow entry data, and lock entity behavior. The README must stop describing a template integration and instead document the real API migration, the local development commands, and the remaining websocket-command prerequisite.

## Concrete Steps

Work from the repository root `/Users/peyton/ghq/github.com/peyton/homeassistant-anona-security`.

Create or update the execplan and then edit the runtime modules and tests in place.

Set up a repo-local environment with:

    UV_CACHE_DIR=/tmp/uv-cache uv venv .venv
    UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -r requirements.txt

Run validation with:

    .venv/bin/ruff check custom_components/anona_security tests
    .venv/bin/pyright custom_components/anona_security tests
    .venv/bin/python -m pytest

If `pyright` needs the interpreter path explicitly in this repo, use:

    .venv/bin/pyright --pythonpath .venv/bin/python custom_components/anona_security tests

Observed validation on 2026-04-02:

    .venv/bin/ruff check custom_components/anona_security tests
    # All checks passed

    .venv/bin/python -m pytest
    # 18 passed, 1 Home Assistant deprecation warning from upstream

    XDG_CACHE_HOME=/tmp/xdg-cache UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pyright --pythonpath .venv/bin/python custom_components/anona_security tests
    # 0 errors, 0 warnings, 0 informations

## Validation and Acceptance

Acceptance for this migration is behavioral and repository-local. The repository must contain an API client that decodes captured envelopes, signs requests with the verified formulas, and normalizes home, device, online, websocket, cert, and status data from sanitized fixtures. The config flow must store `email`, `password`, `client_uuid`, `user_id`, and `home_id` when the mocked API succeeds. The lock entity setup must create only lock devices from normalized device contexts and expose availability, lock state, battery, and raw status diagnostics from the mocked API models.

Because websocket command frames are still missing from the capture, the live acceptance condition is now “real login and polling work; lock and unlock remain intentionally blocked.” The integration must fail with a precise runtime error only when lock or unlock is attempted without a websocket-frame capture.

## Idempotence and Recovery

All file edits in this plan are in-place code and documentation changes. They can be re-applied safely as long as the same runtime surface is preserved. The fixture files are sanitized and static, so regenerating or editing them does not affect user data. If validation fails after a partial edit, rerun the relevant command after fixing the failing file; there is no database migration or destructive cleanup step in this work.

The risky operations in this task are not filesystem operations but false confidence. The HTTP signer is now verified, so keep it. Do not extend that confidence to websocket commands without the corresponding frame capture. If a future contributor captures websocket auth plus command frames, update this plan, add the new tests, and remove the remaining command blocker deliberately.

## Artifacts and Notes

Key reverse-engineering evidence captured during research:

    login password hashing path:
    0x100e32764  literal pool for "329he3wihfeibfk3209(&*^%dehsi3)*&"
    0x100e327bc  Objc message: -[x0 com_md5String]
    0x100e32808  lowercased

    request-sign cache helper at 0x100c56624:
    build "{ts}_{uuid.lower()}_{channel}"
    md5 it
    PubKeychainManager.getValueForKeychain(forKey: md5Value)
    if missing and token present:
      getValueForKeychain(forKey: "{ts}_{token}")
      setValueForKeychain(tempValue, forKey: md5Value)
      removeValueForKeychain(forKey: "{ts}_{token}")

    live bad-signature login response:
    {"resultBodyObject":null,"error":true,"errorMessage":"sig not passed","errorCode":-1}

## Interfaces and Dependencies

At the end of this migration, `custom_components/anona_security/api.py` must define typed runtime models and an API client roughly in this shape:

    class AnonaApi:
        async def login(self, email: str, password: str) -> LoginContext: ...
        async def get_homes(self) -> list[HomeContext]: ...
        async def get_devices(self, home_id: str | None = None) -> list[DeviceContext]: ...
        async def get_device_info(self, device_id: str) -> DeviceContext: ...
        async def get_device_online_status(self, device: DeviceContext | str) -> OnlineStatus: ...
        async def get_device_status(self, device: DeviceContext) -> LockStatus: ...
        async def get_device_certs_for_owner(self, device: DeviceContext | str) -> DeviceCerts: ...
        async def get_websocket_address(self) -> WebsocketContext: ...
        async def lock(self, device: DeviceContext | str) -> None: ...
        async def unlock(self, device: DeviceContext | str) -> None: ...

The module must also expose pure helpers for envelope decoding, password hashing, signature construction, and `dataHexStr` parsing so the tests can exercise them without network I/O.

`custom_components/anona_security/config_flow.py` must create entries with at least `email`, `password`, `client_uuid`, `user_id`, and `home_id` in `data`. `custom_components/anona_security/lock.py` must use normalized `DeviceContext`, `OnlineStatus`, and `LockStatus` objects instead of raw JSON dicts. The integration depends only on `aiohttp` and Home Assistant’s built-in helpers for the code delivered in this plan.

Change note: 2026-04-02. Updated this ExecPlan after live production validation proved the HTTP signer formulas, narrowed the remaining blocker to websocket command frames, and aligned the repository state with that verified boundary.
