"""Tests for the local Home Assistant config bootstrap helper."""

# ruff: noqa: S101

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.ensure_dev_config import DEFAULT_CONFIGURATION_YAML, main

if TYPE_CHECKING:
    from pathlib import Path


def test_main_creates_configuration_file_when_missing(tmp_path: Path) -> None:
    """The helper should create the default config in a missing directory."""
    config_dir = tmp_path / "config"

    exit_code = main(["--config-dir", str(config_dir)])

    assert exit_code == 0
    assert (config_dir / "configuration.yaml").read_text() == DEFAULT_CONFIGURATION_YAML


def test_main_preserves_existing_configuration_file(tmp_path: Path) -> None:
    """The helper should not overwrite an existing local config file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    configuration_path = config_dir / "configuration.yaml"
    configuration_path.write_text("logger:\n  default: warning\n")

    exit_code = main(["--config-dir", str(config_dir)])

    assert exit_code == 0
    assert configuration_path.read_text() == "logger:\n  default: warning\n"
