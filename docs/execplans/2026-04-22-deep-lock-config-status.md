# Expose Deep Lock Configuration Status Without Breaking Stable IDs

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are kept current for this implementation pass. This repository does not check in a separate `PLANS.md`, so this document follows the user-level `~/.agents/PLANS.md` requirements directly.

## Purpose / Big Picture

After this change, Home Assistant users can see the lock's deeper configuration state that the Anona app already exposes, including auto-lock timing, sound volume, and low-power mode, without relying on raw protobuf blobs. The integration must keep device registry identifiers and entity unique IDs stable so an update adds entities in place instead of creating duplicate devices or duplicate entities.

## Progress

- [x] (2026-04-23 03:35Z) Audited the current integration runtime, coordinator, entity ID scheme, and existing tests.
- [x] (2026-04-23 03:37Z) Reverse engineered live lock settings from the vendor app and lock status payload. Confirmed `Auto-lock`, `Sound settings`, `Low power mode`, and `Temporary disable auto-lock` surfaces in the native UI.
- [x] (2026-04-23 03:39Z) Verified with live app interaction that changing auto-lock from `3min` to `5s` changes one status protobuf field from `180` to `5`, proving the integration can read auto-lock timing directly from `getAnonaDeviceStatus`.
- [x] (2026-04-23 03:41Z) Verified with live app interaction that sound settings expose `Sound alert` plus a `Volume` picker with `High` and `Low`, and that the status protobuf still carries a `volume` field.
- [x] (2026-04-23 03:56Z) Remapped `LockStatus` to expose confirmed config fields: auto-lock enabled, auto-lock delay seconds/label, sound volume code/label, and low-power mode status. Stopped surfacing the incorrect battery-voltage interpretation in Home Assistant entities.
- [x] (2026-04-23 04:00Z) Added Home Assistant entities for the confirmed deep config state using deterministic unique ID suffixes: `binary_sensor.auto_lock`, `sensor.auto_lock_delay`, and `sensor.sound_volume`.
- [x] (2026-04-23 04:05Z) Added regression tests for protobuf parsing, entity mapping, lock attributes, and config-entry reload stability with a one-device/no-duplicate assertion.
- [x] (2026-04-23 04:12Z) Ran repository validation successfully: focused pytest, then `just check`.

## Surprises & Discoveries

- Observation: the native app exposes `Temporary disable auto-lock` directly on the main lock detail screen, not only inside the settings page.
  Evidence: live accessibility tree for `Front Door Lock` showed `Temporary disable auto-lock, Off`.

- Observation: the existing integration's `battery_voltage` field mapping is almost certainly wrong for the current lock model. The same raw field changed from `180` to `5` exactly when the app changed auto-lock delay from `3min` to `5s`.
  Evidence: live `getAnonaDeviceStatus` payloads before and after the app change.

- Observation: the shipped app binary contains explicit lock-setting command names for both BLE and websocket paths, including `getAutoLock`, `setAutoLock`, `getSound`, `setSound`, `getDoorlockLongEndurance`, `setDoorlockLongEndurance`, and `setNormalOpenMode`.
  Evidence: string extraction from `/Applications/Anona Security.app/Wrapper/Anona.app/Anona`.

- Observation: the app's sound screen revealed `High` and `Low` options only after `Sound alert` was turned on, but the status payload still reported a remembered `volume` value even when the toggle had previously appeared off.
  Evidence: live UI inspection and status log lines containing `doorlock_status { volume: HIGH }`.

## Decision Log

- Decision: ship only the deep configuration fields that were proven from live status payloads and app UI in this pass.
  Rationale: writable setting commands exist in the app binary, but the exact command payload format is still underconstrained. Exposing confirmed read models is safer than guessing writes for a real door lock.
  Date/Author: 2026-04-23 / Codex

- Decision: preserve the existing `(DOMAIN, device_id)` device identifier and continue deriving new entity unique IDs from `f"{DOMAIN}_{device_id}_{suffix}"`.
  Rationale: this is the simplest way to guarantee Home Assistant adds new entities without duplicating the device or reparenting existing entities.
  Date/Author: 2026-04-23 / Codex

## Outcomes & Retrospective

The integration now exposes the deeper lock configuration state that could be proven from live app and payload inspection: Home Assistant users can see whether auto-lock is enabled, the current auto-lock timeout, the current sound volume, and the existing low-power-mode state. The lock entity's extra attributes also carry these fields with human-readable labels, and the incorrect battery-voltage interpretation is no longer exposed as a first-class entity.

The stable-ID requirement held. New entities continue to derive their unique IDs from the existing `device_id`, and a runtime unload/reload test now proves that the integration reuses the same Home Assistant device entry instead of creating duplicates.

Writable deep config commands remain intentionally out of scope for this pass. The app binary clearly contains websocket and BLE command names for those settings, but the exact payload contracts were still not strong enough to justify shipping writes for a real door lock.

## Context and Orientation

The integration lives in `custom_components/anona_holo`. The API client is implemented in `custom_components/anona_holo/api.py`. It already logs in to the Anona cloud, fetches devices, polls `getAnonaDeviceStatus`, and decodes the returned protobuf-like `dataHexStr` payload into a `LockStatus` dataclass. The per-device polling state is assembled in `custom_components/anona_holo/coordinator.py`, and the Home Assistant entities are split across `lock.py`, `sensor.py`, `binary_sensor.py`, `switch.py`, and `update.py`.

Stable Home Assistant device identity is currently anchored in `custom_components/anona_holo/entity.py`, where each entity advertises `identifiers={(DOMAIN, device.device_id)}` and each entity unique ID is composed from the device ID plus a stable suffix. Any new entities must keep using that same pattern.

The key reverse-engineering result for this change is that the native app and the status payload agree on several deeper settings. The live app showed:

- `Auto-lock` with `No delay`, `5s`, `10s`, `15s`, `30s`, `1min`, `3min`
- `Sound settings` with `Sound alert` and `Volume` values `High` and `Low`
- `Low power mode`
- `Temporary disable auto-lock` with `Off`, `Always on`, `10 minutes`, `30 minutes`, `1 hour`, and a `Custom` entry

The current implementation already stores the full raw decoded fields on `LockStatus.raw_fields`. That lets us add typed helpers while still keeping the original raw snapshot in lock attributes for debugging.

## Plan of Work

First, update `custom_components/anona_holo/api.py` so `LockStatus` includes typed fields for the confirmed config state. Replace the incorrect `battery_voltage` extraction with an `auto_lock_delay_seconds` field derived from the nested field that changed with the live app, add an `auto_lock_enabled` boolean from the same nested structure, and add `sound_volume_code` plus a human-readable `sound_volume` string from the field that the app logs as `volume: HIGH`. Keep the existing raw field map untouched.

Next, update the entity layers so these settings appear in Home Assistant in a way that matches how much certainty we have. `custom_components/anona_holo/sensor.py` should gain diagnostic/config-style sensors for sound volume and auto-lock delay. `custom_components/anona_holo/binary_sensor.py` should expose the auto-lock enable state if it can be read unambiguously from the status payload. `custom_components/anona_holo/lock.py` should update its extra state attributes to publish the new typed status keys and stop advertising the incorrect battery-voltage-derived field.

Then extend tests. `tests/test_api.py` must prove the new `LockStatus` parsing against both the checked-in fixture payload and the live-observed `5s` payload. `tests/test_platform_entities.py` must assert the new sensor/binary-sensor values and keep unique IDs deterministic. `tests/test_integration_runtime.py` must verify that reloading the config entry does not create duplicate lock devices or duplicate entities when the new entities are added.

Finally, run repo-local validation with the existing `just` entry points and record the exact outcomes here.

## Concrete Steps

From the repository root `/Users/peyton/.codex/worktrees/5a50/homeassistant-anona-holo`, implement and validate with:

    just lint
    just typecheck
    just test

During development, use focused test runs when needed, for example:

    .venv/bin/python -m pytest -q tests/test_api.py tests/test_platform_entities.py tests/test_integration_runtime.py

The acceptance proof for the live reverse-engineering step came from:

    .venv/bin/python - <<'PY'
    import asyncio
    from custom_components.anona_holo.api import AnonaApi
    import aiohttp

    async def main() -> None:
        async with aiohttp.ClientSession() as session:
            api = AnonaApi(session, client_uuid="D294537B-5907-5ECB-92FB-F0C32D3CC82B73")
            await api.login("<redacted>", "<redacted>")
            await api.get_homes()
            device = next(d for d in await api.get_all_devices() if d.device_id == "d3c03cf3fdf641dc90520940d26df688")
            status = await api.get_device_status(device)
            print(status.raw_fields)

    asyncio.run(main())
    PY

The observed output included:

    {'10': {'1': 2}, '11': {'1': 1, '2': 5}, '12': {'1': 0}, ...}

which aligns with the app showing sound volume `High`, auto-lock enabled, auto-lock delay `5s`, and low power mode `Off`.

Final validation commands completed successfully:

    just check

with:

    0 errors, 0 warnings, 0 informations
    51 passed in 0.71s

## Validation and Acceptance

Acceptance is reached when Home Assistant can expose the confirmed config state without duplicate-device regressions:

- `getAnonaDeviceStatus` parsing yields stable typed fields for auto-lock enable, auto-lock delay, sound volume, and low-power mode from the checked-in fixture and the live-observed payload.
- The new entities use deterministic unique IDs based on the existing device ID scheme.
- A config-entry unload/reload cycle leaves one Home Assistant device for the lock and one instance of each entity rather than duplicating them.
- `just lint`, `just typecheck`, and `just test` complete successfully.

## Idempotence and Recovery

These code changes are additive and safe to re-run. If a mapping guess is disproven by a failing test or a later live payload, prefer narrowing the exposed field rather than shipping a broader but uncertain interpretation. Do not change the device identifier scheme or entity unique ID prefixes; those are the recovery boundary that preserves existing Home Assistant state.

## Artifacts and Notes

Most relevant live evidence collected so far:

    Auto-lock before change: app showed `3min`
    Auto-lock after change:  app showed `5s`
    Status field before: {'11': {'1': 1, '2': 180}, ...}
    Status field after:  {'11': {'1': 1, '2': 5}, ...}

    Sound screen after enabling:
    - Sound alert: On
    - Volume picker options: High, Low

    App binary command names:
    - getAutoLock / setAutoLock
    - getSound / setSound
    - getDoorlockLongEndurance / setDoorlockLongEndurance
    - getNormalOpenMode / setNormalOpenMode

Revision note: created this ExecPlan after live protocol investigation because the existing status-field assumptions were no longer trustworthy once deeper settings were verified.
