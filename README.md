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

The integration supports live login, home discovery, device discovery, online polling, and status polling against the production API. On April 2, 2026, the mounted component was also probed from a local Home Assistant `2026.3.4` container and successfully fetched homes, devices, online state, and lock status from production.

The repository also includes the reconstructed websocket command helpers from the native app capture:

- plaintext websocket handshake using the session token from `getWebsocketAddress`
- AES-CBC websocket frame encryption/decryption helpers
- protobuf command packing for `sendID = 7` (`lockDoor`) and `sendID = 6` (`unLockDoor`)
- same-`operateId` ack/result parsing

Current boundary:

1. `lock` and `unlock` are intentionally blocked in the public API because live Home Assistant validation showed the production websocket closes immediately after the handshake when Home Assistant sends the reconstructed command frame.
2. The remaining gap is the native app's missing websocket command conversion/auth step, not the HTTP API.

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
