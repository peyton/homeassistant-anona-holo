"""Sensor platform for the Anona Holo integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.util import dt as dt_util

from .const import DEVICE_TYPE_LOCK
from .entity import AnonaHoloCoordinatorEntity

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import AnonaConfigEntry
    from .coordinator import AnonaDeviceCoordinator, AnonaDeviceSnapshot


@dataclass(slots=True, frozen=True, kw_only=True)
class AnonaSensorDescription(SensorEntityDescription):
    """Description for coordinator-backed Anona sensors."""

    value_fn: Callable[[AnonaDeviceSnapshot], Any]


SENSOR_DESCRIPTIONS: tuple[AnonaSensorDescription, ...] = (
    AnonaSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        value_fn=lambda snapshot: (
            snapshot.lock_status.battery_capacity if snapshot.lock_status else None
        ),
    ),
    AnonaSensorDescription(
        key="auto_lock_delay",
        translation_key="auto_lock_delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        value_fn=lambda snapshot: (
            snapshot.lock_status.auto_lock_delay_seconds
            if snapshot.lock_status
            else None
        ),
    ),
    AnonaSensorDescription(
        key="sound_volume",
        translation_key="sound_volume",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.CONFIG,
        options=["high", "low"],
        has_entity_name=True,
        value_fn=lambda snapshot: (
            snapshot.lock_status.sound_volume if snapshot.lock_status else None
        ),
    ),
    AnonaSensorDescription(
        key="keypad_battery",
        translation_key="keypad_battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_entity_name=True,
        value_fn=lambda snapshot: (
            snapshot.lock_status.keypad_battery_capacity
            if snapshot.lock_status
            else None
        ),
    ),
    AnonaSensorDescription(
        key="last_alive",
        translation_key="last_alive",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_entity_name=True,
        value_fn=lambda snapshot: _ts_to_datetime(
            snapshot.online_status.last_alive_ts if snapshot.online_status else None
        ),
    ),
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AnonaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anona telemetry sensors."""
    coordinators: dict[str, AnonaDeviceCoordinator] = entry.runtime_data.coordinators

    entities: list[AnonaHoloSensor] = []
    for coordinator in coordinators.values():
        if coordinator.device.device_type != DEVICE_TYPE_LOCK:
            continue
        entities.extend(
            AnonaHoloSensor(coordinator, description)
            for description in SENSOR_DESCRIPTIONS
        )
    async_add_entities(entities)


class AnonaHoloSensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    AnonaHoloCoordinatorEntity,
    SensorEntity,
):
    """Coordinator-backed telemetry sensor."""

    def __init__(
        self,
        coordinator: AnonaDeviceCoordinator,
        description: AnonaSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            unique_suffix=f"sensor_{description.key}",
            translation_key=description.translation_key,
        )
        self._description = description
        self.entity_description = description
        self._apply_snapshot()

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and refresh Home Assistant attributes."""
        self._apply_snapshot()
        super()._handle_coordinator_update()

    def _apply_snapshot(self) -> None:
        """Apply latest coordinator snapshot fields to entity attributes."""
        self._attr_native_value = self._description.value_fn(self.snapshot)


def _ts_to_datetime(value: int | None) -> datetime | None:
    """Convert an epoch-millis timestamp to a timezone-aware datetime."""
    if value is None:
        return None
    return dt_util.utc_from_timestamp(value / 1000)
