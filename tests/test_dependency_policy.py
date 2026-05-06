"""Repository dependency policy checks."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = REPO_ROOT / "requirements.txt"


def _requirement_names() -> set[str]:
    names: set[str] = set()
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        requirement = raw_line.partition("#")[0].strip()
        if not requirement:
            continue
        name = requirement
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if separator in requirement:
                name = requirement.split(separator, 1)[0]
                break
        names.add(name.split("[", 1)[0].strip().replace("_", "-").lower())
    return names


def test_home_assistant_test_stack_is_helper_managed() -> None:
    """Keep generated Home Assistant test-stack pins together."""
    requirement_names = _requirement_names()

    if "pytest-homeassistant-custom-component" not in requirement_names:
        pytest.fail("requirements.txt must pin pytest-homeassistant-custom-component")
    if "homeassistant" in requirement_names:
        pytest.fail("homeassistant must remain transitive through the test helper")
    if "pytest" in requirement_names:
        pytest.fail("pytest must remain transitive through the test helper")
