"""Pytest configuration for Home Assistant integration tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading custom components from this repository in tests."""
    _ = enable_custom_integrations
