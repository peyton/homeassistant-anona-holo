"""Tests for custom integration translation coverage."""

# ruff: noqa: S101

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from custom_components.anona_holo.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.anona_holo.sensor import SENSOR_DESCRIPTIONS
from custom_components.anona_holo.switch import NOTIFICATION_SWITCHES, SILENT_OTA_SWITCH
from custom_components.anona_holo.update import FIRMWARE_TRANSLATION_KEY

ROOT = Path(__file__).parents[3]
INTEGRATION_DIR = ROOT / "custom_components" / "anona_holo"
TRANSLATION_DIR = INTEGRATION_DIR / "translations"
REQUIRED_TRANSLATIONS = ("en", "zh-Hans", "zh-Hant")
MISSING_SWITCH_SETTINGS_MESSAGE = (
    "Notification switch settings are not available yet. Try again after "
    "Home Assistant refreshes the lock."
)


def _load_translation(language: str) -> dict[str, Any]:
    """Load a translation file."""
    payload = json.loads((TRANSLATION_DIR / f"{language}.json").read_text())
    assert isinstance(payload, dict)
    return cast("dict[str, Any]", payload)


def _leaf_paths(value: object, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Return recursive leaf paths for a JSON-compatible value."""
    if isinstance(value, dict):
        paths: set[tuple[str, ...]] = set()
        for key, child in value.items():
            assert isinstance(key, str)
            paths.update(_leaf_paths(child, (*prefix, key)))
        return paths
    return {prefix}


def _string_values(value: object) -> list[str]:
    """Return every string in a JSON-compatible value."""
    if isinstance(value, dict):
        strings: list[str] = []
        for child in value.values():
            strings.extend(_string_values(child))
        return strings
    if isinstance(value, str):
        return [value]
    return []


def test_custom_integration_translation_files_are_complete() -> None:
    """Custom integrations should ship complete translations, not strings.json."""
    assert not (INTEGRATION_DIR / "strings.json").exists()

    translations = {
        language: _load_translation(language) for language in REQUIRED_TRANSLATIONS
    }
    expected_leaf_paths = _leaf_paths(translations["en"])

    for language, payload in translations.items():
        assert (TRANSLATION_DIR / f"{language}.json").is_file()
        assert _leaf_paths(payload) == expected_leaf_paths
        assert all("[%key:" not in value for value in _string_values(payload))


def test_entity_translation_keys_are_covered() -> None:
    """Every translated entity should have a matching translation entry."""
    payload = _load_translation("en")
    entity_translations = payload["entity"]

    sensor_translations = entity_translations["sensor"]
    for description in SENSOR_DESCRIPTIONS:
        assert description.translation_key == description.key
        assert description.translation_key in sensor_translations

    sound_volume = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "sound_volume"
    )
    assert set(sound_volume.options or []) == set(
        sensor_translations["sound_volume"]["state"]
    )

    binary_sensor_translations = entity_translations["binary_sensor"]
    for description in BINARY_SENSOR_DESCRIPTIONS:
        assert description.translation_key == description.key
        assert description.translation_key in binary_sensor_translations

    switch_translations = entity_translations["switch"]
    for description in NOTIFICATION_SWITCHES:
        assert description.translation_key == description.key
        assert description.translation_key in switch_translations
    assert SILENT_OTA_SWITCH.translation_key in switch_translations

    update_translations = entity_translations["update"]
    assert FIRMWARE_TRANSLATION_KEY in update_translations


def test_exception_translation_is_available() -> None:
    """User-visible HomeAssistantError keys should have messages."""
    payload = _load_translation("en")

    assert (
        payload["exceptions"]["missing_switch_settings"]["message"]
        == MISSING_SWITCH_SETTINGS_MESSAGE
    )
