# AGENTS.md

Repo-specific guidance for AI assistants (Codex, Claude Code, etc.). User-level
defaults live in `~/.codex/AGENTS.md`.

## GitHub Actions

This repo enforces strict Actions hygiene. All of these are enforced either by
GitHub repo settings or Renovate — do not bypass them:

- **SHA-pin every action.** Use the full 40-char commit SHA, not a tag or
  branch. Leave a trailing `# vX.Y.Z` comment so Renovate can track semver.
  GitHub will reject workflow runs with unpinned refs
  (`sha_pinning_required` is on).
- **Allowlist.** New actions must be added to the repo's Actions allowlist
  (`gh api /repos/peyton/homeassistant-anona-holo/actions/permissions/selected-actions`).
  Current allowlist: `actions/*` (GitHub-owned), `home-assistant/*`, `hacs/*`,
  `jdx/*`. Owner-level wildcards are used because GitHub's allowlist matching
  doesn't handle subpath patterns like `home-assistant/actions/hassfest`.
- **Minimal permissions.** Every job must declare `permissions:` explicitly.
  Default to `contents: read`; escalate only the job that needs it.
- **Checkout hygiene.** Always pass `persist-credentials: false` to
  `actions/checkout` unless the job needs to push.
- **`timeout-minutes`.** Every job sets one.
- **No `pull_request_target` with checkout of `github.head_ref`.** If you ever
  need write-scoped triggers on PRs from forks, stop and discuss first — this
  is the most common Actions escape hatch.
- **Don't interpolate `${{ … }}` into `run:`** when the value comes from a PR
  title, branch name, or issue body. Pass it as an `env:` var instead.

## Dependencies

- GitHub Actions and mise patches/minors auto-merge after 3 days (Renovate).
- `homeassistant` pip and mise majors are manual review.

## Commits

- Sign-off required on web edits (`web_commit_signoff_required`).
- Linear history on master; no force-pushes.
