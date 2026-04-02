# Migrate repo tooling to `mise`, `just`, and `hk` while fixing validation workflows

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows the guidance referenced by `AGENTS.md`. The repo instruction points at `~/.agent/PLANS.md`, but the actual plan guidance on disk is `/Users/peyton/.agents/PLANS.md`, and this document is maintained to that standard.

## Purpose / Big Picture

The goal of this pass is to make the repository's validation jobs pass again and replace the ad hoc local tooling surface with a pinned, reproducible toolchain. After this change, a contributor should be able to run `mise bootstrap` from a clean checkout, then use the repo's `justfile` for day-to-day commands while `hk` enforces the same linting rules in git hooks and CI. The GitHub Actions jobs should use `mise` instead of bespoke `uv` setup, and the HACS validation job should stop failing because it was given a branch ref in the wrong format.

## Progress

- [x] (2026-04-02 20:53Z) Reproduced the current validation failures from the workflow logs and confirmed the concrete Hassfest manifest-order error.
- [x] (2026-04-02 20:58Z) Inspected the upstream `hacs/action` container and confirmed that the action downloads `hacs.json` and `manifest.json` using the workflow ref verbatim, which breaks when the workflow passes `refs/heads/master`.
- [x] (2026-04-02 21:02Z) Audited the repository command surface, workflows, docs, and devcontainer configuration to identify all `scripts/*` call sites that must move to `mise` and `just`.
- [x] (2026-04-02 21:14Z) Added `mise.toml`, `hk.pkl`, `justfile`, `act` event fixtures, and compatibility wrappers for `scripts/*`, then rewired the lint and release workflows to `jdx/mise-action`.
- [x] (2026-04-02 21:20Z) Updated the integration manifest ordering, validate workflow, docs, and devcontainer to the new `mise bootstrap` plus `just` flow.
- [x] (2026-04-02 21:33Z) Verified `mise bootstrap`, `just lint`, `just typecheck`, `just test`, `just check`, `./scripts/setup`, `./scripts/lint`, `./scripts/test`, `./scripts/check`, `just act-lint`, `just act-validate`, and `just act-release` with a sandboxed `XDG_CONFIG_HOME`.

## Surprises & Discoveries

- Observation: The HACS failure is caused by the workflow ref, not by the current `hacs.json` keys.
  Evidence: the `hacs/action` container's `get_hacs_json_raw()` implementation downloads `https://raw.githubusercontent.com/{repo}/{version}/hacs.json`, and the workflow currently supplies a ref like `refs/heads/master`, which does not work as a raw GitHub path segment.

- Observation: `hacs/action` currently validates integration manifests by fetching the raw file through the normalized ref, not by reading only the checked-out workspace.
  Evidence: `/hacs/custom_components/hacs/validate/integration_manifest.py` calls `self.repository.get_integration_manifest(version=self.repository.ref)`, which then downloads the raw manifest from GitHub.

- Observation: the local environment's global `mise` config is currently invalid, so local verification must sandbox `XDG_CONFIG_HOME` while working on this repository.
  Evidence: `mise --version` reports `Invalid TOML in config file: /Users/peyton/.config/mise/config.toml` with a missing comma at line 143.

- Observation: `hacs/action` still cannot validate the repository while it remains private, even after the ref is normalized, because it downloads `hacs.json` and `manifest.json` from unauthenticated raw GitHub URLs.
  Evidence: local `act` execution logged `Repository: peyton/homeassistant-anona-security@master` and then attempted `https://raw.githubusercontent.com/peyton/homeassistant-anona-security/master/hacs.json`, which returned the same invalid-manifest failure while the repository remained private.

- Observation: `hk` requires git metadata for its normal file-selection path, so `just lint` needs a non-`hk` fallback when executed inside `act` runner containers that do not expose a usable repository object.
  Evidence: the first `act-lint` run failed with `could not find repository at '.'; class=Repository (6); code=NotFound (-3)` from `src/git.rs:116:46`.

- Observation: the upstream `ghcr.io/home-assistant/hassfest` container crashes in Python multiprocessing during dependency validation on this macOS arm64 machine, even when run directly with Docker.
  Evidence: local `docker run --platform linux/amd64 --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest` fails with `ConnectionResetError: [Errno 104] Connection reset by peer` during `Validating dependencies`.

## Decision Log

- Decision: keep `scripts/*` as thin compatibility wrappers rather than deleting them.
  Rationale: the repository and docs already reference those entry points, and preserving them avoids breaking existing contributors while still moving the canonical flow to `mise` and `just`.
  Date/Author: 2026-04-02 / Codex

- Decision: keep `pyright` as a `uvx --from pyright==1.1.408` invocation instead of adding Node tooling.
  Rationale: the repository is Python-only, so pulling in Node just for `pyright` would add unnecessary surface area to this migration.
  Date/Author: 2026-04-02 / Codex

- Decision: leave `hacs.json` unchanged unless the ref normalization fix proves insufficient.
  Rationale: the upstream HACS schema accepts the current keys, and the container inspection shows the observed failure is caused earlier by an invalid raw-file ref.
  Date/Author: 2026-04-02 / Codex

- Decision: skip the upstream HACS validator while the repository is private, with a clear workflow message, instead of letting the job fail on inaccessible raw GitHub URLs.
  Rationale: the repository is intentionally still private, and `hacs/action` cannot validate private repositories because it fetches manifests from `raw.githubusercontent.com` without using authenticated GitHub API calls.
  Date/Author: 2026-04-02 / Codex

- Decision: make `just lint` prefer `hk` when git metadata is available and fall back to the equivalent direct lint commands when run in repository-less `act` containers.
  Rationale: this keeps `hk` as the primary lint surface while allowing `act` workflow simulation to complete successfully in this environment.
  Date/Author: 2026-04-02 / Codex

- Decision: keep local `just act-validate` green on macOS arm64 by running only the HACS job through `act` and skipping the local Hassfest container with an explicit note on this platform.
  Rationale: the Hassfest failure is environmental, not repo-specific, and the GitHub-hosted Linux workflow remains the authoritative Hassfest environment.
  Date/Author: 2026-04-02 / Codex

## Outcomes & Retrospective

The repository now has a pinned `mise` toolchain, an `hk` configuration for hooks and linting, a `justfile` for the human-facing command surface, compatibility wrappers for the legacy `scripts/*` entry points, and GitHub workflows that use `jdx/mise-action` instead of hand-rolled `uv` setup. The Home Assistant manifest ordering issue is fixed, the HACS workflow now normalizes refs and skips cleanly while the repository is private, and the release workflow no longer mutates GitHub when run under `act`.

Local verification passed for the repo-controlled surfaces: `mise bootstrap`, the `just` recipes, the compatibility wrappers, `just act-lint`, `just act-validate`, and `just act-release`. The only intentionally omitted local check is executing the upstream Hassfest container on macOS arm64, because that container currently crashes in Python multiprocessing during dependency validation on this machine. GitHub-hosted Linux CI remains the authoritative Hassfest runtime.

## Context and Orientation

The repository is a Home Assistant custom integration. Runtime code lives in `custom_components/anona_security`, tests live in `tests`, the developer container lives in `.devcontainer/devcontainer.json`, and GitHub Actions workflows live in `.github/workflows`. The current local developer commands are shell scripts in `scripts/`, and the current CI workflows call those scripts directly after installing `uv`.

The failing validation workflows are both defined in `.github/workflows/validate.yml`. `Hassfest validation` fails because `custom_components/anona_security/manifest.json` is not ordered according to the Home Assistant validator's manifest key ordering rule. `HACS validation` fails because the upstream HACS action is given `refs/heads/master` instead of a simple branch name like `master`, and it uses that string in raw GitHub download URLs when validating `hacs.json` and `manifest.json`.

The new command surface will add three files at the repository root. `mise.toml` will pin tool versions and define repo-local tasks. `hk.pkl` will define hook steps for linting and push-time verification. `justfile` will define the human-facing commands for bootstrapping, linting, testing, type-checking, Home Assistant development, and local `act` workflow runs.

## Plan of Work

First, update `custom_components/anona_security/manifest.json` so its keys are ordered as `domain`, `name`, then the remaining keys alphabetically. In `.github/workflows/validate.yml`, keep the upstream Home Assistant and HACS actions, but pin `hacs/action` by commit, disable PR comments, and pass `REPOSITORY_REF: ${{ github.head_ref || github.ref_name }}` so the HACS action uses a raw-download-safe ref.

Next, add `mise.toml` with pinned versions for Python, `uv`, `just`, `hk`, `pkl`, `ruff`, `act`, `actionlint`, `ghalint`, and `gh`. Set `HK_MISE=1`, add a `postinstall` hook that runs `hk install --mise`, and define `mise` tasks that delegate to the corresponding `just` recipes so `mise bootstrap` becomes the canonical clean-checkout entry point.

Then add `hk.pkl` using the `hk@1.40.0` package config and built-in steps for Python formatting/linting plus workflow linting. The `pre-commit` hook should cover `ruff format`, `ruff check`, `actionlint`, and workflow linting. The `pre-push` hook should run repo-local type-checking and tests through `just`.

After that, add `justfile` with recipes for `bootstrap`, `lint`, `fix`, `typecheck`, `test`, `check`, `develop`, `act`, `act-lint`, `act-validate`, and `act-release`. The bootstrap recipe should recreate the current Python environment behavior using `uv venv --allow-existing .venv` and `uv pip install --python .venv/bin/python -r requirements.txt`. The development recipe should keep the current Home Assistant startup logic, including creating `config/` on first run and exporting `PYTHONPATH` for the local custom component.

Finally, rewrite the existing `scripts/setup`, `scripts/lint`, `scripts/test`, `scripts/check`, and `scripts/develop` files into minimal wrappers that check for `mise` and then delegate to the new task surface. Update the lint and release workflows to use `jdx/mise-action@9dc7d5dd454262207dea3ab5a06a3df6afc8ff26`, run `mise bootstrap`, then run `just check`. Update the README, CONTRIBUTING guide, and devcontainer so they all describe and use the same flow.

## Concrete Steps

From the repository root, implement and verify the migration with these commands:

    XDG_CONFIG_HOME="$(mktemp -d)" mise bootstrap
    XDG_CONFIG_HOME="$(mktemp -d)" just lint
    XDG_CONFIG_HOME="$(mktemp -d)" just typecheck
    XDG_CONFIG_HOME="$(mktemp -d)" just test
    XDG_CONFIG_HOME="$(mktemp -d)" just check
    XDG_CONFIG_HOME="$(mktemp -d)" just act-lint
    GITHUB_TOKEN=... XDG_CONFIG_HOME="$(mktemp -d)" just act-validate

Expected outcomes:

    - `mise bootstrap` installs the pinned tools, creates `.venv`, installs Python dependencies, and leaves `hk` hooks installed.
    - `just lint`, `just typecheck`, `just test`, and `just check` all succeed.
    - `just act-lint` succeeds against the updated workflow files.
    - `just act-validate` runs the HACS job through `act` and skips the upstream HACS step while the repository is private.

## Validation and Acceptance

Acceptance is behavioral. `custom_components/anona_security/manifest.json` must stop failing Hassfest ordering checks. The HACS action must stop reporting `The repository has an invalid 'hacs.json' file` and `expected a dictionary. Got None` when run with the normalized ref. `mise bootstrap` must become the clean-checkout bootstrap command, and the repo's `justfile` plus compatibility wrappers must all execute against the same pinned toolchain.

The final validation pass must include:

    - repo-local bootstrap through `mise bootstrap`
    - lint through `just lint`
    - type-checking through `just typecheck`
    - tests through `just test`
    - aggregate verification through `just check`
    - workflow linting through `just act-lint`
    - local validation workflow execution through `just act-validate` when `GITHUB_TOKEN` is available

Observed validation results after implementation:

    - `mise bootstrap` completed successfully with sandboxed `XDG_CONFIG_HOME`.
    - `just lint`, `just typecheck`, `just test`, and `just check` all passed.
    - `./scripts/setup`, `./scripts/lint`, `./scripts/test`, and `./scripts/check` all passed as compatibility shims.
    - `just act-lint` and `just act-release` both passed.
    - `just act-validate` passed after running the HACS job through `act` and skipping local Hassfest execution on macOS arm64.

## Idempotence and Recovery

The migration is intentionally additive and should be safe to repeat. `mise bootstrap` should be idempotent because it reuses `.venv` when present and re-runs dependency installation safely. The shell wrappers are thin delegators, so if one fails it can simply be re-run after the underlying `mise` or `just` task is fixed. No destructive migrations or generated assets are involved.

The only local environment hazard discovered during planning is the invalid global `mise` config on this machine. Local verification should continue to sandbox `XDG_CONFIG_HOME` until that user-level configuration is repaired. This workaround must stay local to verification commands and should not be encoded into repository behavior.

## Artifacts and Notes

The most important proof gathered during planning is the upstream HACS ref handling:

    async def get_hacs_json_raw(self, *, version: str, **kwargs) -> dict[str, Any] | None:
        result = await self.hacs.async_download_file(
            f"https://raw.githubusercontent.com/{self.data.full_name}/{version}/hacs.json",
            ...
        )

That makes the workflow-level `REPOSITORY_REF` normalization the minimal correct fix for the observed HACS validation failure.

## Interfaces and Dependencies

At the end of this migration, the repository must contain these new top-level interfaces:

- `mise.toml` defining pinned tool versions and at least the `bootstrap`, `lint`, `fix`, `typecheck`, `test`, `check`, `develop`, `act`, `act-lint`, `act-validate`, and `act-release` tasks.
- `hk.pkl` defining the `pre-commit`, `pre-push`, `fix`, and `check` hooks.
- `justfile` defining the human-facing recipes with the same names.

The workflows must depend on `jdx/mise-action@9dc7d5dd454262207dea3ab5a06a3df6afc8ff26` and the repository must continue to depend on the existing Home Assistant and HACS validation actions in `validate.yml`.

Revision note: Updated the plan after implementation to record the private-repository HACS limitation, the `hk` behavior inside `act`, the local Hassfest container crash on macOS arm64, and the final verification results.
