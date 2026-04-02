# Anona Security

Home Assistant custom integration for Anona smart locks.

## Status

This repository now matches the captured HTTP API shape from the Anona mobile app:

- base64 response envelopes with `resultBodyObject`, `error`, and `errorCode`
- server-time bootstrap via `/baseServiceApi/V2/getTs`
- verified request signing for login and authenticated HTTP calls
- normalized home and device discovery
- online state from `/anona/device/api/getDeviceOnlineStatus`
- lock state and battery parsing from `dataHexStr`
- websocket bootstrap via `getDeviceCertsForOwner` and `getWebsocketAddress`

The integration now supports live login, home discovery, device discovery, online polling, and status polling against the production API.
The repository now also includes the captured websocket command path for lock and unlock:

- plaintext websocket handshake using the session token from `getWebsocketAddress`
- AES-CBC encrypted websocket command frames
- protobuf command packing for `sendID = 7` (`lockDoor`) and `sendID = 6` (`unLockDoor`)
- same-`operateId` command completion handling

Current boundary:

1. The websocket command implementation is fixture-backed and protocol-grounded, but it still needs a fresh end-to-end validation run from a live Home Assistant instance.

## Development

From a clean checkout:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv venv .venv
UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/ruff check custom_components/anona_security tests
uvx pyright custom_components/anona_security tests
.venv/bin/python -m pytest
```

## Repository Notes

- Runtime code lives in `custom_components/anona_security`.
- Fixture-backed tests live in `tests/`.
- The migration exec plan is in [`docs/execplans/2026-04-01-align-anona-security-with-captured-api.md`](docs/execplans/2026-04-01-align-anona-security-with-captured-api.md).
- The websocket command capture note is in [`docs/2026-04-02-anona-websocket-command-capture.md`](docs/2026-04-02-anona-websocket-command-capture.md).
