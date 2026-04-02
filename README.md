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

One live-control gap remains intentionally blocked:

1. Lock and unlock still require a websocket capture that includes `authSync`, `lockDoor`, and `unLockDoor` frames.

Until those frames are captured, the integration keeps command execution behind an explicit error instead of sending guessed websocket payloads.

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
