# Anona Holo

Home Assistant custom integration for the Anona Holo smart lock, available [here](https://www.anonasecurity.com/products/holo).

## Supported Features

This integration currently supports:

- lock and unlock commands
- lock state
- online and availability state
- battery and telemetry sensors:
  - battery level (enabled by default)
  - auto-lock delay and sound volume (enabled by default)
  - keypad battery and last alive timestamp (diagnostic; disabled by default)
- binary telemetry:
  - auto-lock enabled
  - lock jam / locking failure
  - door open too long
  - online
  - low power mode and keypad connected (diagnostic; disabled by default)
- writable controls:
  - allow notifications
  - abnormal notifications
  - event notifications
  - other notifications
  - silent OTA
- firmware update entity with installed/latest version, release notes, and release URL
- config-entry and device diagnostics export with sensitive-field redaction
- system health reporting with aggregate integration status and Anona API reachability

**This integration does not support the Anona Holo Keypad.** Raw keypad-related diagnostic fields may still appear in lock attributes because the upstream lock status payload includes them, but no keypad entity or keypad controls are provided.

## HACS

This integration is structured for HACS distribution:

1. Add this repository to HACS as a custom integration repository, or install it directly once the repository is published in HACS.
2. Install `Anona Holo`.
3. Restart Home Assistant.
4. Add the integration from `Settings -> Devices & services`.
5. Sign in with the same email address and password you use in the Anona app.

If you already installed the previous version of this integration, remove it first and then add the renamed `anona_holo` integration again. This rename is a breaking change and does not include a migration path for existing installs.

Minimum tested Home Assistant version: `2026.3.4`

## Status

This integration matches the Anona mobile app API shape that was captured and verified live using Anona Security v1.5.0 for iOS:

- base64 response envelopes with `resultBodyObject`, `error`, and `errorCode`
- server-time bootstrap via `/baseServiceApi/V2/getTs`
- verified request signing for login and authenticated HTTP calls
- normalized home and device discovery
- online state from `/anona/device/api/getDeviceOnlineStatus`
- lock state and battery parsing from `dataHexStr`
- deeper config-state parsing from `dataHexStr`, including auto-lock timing, sound volume, and low-power mode
- websocket bootstrap via `getDeviceCertsForOwner` and `getWebsocketAddress`

The repository also includes the reconstructed websocket command helpers from the native app capture:

- plaintext websocket handshake using the session token from `getWebsocketAddress`
- AES-CBC websocket frame encryption/decryption with the app's trailing little-endian CRC32
- websocket command JSON using the mobile-client `deviceType = 73` and `target = 2`
- protobuf command packing for `sendID = 7` (`lockDoor`) and `sendID = 6` (`unLockDoor`)
- same-`operateId` ack/result parsing through Home Assistant lock service calls

## Development

From a clean checkout:

```bash
mise bootstrap
just lint
just typecheck
just test
```

`mise bootstrap` installs the pinned CLI tools, creates `.venv`, installs the Python dependencies, and refreshes the `hk` git hooks. The `justfile` is the canonical manual command surface after bootstrap.

For local Home Assistant development, run `just develop`. It will create an ignored `config/` directory with a default `configuration.yaml` on first run and preserve any existing local changes under that directory.

Codex worktrees also bootstrap through [`.codex/environments/environment.toml`](.codex/environments/environment.toml). The default environment runs `./scripts/codex setup` and exposes `develop` and `check` actions backed by the same repo-local wrapper. That wrapper ignores the user-global `mise` config so a fresh Codex worktree only installs and runs this repository's pinned toolchain.

## Release

This repository uses stable CalVer for releases:

- Manifest version format: `YYYY.M.P` (for example `2026.4.0`)
- Git tag format: `vYYYY.M.P` (for example `v2026.4.0`)
- Release invariant: `custom_components/anona_holo/manifest.json` version must exactly match the tag version.

Choose the next release version by keeping the current year/month and incrementing patch manually:

- First release in a month: `YYYY.M.0`
- Next release in that month: `YYYY.M.1`, `YYYY.M.2`, ...

Cut a release with one command:

```bash
just release-tag 2026.4.0
```

`just release-tag` performs `release-check` guardrails, runs `just check`, updates the manifest version, creates commit `chore(release): v<version>`, creates an annotated tag, and pushes both commit and tag.

After pushing, monitor and verify the GitHub `Release` workflow:

```bash
gh run list --workflow Release --limit 5
gh run watch <run-id>
gh release view v2026.4.0
```

## Repository Notes

- Runtime code lives in `custom_components/anona_holo`.
- Fixture-backed tests live in `tests/`.
- CI now includes Home Assistant runtime config-entry lifecycle coverage (setup,
  auth/not-ready mapping, unload cleanup) and entity/service behavior tests for
  the lock platform.
- Future hardening we can add later: step 3 HTTP-boundary tests with a local
  `aiohttp` test server, and step 4 an optional secret-backed live smoke
  workflow against a sacrificial test account/device.
- The migration exec plan is in [`docs/execplans/2026-04-01-align-anona-security-with-captured-api.md`](docs/execplans/2026-04-01-align-anona-security-with-captured-api.md).
- The websocket command capture note is in [`docs/2026-04-02-anona-websocket-command-capture.md`](docs/2026-04-02-anona-websocket-command-capture.md).
