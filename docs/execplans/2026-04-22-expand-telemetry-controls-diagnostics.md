# Expand `anona_holo` Telemetry, Controls, and Diagnostics

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are kept current for this implementation pass.

## Purpose / Big Picture

The lock-only integration should expose useful operational telemetry and controls that the Anona API already provides, without overwhelming users with noisy raw data by default. This pass introduces a shared per-device coordinator, new Home Assistant platforms (`sensor`, `binary_sensor`, `switch`, `update`), and config-entry diagnostics with strict redaction while preserving existing lock behavior.

## Progress

- [x] (2026-04-22 21:40Z) Confirmed live payload contracts for `getDeviceInfo`, `getDeviceSwitch`, `getDeviceSwitchListByHomeId`, and `checkNewRomFromApp`; validated field mappings against native app UI.
- [x] (2026-04-22 22:05Z) Extended `anona_holo.api` with typed contexts (`DeviceInfoContext`, `DeviceSwitchSettings`, `FirmwareUpdateContext`) and write APIs (`updateDeviceSwitch`, `setSilentOTA`) plus firmware version availability helper logic.
- [x] (2026-04-22 22:22Z) Implemented `AnonaDeviceCoordinator` with fast polling (online/status) and slower detail polling (device info, switches, firmware), including stale-detail fallback behavior.
- [x] (2026-04-22 22:43Z) Refactored lock entity to coordinator-backed state and expanded setup to include `sensor`, `binary_sensor`, `switch`, and `update` platforms.
- [x] (2026-04-22 22:50Z) Added config-entry diagnostics exporter with recursive redaction for IDs, credentials, network identifiers, and cert/key-like fields.
- [x] (2026-04-22 23:10Z) Added and updated tests for API normalization/write payloads, coordinator refresh/stale handling, new platform mappings/writes, diagnostics redaction, and lock regression coverage.
- [x] (2026-04-22 23:16Z) Ran repository validation: `just lint`, `just typecheck`, `just test`.

## Surprises & Discoveries

- Observation: `getDeviceInfo` exposes firmware and silent OTA settings directly, including `softwareVersionNumber`, `silentOTA`, and JSON `silentOTATime`.
  Evidence: live probe response keys from `/anona/device/api/getDeviceInfo`.

- Observation: firmware check payload uses fields `version`, `subVersion`, `newVersion`, `desc`, and `fileUrl` rather than the earlier guessed `newVerNum` style fields.
  Evidence: live probe response from `/versionApi/V3/checkNewRomFromApp`.

- Observation: Home Assistant type stubs report coordinator/entity `available` incompatibilities across multiple entity mixins; targeted pyright ignores are required for these known stub conflicts.
  Evidence: `just typecheck` failures before class-level pyright ignores.

## Decision Log

- Decision: Use a per-device coordinator with dual cadence in one update method rather than separate coordinators per endpoint family.
  Rationale: this keeps all platform entities for a device consistent on one snapshot while still reducing API load for slower detail endpoints.
  Date/Author: 2026-04-22 / Codex

- Decision: Keep raw/noisy telemetry diagnostic entities disabled by default while enabling core states by default.
  Rationale: aligns with Home Assistant expectations for actionable defaults and the requested balance between usability and diagnostics depth.
  Date/Author: 2026-04-22 / Codex

- Decision: Exclude unresolved event-history endpoints in this pass.
  Rationale: live probing did not produce stable payload contracts; safer to defer than ship brittle parsing.
  Date/Author: 2026-04-22 / Codex

## Outcomes & Retrospective

The integration now exposes battery, health, and firmware telemetry plus writable notification/silent-OTA controls while preserving lock command behavior and using shared coordinator snapshots across platforms. Diagnostics are exportable with redaction safeguards. Test coverage was expanded for API payload normalization, coordinator behavior, platform mapping/writes, and diagnostics.

The intentionally deferred scope remains event-history entities and any live-write behavioral validation that toggles real account settings.
