# Port `integration_blueprint` to the `anona_holo` lock-only behavior

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows the instructions in [AGENTS.md](/Users/peyton/ghq/github.com/peyton/homeassistant-anona-security/AGENTS.md), which require complex integration work to be executed and documented through an ExecPlan that is maintained during implementation.

## Purpose / Big Picture

After this change, `custom_components/integration_blueprint` behaves like the working `custom_components/anona_holo` integration instead of the template scaffold. A Home Assistant user can add the integration with Anona credentials, discover only lock devices, and lock or unlock the device while periodic polling updates entity state. The observable proof is a successful config flow, a lock entity created from the returned device list, and passing focused tests that exercise config flow validation and lock command/state behavior.

## Progress

- [x] (2026-03-27 21:23Z) Read the repository instructions, the current template integration, and the reference `custom_components/anona_holo` implementation.
- [x] (2026-03-27 21:23Z) Decided to keep the package and manifest domain as `integration_blueprint` while porting runtime behavior from `anona_holo`.
- [x] (2026-03-27 21:28Z) Replaced the template runtime modules with the lock-only Anona implementation and added `custom_components/integration_blueprint/lock.py`.
- [x] (2026-03-27 21:28Z) Removed scaffold-only entity/coordinator/data modules and aligned the manifest and translations to the lock-oriented flow.
- [x] (2026-03-27 21:33Z) Added focused tests for config flow creation, invalid auth, duplicate email aborts, lock state mapping, lock/unlock dispatch, and lock-device filtering during setup.
- [x] (2026-03-27 21:35Z) Ran `ruff check custom_components/integration_blueprint tests`, `pyright --pythonpath .venv/bin/python custom_components/integration_blueprint tests`, and `.venv/bin/python -m pytest`.
- [ ] Run a live Home Assistant smoke test with real Anona credentials through `scripts/develop` and confirm entity creation and lock/unlock behavior end to end.

## Surprises & Discoveries

- Observation: The repo instruction points to `~/.agent/PLANS.md`, but the actual plan document on disk is `/Users/peyton/.agents/PLANS.md`.
  Evidence: `sed` on `~/.agent/PLANS.md` failed with “No such file or directory”; `find ~ -maxdepth 3 -name 'PLANS.md'` returned `/Users/peyton/.agents/PLANS.md`.

- Observation: The repository has no existing `docs/` directory, `tests/` tree, or root `pyproject.toml`.
  Evidence: `find docs -maxdepth 3 -type f` failed because `docs` did not exist; `find . -maxdepth 3 -type f \( -path './tests/*' -o -path './custom_components/*test*' \)` returned no tests; `sed -n '1,260p' pyproject.toml` failed because the file does not exist.

- Observation: The base environment did not have the `homeassistant` package installed, so both tests and `pyright` import resolution required a repository-local virtual environment.
  Evidence: `python -c "import homeassistant"` failed with `ModuleNotFoundError`; after `UV_CACHE_DIR=/tmp/uv-cache uv venv .venv` and `uv pip install --python .venv/bin/python -r requirements.txt`, the validation commands succeeded.

## Decision Log

- Decision: Treat the user-supplied implementation request as the approved design and convert it into this checked-in ExecPlan instead of re-running a separate design cycle.
  Rationale: The user explicitly asked to “IMPLEMENT THIS PLAN” and then asked to “keep going”, so the correct behavior is to execute the provided plan while still satisfying the repo requirement to maintain an ExecPlan.
  Date/Author: 2026-03-27 / Codex

- Decision: Keep the integration identity as `integration_blueprint` instead of renaming the package or Home Assistant domain to `anona_holo`.
  Rationale: The request is to make `custom_components/integration_blueprint` match `custom_components/anona_holo`; changing the folder and domain would expand scope into a repository rename rather than a behavior port.
  Date/Author: 2026-03-27 / Codex

- Decision: Add `pytest==9.0.2` to `requirements.txt`.
  Rationale: The repository now has a real `tests/` tree and the validation command is `python -m pytest`, so the test runner must be part of the declared setup dependencies instead of relying on a preinstalled global tool.
  Date/Author: 2026-03-27 / Codex

## Outcomes & Retrospective

The intended outcome was a minimal behavior port, not a broader repository rename or API redesign, and that outcome was achieved. `custom_components/integration_blueprint` is now a lock-only Anona integration with the same runtime model as `custom_components/anona_holo`: setup re-authenticates and stores an `AnonaApi` instance, the config flow validates and stores Anona credentials plus returned identifiers, and the lock platform filters devices to supported lock hardware and issues lock or unlock commands through the API client.

The repo now also has a focused `tests/` surface that proves the behavior most likely to regress during future edits. Automated validation passed with `ruff`, `pyright`, and `pytest` in a repository-local virtual environment. The remaining gap against the original plan is the live Home Assistant smoke test with real credentials, which was not run because no credentials or running dev session were available in this task.

## Context and Orientation

The source integration that currently works lives under `custom_components/anona_holo`. Its core files are `__init__.py`, `api.py`, `config_flow.py`, `const.py`, `lock.py`, `manifest.json`, and `strings.json`. That implementation is lock-only: it logs in to the Anona API, stores the API client in `hass.data[DOMAIN][entry.entry_id]`, forwards only the `lock` platform, filters devices to lock hardware, and exposes lock and unlock actions through a WebSocket command channel.

The target integration that currently needs porting lives under `custom_components/integration_blueprint`. Right now it is still the standard Home Assistant template scaffold. Its `__init__.py` depends on `coordinator.py`, `data.py`, and `entity.py`. It also exposes `sensor.py`, `binary_sensor.py`, and `switch.py`, all of which are template-only behavior that must be removed. Its `api.py` points at JSONPlaceholder, and its `config_flow.py` still uses `username` and `slugify` instead of the Anona credential flow.

In this repository, a “config flow” means the Home Assistant UI form that collects credentials and creates a config entry. A “config entry” means the stored Home Assistant record containing integration data such as email, password, and tokens. A “platform” means the Home Assistant entity type that gets loaded from a config entry, in this case only `lock`.

## Plan of Work

First, replace `custom_components/integration_blueprint/const.py` with the Anona constants, keeping only the domain string changed to `integration_blueprint`. Then replace `custom_components/integration_blueprint/api.py` with the Anona API client shape: HTTP helpers, login, device discovery, status polling, WebSocket command dispatch, and convenience methods for lock state, online state, and battery extraction.

Next, replace `custom_components/integration_blueprint/__init__.py` so it becomes lock-only. It must create `AnonaApi` with the Home Assistant aiohttp session, re-login using stored credentials during setup, store the API instance in `hass.data[DOMAIN][entry.entry_id]`, forward only the `lock` platform, and unload cleanly.

Then replace `custom_components/integration_blueprint/config_flow.py` with an email-and-password flow that validates credentials through `api.login`, prevents duplicate entries by normalized lowercase email, and stores `email`, `password`, `access_token`, `user_id`, and `home_id`. Add `custom_components/integration_blueprint/lock.py` so it discovers devices through `api.get_devices`, keeps only devices whose `deviceType` matches the Anona lock type, creates stable unique IDs and names, and exposes lock state, availability, and lock/unlock actions.

After the runtime port is complete, delete the template-only modules `binary_sensor.py`, `sensor.py`, `switch.py`, `coordinator.py`, `entity.py`, and `data.py`. Update `custom_components/integration_blueprint/manifest.json` to the lock-oriented metadata and requirements used by the Anona integration, while preserving the target domain. Replace `custom_components/integration_blueprint/translations/en.json` with `custom_components/integration_blueprint/strings.json` using the Anona key layout, then remove the old translation file.

Finally, add a new `tests/` tree with focused unit-style tests. The tests must cover successful config flow creation, duplicate email prevention, lock entity state mapping from device status, and command dispatch for lock and unlock using mocked API objects. When those are in place, run repo-local validation commands and record the results in this document.

## Concrete Steps

Work from the repository root `/Users/peyton/ghq/github.com/peyton/homeassistant-anona-security`.

Write and edit the integration files, then run:

    ruff check custom_components/integration_blueprint tests
    pyright custom_components/integration_blueprint tests
    python -m pytest

The commands that were run during implementation were:

    UV_CACHE_DIR=/tmp/uv-cache uv venv .venv
    UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -r requirements.txt
    ruff check custom_components/integration_blueprint tests
    pyright --pythonpath .venv/bin/python custom_components/integration_blueprint tests
    .venv/bin/python -m pytest

## Validation and Acceptance

Acceptance is reached when the following behavior is demonstrable:

`custom_components/integration_blueprint` loads only a `lock` platform from a config entry, not sensors, switches, or binary sensors. The config flow accepts valid Anona credentials, rejects invalid credentials, and aborts a second entry for the same lowercase email. The lock entity setup filters out non-lock devices, uses the device status response to compute `is_locked`, availability, and battery attributes, and issues lock or unlock commands against the mocked API object. The validation commands in `Concrete Steps` now complete successfully. The only remaining acceptance item is a manual smoke test through Home Assistant with real credentials.

## Idempotence and Recovery

The file edits are additive or replace template files in place, so they are safe to re-run as long as the same target behavior is preserved. If validation fails after a partial edit, re-run the relevant command after fixing the failing file; there is no destructive migration or generated artifact to clean up beyond normal Python caches. If Home Assistant local runtime smoke testing is attempted later, it should be done through the existing `scripts/develop` entry point so the repository layout remains intact.

## Artifacts and Notes

Initial evidence gathered before implementation:

    git status --short
    ?? custom_components/anona_holo/

    python -m pytest --version
    pytest 9.0.2

    pyright --version
    pyright 1.1.408

Validation evidence after implementation:

    ruff check custom_components/integration_blueprint tests
    All checks passed!

    pyright --pythonpath .venv/bin/python custom_components/integration_blueprint tests
    0 errors, 0 warnings, 0 informations

    .venv/bin/python -m pytest
    collected 6 items
    tests/test_config_flow.py ...                                            [ 50%]
    tests/test_lock.py ...                                                   [100%]
    6 passed, 1 warning in 0.48s

## Interfaces and Dependencies

At the end of the port, `custom_components/integration_blueprint/api.py` must define:

    class AnonaApi:
        async def login(self, email: str, password: str) -> dict[str, Any]: ...
        async def get_homes(self) -> list[dict]: ...
        async def get_devices(self, home_id: str | None = None) -> list[dict]: ...
        async def get_device_status(self, device_id: str) -> dict: ...
        async def lock(self, device_id: str) -> None: ...
        async def unlock(self, device_id: str) -> None: ...
        async def ws_get_status(self, device_id: str) -> dict | None: ...
        def is_locked(self, status: dict) -> bool: ...
        def is_online(self, status: dict) -> bool: ...
        def battery_level(self, status: dict) -> int | None: ...

`custom_components/integration_blueprint/__init__.py` must expose `PLATFORMS = [Platform.LOCK]` and define `async_setup_entry` and `async_unload_entry` that store and remove `AnonaApi` instances from `hass.data[DOMAIN]`.

`custom_components/integration_blueprint/config_flow.py` must define a Home Assistant `ConfigFlow` subclass for `DOMAIN` that asks for `email` and `password`, normalizes the unique ID with `email.lower()`, and stores `access_token`, `user_id`, and `home_id` in the created entry.

`custom_components/integration_blueprint/lock.py` must define `async_setup_entry(...)` and a `LockEntity` subclass that reads from `AnonaApi`.

This integration depends on `aiohttp` for HTTP and WebSocket access, `websockets` in manifest requirements for parity with the target integration metadata, and Home Assistant’s built-in config entry, lock entity, and aiohttp client helpers.

Change note: 2026-03-27. Created this ExecPlan from the user-provided implementation plan so repository-required progress, decisions, and validation can be tracked during the port.
Change note: 2026-03-27. Updated progress, discoveries, decisions, and validation results after completing the port and automated test pass; recorded that a live credential-backed smoke test remains outstanding.
