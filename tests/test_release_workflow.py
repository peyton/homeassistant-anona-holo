"""Tests for CalVer release workflow helpers."""

# ruff: noqa: S101

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.release_workflow import (
    ensure_tag_matches_manifest,
    set_manifest_version,
    tag_to_version,
    validate_calver,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_validate_calver_accepts_stable_non_zero_padded_month() -> None:
    """Stable CalVer strings should parse as `YYYY.M.P`."""
    assert validate_calver("2026.4.0") == (2026, 4, 0)


def test_validate_calver_rejects_zero_padded_month() -> None:
    """Zero-padded month strings should fail validation."""
    with pytest.raises(ValueError, match=r"YYYY\.M\.P"):
        validate_calver("2026.04.0")


def test_validate_calver_rejects_prerelease_suffix() -> None:
    """Pre-release suffixes are not allowed for this workflow."""
    with pytest.raises(ValueError, match=r"YYYY\.M\.P"):
        validate_calver("2026.4.0-rc.1")


def test_tag_to_version_requires_v_prefix() -> None:
    """Release tags should use the `vYYYY.M.P` form."""
    with pytest.raises(ValueError, match="must start with `v`"):
        tag_to_version("2026.4.0")


def test_ensure_tag_matches_manifest_detects_mismatch(tmp_path: Path) -> None:
    """Tag and manifest versions should match exactly."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "domain": "anona_holo",
                "name": "Anona Holo",
                "documentation": "https://example.com",
                "issue_tracker": "https://example.com/issues",
                "codeowners": ["@owner"],
                "integration_type": "hub",
                "iot_class": "cloud_polling",
                "requirements": [],
                "version": "2026.4.0",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match manifest version"):
        ensure_tag_matches_manifest("v2026.4.1", manifest_path)


def test_set_manifest_version_updates_version_field(tmp_path: Path) -> None:
    """Manifest version writes should update the version field."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "domain": "anona_holo",
                "name": "Anona Holo",
                "documentation": "https://example.com",
                "issue_tracker": "https://example.com/issues",
                "codeowners": ["@owner"],
                "integration_type": "hub",
                "iot_class": "cloud_polling",
                "requirements": [],
                "version": "2026.4.0",
            }
        ),
        encoding="utf-8",
    )

    changed = set_manifest_version("2026.4.1", manifest_path)

    assert changed is True
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated["version"] == "2026.4.1"
