# Anona Security

Home Assistant custom integration for Anona smart locks.

## HACS

This integration is structured for HACS distribution:

1. Add this repository to HACS as a custom integration repository, or install it directly once the repository is published in HACS.
2. Install `Anona Security`.
3. Restart Home Assistant.
4. Add the integration from `Settings -> Devices & services`.
5. Sign in with the same email address and password you use in the Anona app.

Minimum tested Home Assistant version: `2026.3.4`

## Status

This repository now matches the Anona mobile app API shape that was captured and verified live:

- base64 response envelopes with `resultBodyObject`, `error`, and `errorCode`
- server-time bootstrap via `/baseServiceApi/V2/getTs`
- verified request signing for login and authenticated HTTP calls
- normalized home and device discovery
- online state from `/anona/device/api/getDeviceOnlineStatus`
- lock state and battery parsing from `dataHexStr`
- websocket bootstrap via `getDeviceCertsForOwner` and `getWebsocketAddress`

The repository also includes the reconstructed websocket command helpers from the native app capture:

- plaintext websocket handshake using the session token from `getWebsocketAddress`
- AES-CBC websocket frame encryption/decryption with the app's trailing little-endian CRC32
- websocket command JSON using the mobile-client `deviceType = 73` and `target = 2`
- protobuf command packing for `sendID = 7` (`lockDoor`) and `sendID = 6` (`unLockDoor`)
- same-`operateId` ack/result parsing through Home Assistant lock service calls

Live command validation:

1. On April 2, 2026, repo-local live validation against production successfully issued a real `unlock` followed by a real `lock`, ending `Front Door Lock` back in the locked state.
2. On April 2, 2026, a local Home Assistant `2026.3.4` container loaded the mounted integration and completed a real `lock.unlock` then `lock.lock` round trip for `Front Door Lock`.

## Development

From a clean checkout:

```bash
mise bootstrap
just lint
just typecheck
just test
```

`mise bootstrap` installs the pinned CLI tools, creates `.venv`, installs the Python dependencies, and refreshes the `hk` git hooks. The `justfile` is the canonical manual command surface after bootstrap.

## Repository Notes

- Runtime code lives in `custom_components/anona_security`.
- Fixture-backed tests live in `tests/`.
- The migration exec plan is in [`docs/execplans/2026-04-01-align-anona-security-with-captured-api.md`](docs/execplans/2026-04-01-align-anona-security-with-captured-api.md).
- The websocket command capture note is in [`docs/2026-04-02-anona-websocket-command-capture.md`](docs/2026-04-02-anona-websocket-command-capture.md).
