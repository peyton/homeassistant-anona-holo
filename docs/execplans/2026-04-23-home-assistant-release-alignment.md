# Align `anona_holo` With Current Home Assistant Release Guidance

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows `~/.agents/PLANS.md`; this document must be maintained in accordance with that file while implementation is in progress.

## Purpose / Big Picture

After this change, the custom integration should follow the Home Assistant developer guidance that matters for a release-ready HACS integration: config entries store runtime objects in `ConfigEntry.runtime_data`, credentials can be reauthenticated from the UI, existing entries can be reconfigured from the UI, custom-component translations load correctly from `translations/en.json`, and entities expose translated names instead of hard-coded English strings. A maintainer should be able to prove this by running the repository checks, by exercising the config flow and reauth tests, and by seeing that the integration no longer relies on Core-only `strings.json` behavior.

## Progress

- [x] (2026-04-23 14:52Z) Re-read the relevant Home Assistant developer docs and confirmed the release-alignment gaps: custom integrations must use `translations/<language>.json`, reauth should be available through the UI, runtime objects should live in `ConfigEntry.runtime_data`, and entity translation keys should be preferred over hard-coded names.
- [x] (2026-04-23 14:52Z) Confirmed the repository baseline before mutation: detached checkout at `2dd8396`, matching `origin/master`, with local `just check` and the latest remote `CI` and `Validate` workflows green.
- [x] (2026-04-23 15:16Z) Implemented runtime-data storage, reauth/reconfigure config-flow support, translation-backed entity naming, and release-facing cleanup in the integration code. `entry.runtime_data` now owns the API client, discovered devices, and coordinators; setup/auth failures map to `ConfigEntryNotReady` and `ConfigEntryAuthFailed`; custom-component localization moved to `translations/en.json`; and platform modules now declare explicit `PARALLEL_UPDATES`.
- [x] (2026-04-23 15:16Z) Reorganized and expanded Home Assistant tests under `tests/components/anona_holo/` while keeping repo-script tests at the root. The new tests cover the real flow manager for user/reauth/reconfigure behavior, runtime-data lifecycle, translated entities, and setup/auth failure handling.
- [x] (2026-04-23 15:16Z) Re-ran `just check`, inspected the resulting repository state, and updated this document with the outcome. Verification finished green with `0 errors, 0 warnings, 0 informations` from pyright and `65 passed` from pytest.

## Surprises & Discoveries

- Observation: Home Assistant now documents custom integration localization separately and explicitly warns that `strings.json` is a Core-only build-time feature.
  Evidence: `developers.home-assistant.io/docs/internationalization/custom_integration/` says custom integrations must ship `translations/en.json` and "Do not use `strings.json` for custom components."

- Observation: This checkout is not on a branch even though it is clean and matches `origin/master`.
  Evidence: `git status -b --short` reported `## HEAD (no branch)` before work started, so the implementation is being done on `codex/ha-release-alignment`.

- Observation: Existing local and remote validation are already green, so the remaining work is standards alignment rather than fixing a known failing build.
  Evidence: local `just check` passed with `56 passed in 0.61s`, and GitHub workflow runs `24831290360` (`CI`) and `24831290380` (`Validate`) both succeeded on `master`.

- Observation: `async_config_entry_first_refresh()` can only run while Home Assistant has the entry in `SETUP_IN_PROGRESS`, so direct unit calls to `async_setup_entry()` are no longer a valid way to test coordinator-auth failures.
  Evidence: the first pass of `tests/components/anona_holo/test_init.py` failed with `ConfigEntryError: async_config_entry_first_refresh called when config entry state is NOT_LOADED`; the fix was to assert behavior through `hass.config_entries.async_setup(...)`, which starts reauth and leaves the entry in `SETUP_ERROR`.

- Observation: Pyright is stricter than pytest around config-flow results because `ConfigFlowResult["context"]` is not a required TypedDict key.
  Evidence: `just check` initially failed with `reportTypedDictNotRequiredAccess` in the new reauth-flow assertion, which required guarded `.get(...)` access instead of direct indexing.

## Decision Log

- Decision: Treat this as a release-readiness alignment pass for a custom integration, not a Home Assistant Core contribution.
  Rationale: The repository is a standalone HACS-style custom integration, so the goal is to follow the developer guidance that applies to custom components without adding Core-specific build steps or packaging churn.
  Date/Author: 2026-04-23 / Codex

- Decision: Do not add an options flow in this pass.
  Rationale: The current integration has no account-level optional settings that belong in `ConfigEntry.options`; the writable settings already surface as Home Assistant entities, so an options flow would introduce UI without a real use case.
  Date/Author: 2026-04-23 / Codex

- Decision: Reorganize Home Assistant integration tests into `tests/components/anona_holo/`, but leave repository helper tests like `tests/test_release_workflow.py` and `tests/test_ensure_dev_config.py` at the repository root.
  Rationale: This matches the Home Assistant test-file guidance without mixing integration behavior tests with repository script/unit tests.
  Date/Author: 2026-04-23 / Codex

- Decision: Keep the integration without `services.yaml` or integration-scoped service registrations in this pass.
  Rationale: The Home Assistant services guidance only applies when the integration registers actions under its own domain. `anona_holo` currently exposes device behavior through entity services and does not define custom domain services, so adding `services.yaml` would be empty ceremony.
  Date/Author: 2026-04-23 / Codex

## Outcomes & Retrospective

The integration now follows the current Home Assistant custom-integration guidance that was in scope for release readiness without changing the product surface. Runtime objects moved from `hass.data` into typed `ConfigEntry.runtime_data`, config-entry setup now raises Home Assistant-native retry/auth exceptions, config flow supports reauth and reconfigure, and custom-component localization moved from the old `strings.json` shape into `translations/en.json`. Entity names now come from translation keys for sensors, binary sensors, switches, update entities, and user-facing error messages.

The test tree now matches the documented Home Assistant layout more closely: integration tests live in `tests/components/anona_holo/`, repository helper tests remain at the root, and the new tests exercise the real flow manager and runtime-data lifecycle instead of mostly direct unit calls. A small test-only correction was needed because coordinator first refreshes must run under Home Assistant's setup state machine, and another was needed to satisfy pyright's TypedDict rules for config-flow results.

Final verification on this branch completed with:

    $ just check
    ...
    0 errors, 0 warnings, 0 informations
    ...
    65 passed in 0.44s

Remaining intentionally omitted scope:

- No options flow was added because there is still no clear `ConfigEntry.options` use case.
- No new custom integration services were added because the integration does not register any domain services today.
- No GitHub or release-tag automation changes were needed because the repository checks were already green before the standards-alignment work began.

## Context and Orientation

The runtime integration code lives under `custom_components/anona_holo/`. The entry setup currently happens in `custom_components/anona_holo/__init__.py`, the config flow in `custom_components/anona_holo/config_flow.py`, shared platform behavior in `custom_components/anona_holo/entity.py` and `custom_components/anona_holo/coordinator.py`, and localized strings in the now-outdated `custom_components/anona_holo/strings.json`. The tests currently live in the repository root `tests/` directory, including both Home Assistant integration tests and repository helper tests.

In Home Assistant, a config entry is the saved record that stores integration credentials and other durable configuration. `ConfigEntry.runtime_data` is the in-memory slot attached to one config entry for objects like API clients and coordinators. Reauthentication is the UI path that lets Home Assistant ask the user for fresh credentials after an authentication failure. Reconfiguration is the UI path that lets a user update an existing config entry without creating a new one.

## Plan of Work

First, create a small typed runtime-data container and move all `api`, device, and coordinator objects from `hass.data[DOMAIN][entry_id]` into `entry.runtime_data`. Update `custom_components/anona_holo/__init__.py`, every platform module, `diagnostics.py`, and `system_health.py` to read that typed runtime data instead of the current shared dictionary.

Next, extend `custom_components/anona_holo/config_flow.py` so the flow supports three UI paths: the existing `user` step, a `reauth` plus `reauth_confirm` pair, and a `reconfigure` step. The reauth flow should validate credentials against the existing account, update the config entry, and reload it. The reconfigure flow should update the stored email/password and reload the entry, while refusing to switch the entry to a different normalized account identifier.

Then replace `custom_components/anona_holo/strings.json` with `custom_components/anona_holo/translations/en.json`. The new file should include config-flow strings, reauth/reconfigure success and error messages, entity translation keys, and the existing system-health labels. Update entity descriptions so sensors, binary sensors, switches, and the update entity use translation keys instead of hard-coded names. Keep the main lock entity as the device’s primary entity with the device name.

After that, remove the unnecessary custom `aiohttp` requirement from `custom_components/anona_holo/manifest.json`, add explicit `PARALLEL_UPDATES` declarations for platform modules, and reduce lock extra state attributes so raw payload dumps and timestamp churn are no longer mirrored on the lock state when dedicated sensors, binary sensors, and diagnostics already exist.

Finally, move the Home Assistant integration tests into `tests/components/anona_holo/`, expand them to cover the new flow-manager behavior and runtime-data usage, and run the repository validation commands from the repository root.

## Concrete Steps

Work from the repository root `/Users/peyton/.codex/worktrees/e6c8/homeassistant-anona-holo`.

1. Create a branch for the work.

       git switch -c codex/ha-release-alignment

   Expected result: Git reports that it switched to the new branch.

2. Implement the runtime-data, config-flow, translation, and platform changes in `custom_components/anona_holo/`.

3. Reorganize and expand the integration tests under `tests/components/anona_holo/`.

4. Run the full repository checks.

       just check

   Expected result: lint passes, pyright reports `0 errors`, and pytest reports all tests passed.

5. Inspect the final diff and repository status.

       git status --short
       git diff --stat

## Validation and Acceptance

Acceptance is met when all of the following are true:

`just check` passes from a clean repository checkout. The new config-flow tests prove the UI flow manager can create an entry, reject duplicate accounts, reauthenticate an entry after an auth problem, and reconfigure an existing entry without creating a duplicate. The runtime tests prove that `entry.runtime_data` is populated during setup, used by diagnostics and system health, and released during unload. Translation-backed entity tests prove that coordinator-backed entities now advertise translation keys instead of relying on hard-coded English names. The manifest no longer declares `aiohttp`, and the repository no longer contains `custom_components/anona_holo/strings.json`.

## Idempotence and Recovery

The code and test edits are ordinary repository changes and can be applied repeatedly as long as the tests stay green. If a test move or translation conversion fails midway, rerun `git status --short` to identify incomplete renames and continue until the final tree is coherent. `just check` is the authoritative retry command; if it fails after a partial edit, fix the reported issue and rerun the same command.

## Artifacts and Notes

Important baseline evidence gathered before implementation:

    $ git rev-parse HEAD
    2dd83965fb334a9875fae92da72f8b47aaa3f7bf

    $ git rev-parse origin/master
    2dd83965fb334a9875fae92da72f8b47aaa3f7bf

    $ just check
    ...
    56 passed in 0.61s

Important docs driving this change:

    - Custom integration localization now requires translations/en.json.
    - Config flows reserve reauth and reconfigure steps for existing-entry repair/update.
    - Quality Scale guidance prefers ConfigEntry.runtime_data and explicit PARALLEL_UPDATES.

## Interfaces and Dependencies

Define a typed runtime-data object in the integration package that contains the `AnonaApi` instance, the discovered lock devices keyed by device id, and the per-device `AnonaDeviceCoordinator` instances keyed by device id. `async_setup_entry` must assign that object to `entry.runtime_data`, and `async_unload_entry` must leave the entry without runtime data.

`custom_components/anona_holo/config_flow.py` must expose `async_step_user`, `async_step_reauth`, `async_step_reauth_confirm`, and `async_step_reconfigure`. The reauth and reconfigure flows must finish by calling `self.async_update_reload_and_abort(...)` on the existing entry instead of creating a new entry.

Each coordinator-backed entity platform should expose a module-level `PARALLEL_UPDATES` integer and entity descriptions with translation keys so Home Assistant can localize names from `custom_components/anona_holo/translations/en.json`.

Revision note (2026-04-23): Created this plan at implementation start so the repository contains a self-contained record of the release-alignment scope, baseline evidence, and acceptance criteria before any code changes.
