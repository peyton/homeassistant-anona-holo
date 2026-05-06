# Clear Renovate PRs and Cut the May 2026 Release

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository follows `/Users/peyton/.agents/PLANS.md`; this document is maintained to that standard.

## Purpose / Big Picture

The repository has three open Renovate pull requests that each update one member of the Home Assistant test dependency stack. They fail because `pytest-homeassistant-custom-component` intentionally pins the exact `homeassistant` and `pytest` versions that match the generated Home Assistant test fixtures. After this work, those pull requests should be merged or otherwise resolved, future Renovate runs should stop opening unsatisfiable one-off `homeassistant` or `pytest` PRs, master should be green, and a new GitHub release should exist.

## Progress

- [x] (2026-05-06T22:08Z) Confirmed the open pull requests are #47, #25, and #50, and that each failed during `mise bootstrap` dependency resolution.
- [x] (2026-05-06T22:08Z) Confirmed from PyPI metadata that `pytest-homeassistant-custom-component==0.13.325` pins `homeassistant==2026.4.4` and `pytest==9.0.0`.
- [x] (2026-05-06T22:11Z) Refreshed stale `mise.lock` tool entries and configured CI/Release to run `mise install --locked` through `jdx/mise-action`.
- [x] (2026-05-06T22:17Z) Updated PR #47 so it removes the direct `homeassistant` pin, moves the test helper to `0.13.325`, and hardens mise lockfile enforcement.
- [x] (2026-05-06T22:18Z) Updated PR #25 so it removes the direct `pytest` pin and adds a regression test for the dependency policy.
- [ ] Update PR #50 so it moves the helper to the Renovate-proposed `0.13.326`, which supplies `pytest==9.0.3` and its matching Home Assistant stack.
- [ ] Run local validation for each updated branch and push it. Completed for PR #47 and PR #25; PR #50 remains.
- [ ] Monitor GitHub checks for the updated PRs, merge them once green, and verify master remains green.
- [ ] Cut and verify the next CalVer release after master is green.

## Surprises & Discoveries

- Observation: the individual Renovate PRs are not independently satisfiable because the helper package pins Home Assistant Core and pytest exactly.
  Evidence: PR #47 failed with `pytest-homeassistant-custom-component==0.13.324 depends on homeassistant==2026.4.3`; PR #25 failed because the same helper depends on `pytest==9.0.0`; PR #50 failed because helper `0.13.326` depends on `homeassistant==2026.5.0b0`.
- Observation: master also had stale `mise.lock` entries for tool bumps that CI did not catch.
  Evidence: `mise.toml` pinned `uv==0.11.8`, `hk==1.44.3`, `ruff==0.15.12`, `act==0.2.88`, `ghalint==1.5.6`, and `gh==2.92.0`, while `mise.lock` still contained the previous versions. Running `mise lock` pruned six stale version entries.
- Observation: updating PR #25 after #47 merged caused a direct conflict in `requirements.txt`.
  Evidence: the PR branch wanted `pytest==9.0.3` with helper `0.13.324`, while master had already moved the helper to `0.13.325` and removed the direct Home Assistant pin.

## Decision Log

- Decision: treat `homeassistant` and `pytest` as transitive dependencies of `pytest-homeassistant-custom-component` instead of direct pins in `requirements.txt`.
  Rationale: the helper package is generated from Home Assistant Core and already publishes the exact test stack. Direct pins let Renovate create single-package updates that the resolver cannot satisfy.
  Date/Author: 2026-05-06 / Codex
- Decision: enforce `mise.lock` in CI and Release by passing `install_args: "--locked"` to `jdx/mise-action`.
  Rationale: this makes the lockfile an actual contract instead of documentation, so future Renovate tool bumps cannot pass CI while leaving `mise.lock` stale.
  Date/Author: 2026-05-06 / Codex

## Outcomes & Retrospective

Work is in progress.

- 2026-05-06T22:17Z: PR #47 passed local `mise install --locked`, `mise bootstrap`, and `just check`; pytest reported 69 passed.
- 2026-05-06T22:18Z: PR #25 conflict was resolved by keeping the helper-managed stack and adding `tests/test_dependency_policy.py`.
- 2026-05-06T22:22Z: PR #25 passed local `just check`; pytest reported 70 passed.

## Context and Orientation

`requirements.txt` is the repository's Python dependency input. `just bootstrap` creates `.venv` and installs that file through `uv pip install --python .venv/bin/python -r requirements.txt`. The CI job named `Quality checks` runs `mise bootstrap` and then `just check`, so dependency resolution failures stop the job before lint, typecheck, or tests can run.

`pytest-homeassistant-custom-component` is a test helper package for Home Assistant custom integrations. It depends on the exact Home Assistant Core and pytest versions used to generate its fixtures. In this repository, direct `homeassistant` and `pytest` pins conflict with that helper whenever Renovate updates only one of the three.

## Plan of Work

Update the three open Renovate branches in dependency order. PR #47 should remove the direct Home Assistant pin, bump the helper to the version that supplies Home Assistant `2026.4.4`, refresh `mise.lock`, and make Actions enforce locked tool installs. PR #25 should remove the direct pytest pin and add a repository test that fails if direct `homeassistant` or `pytest` pins are reintroduced. PR #50 should bump only `pytest-homeassistant-custom-component` to `0.13.326`, letting that package supply pytest `9.0.3` and its matching Home Assistant stack.

After each branch is pushed, monitor the PR's required checks. Merge only green PRs, then verify master checks. When master is green, choose the next CalVer version using the README release policy, run the release command from a clean master checkout, and verify the tag and GitHub release.

## Concrete Steps

Work from `/tmp/homeassistant-anona-holo-prs`, a fresh clone of `https://github.com/peyton/homeassistant-anona-holo`.

For PR #47:

    git switch renovate/homeassistant-2026.x
    edit requirements.txt
    mise bootstrap
    just check
    git commit -m "fix(deps): align homeassistant test stack"
    git push origin renovate/homeassistant-2026.x

Observed local validation for PR #47:

    0 errors, 0 warnings, 0 informations
    69 passed in 0.84s

Repeat the same branch-local pattern for PR #25 and PR #50, adapting the files described in the plan.

For PR #25, the expected local test count increases by one because `tests/test_dependency_policy.py` asserts that `homeassistant` and `pytest` remain transitive through `pytest-homeassistant-custom-component`.

Observed local validation for PR #25:

    0 errors, 0 warnings, 0 informations
    70 passed in 0.79s

## Validation and Acceptance

Each updated pull request must pass `Quality checks`, `Hassfest validation`, `HACS validation`, and CodeQL. The local command `just check` should pass before pushing each branch. After merging, master should have successful CI and Validate workflow runs. The release is accepted when `gh release view v<version>` succeeds and the tag points at the intended release commit.

## Idempotence and Recovery

The dependency edits are text changes and can be repeated safely. If a PR branch falls behind master, update it with an actual merge from `origin/master` unless the user explicitly asks for a rebase. If the local linked worktree cannot fetch, use the fresh clone or GitHub API evidence rather than mutating shared worktree metadata.

## Artifacts and Notes

The core dependency metadata observed during this work is:

    pytest-homeassistant-custom-component 0.13.324 -> homeassistant 2026.4.3, pytest 9.0.0
    pytest-homeassistant-custom-component 0.13.325 -> homeassistant 2026.4.4, pytest 9.0.0
    pytest-homeassistant-custom-component 0.13.326 -> homeassistant 2026.5.0b0, pytest 9.0.3

## Interfaces and Dependencies

The maintained dependency contract is that `requirements.txt` directly pins `pytest-homeassistant-custom-component` and does not directly pin `homeassistant` or `pytest`. The helper package remains the interface for choosing the Home Assistant test stack.

Revision note: Initial plan created while repairing the May 2026 Renovate PR set.

Revision note: Recorded PR #47 dependency, lockfile, and local validation work.

Revision note: Recorded PR #25 conflict resolution and dependency policy test.

Revision note: Recorded PR #25 local validation after replacing bare asserts with explicit pytest failures.
