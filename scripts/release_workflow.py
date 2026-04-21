"""Release workflow helpers for CalVer tagging and manifest validation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

MANIFEST_PATH = Path("custom_components/anona_holo/manifest.json")
CALVER_PATTERN = re.compile(
    r"^(?P<year>\d{4})\.(?P<month>[1-9]|1[0-2])\.(?P<patch>0|[1-9]\d*)$"
)


def validate_calver(version: str) -> tuple[int, int, int]:
    """Validate and parse a stable CalVer string (`YYYY.M.P`)."""
    match = CALVER_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(
            "Version must use stable CalVer format `YYYY.M.P`"
            " with a non-zero-padded month."
        )
    return int(match["year"]), int(match["month"]), int(match["patch"])


def tag_to_version(tag: str) -> str:
    """Extract and validate the version from a release tag (`vYYYY.M.P`)."""
    if not tag.startswith("v"):
        raise ValueError("Tag must start with `v` (for example `v2026.4.0`).")
    version = tag[1:]
    validate_calver(version)
    return version


def read_manifest_version(manifest_path: Path = MANIFEST_PATH) -> str:
    """Read and validate the integration manifest version."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{manifest_path} is missing a string `version` field.")
    validate_calver(version)
    return version


def set_manifest_version(version: str, manifest_path: Path = MANIFEST_PATH) -> bool:
    """Set the manifest version and keep key ordering stable."""
    validate_calver(version)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_version = manifest.get("version")
    if current_version == version:
        return False

    manifest["version"] = version
    ordered_manifest = {
        "domain": manifest["domain"],
        "name": manifest["name"],
        **{k: v for k, v in sorted(manifest.items()) if k not in ("domain", "name")},
    }
    manifest_path.write_text(
        json.dumps(ordered_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def ensure_tag_matches_manifest(tag: str, manifest_path: Path = MANIFEST_PATH) -> str:
    """Validate that a release tag version exactly matches manifest version."""
    tag_version = tag_to_version(tag)
    manifest_version = read_manifest_version(manifest_path)
    if tag_version != manifest_version:
        raise ValueError(
            f"Release tag `{tag}` does not match manifest version `{manifest_version}`."
        )
    return manifest_version


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Helpers for validating and cutting CalVer releases."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_version = subparsers.add_parser(
        "validate-version",
        help="Validate a stable CalVer version string (`YYYY.M.P`).",
    )
    validate_version.add_argument(
        "--version", required=True, help="Version to validate."
    )

    validate_tag_manifest = subparsers.add_parser(
        "validate-tag-manifest",
        help="Validate `vYYYY.M.P` tag format and require tag==manifest version.",
    )
    validate_tag_manifest.add_argument(
        "--tag", required=True, help="Git tag to validate."
    )
    validate_tag_manifest.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Path to the integration manifest file.",
    )

    set_manifest = subparsers.add_parser(
        "set-manifest-version",
        help="Set `manifest.json` version to a stable CalVer string.",
    )
    set_manifest.add_argument("--version", required=True, help="Version to write.")
    set_manifest.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Path to the integration manifest file.",
    )

    return parser.parse_args(argv)


def _run_command(args: argparse.Namespace) -> tuple[int, str | None]:
    """Run the selected command and return exit status and optional error."""
    if args.command == "validate-version":
        validate_calver(args.version)
        return 0, None

    if args.command == "validate-tag-manifest":
        ensure_tag_matches_manifest(args.tag, args.manifest)
        return 0, None

    if args.command == "set-manifest-version":
        changed = set_manifest_version(args.version, args.manifest)
        if not changed:
            return 1, f"Manifest is already set to version `{args.version}`."
        return 0, None

    return 1, f"Unknown command `{args.command}`."


def main(argv: Sequence[str] | None = None) -> int:
    """Run the release helper CLI."""
    args = _parse_args(argv)
    try:
        status, error_message = _run_command(args)
    except ValueError as exc:
        sys.stderr.write(f"Release validation failed: {exc}\n")
        return 1

    if error_message is not None:
        sys.stderr.write(f"Release validation failed: {error_message}\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
