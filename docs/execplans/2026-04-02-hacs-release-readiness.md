# Prepare `anona_security` For HACS Release

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current while the release-readiness work proceeds.

## Purpose / Big Picture

The goal of this pass is to make the repository release-ready for HACS distribution rather than only locally functional. That means the integration metadata should match current Home Assistant and HACS expectations, the repo should contain local brand assets instead of HACS validation ignores, the GitHub workflows should validate the actual default branch and release path, and scratch files should be kept out of the repository surface.

## Progress

- [x] (2026-04-02 18:55Z) Audited the current repo surface, issue templates, scripts, workflows, manifest metadata, and ignored files against the current Home Assistant integration file-structure docs and HACS docs.
- [x] (2026-04-02 19:02Z) Confirmed the release-facing gaps: stale template links, no local brand assets, workflow triggers targeting `main` while the repo default branch is `master`, no tag-driven GitHub release workflow, and repo-local scripts that were still template-grade.
- [x] (2026-04-02 19:10Z) Updated the manifest, HACS metadata, README, CONTRIBUTING guide, issue templates, and repo-local scripts for a HACS-facing release surface.
- [x] (2026-04-02 19:13Z) Added local brand assets under `custom_components/anona_security/brand/` from the installed Anona app icon and removed the HACS workflow `ignore: brands` shortcut.
- [x] (2026-04-02 19:17Z) Added a tag-driven GitHub release workflow, fixed the CI and validation workflows to follow both `master` and `main`, and switched the workflows to the repo-local scripts.
- [x] (2026-04-02 19:20Z) Cleaned scratch directories and transient local work files from the repository root, keeping only ignored Home Assistant runtime state under `config/`.
- [x] (2026-04-02 19:24Z) Rebuilt the local environment against `homeassistant==2026.3.4`, reran lint, type-checking, tests, YAML workflow parsing, and a final git-state sanity pass.

## Surprises & Discoveries

- Observation: The GitHub repository default branch is `master`, but the existing workflows only triggered on `main`.
  Evidence: `gh repo view --json defaultBranchRef` returned `{"defaultBranchRef":{"name":"master"}}`.

- Observation: The repo was still carrying template-era issue links and script behavior even though the integration code had already been fully migrated.
  Evidence: the bug and feature templates linked to `ludeeus/integration_blueprint`, and `scripts/develop` still referenced the template comment path and had an invalid shebang.

- Observation: The local Anona macOS bundle already contains usable app icon assets, so the repo did not need synthetic release branding.
  Evidence: `/Applications/Anona Security.app/Wrapper/Anona.app/Annoa76x76@2x~ipad.png` exists and was copied into the integration `brand/` directory for HACS and Home Assistant branding.

- Observation: The repository is still private even though the release surface is now HACS-ready.
  Evidence: `gh repo view --json visibility` returned `"visibility":"PRIVATE"` after the metadata pass.

## Decision Log

- Decision: Add local integration brand assets and remove the HACS workflow brands ignore instead of keeping the validation bypass.
  Rationale: the Home Assistant docs now support local `brand/` assets for custom integrations, and a release-ready repository should validate cleanly without HACS ignores.
  Date/Author: 2026-04-02 / Codex

- Decision: Keep the GitHub release flow repo-local and shell-based with `gh release create`.
  Rationale: this avoids adding another third-party action just to publish releases and keeps the release path aligned with the same repo-local setup, lint, type, and test steps used elsewhere.
  Date/Author: 2026-04-02 / Codex

## Outcomes & Retrospective

This pass was aimed at release discipline, not protocol changes. The repo now has HACS-facing metadata, local brand assets, updated issue templates, repo-local setup/lint/test scripts, CI and validation workflows that match the actual default branch, and a tag-driven GitHub release workflow. Final verification passed after upgrading the local toolchain pin to `homeassistant==2026.3.4`.

The remaining non-code steps are external to the repository contents: the repository must be made public and a real release tag such as `v0.3.0` must be pushed before HACS can consume it as a public release artifact.
