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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricPotential
from homeassistant.util import dt as dt_util

from .const import DATA_COORDINATORS, DEVICE_TYPE_LOCK, DOMAIN
from .entity import AnonaHoloCoordinatorEntity

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import AnonaDeviceCoordinator, AnonaDeviceSnapshot


@dataclass(slots=True, frozen=True, kw_only=True)
class AnonaSensorDescription(SensorEntityDescription):
    """Description for coordinator-backed Anona sensors."""

    value_fn: Callable[[AnonaDeviceSnapshot], Any]


SENSOR_DESCRIPTIONS: tuple[AnonaSensorDescription, ...] = (
    AnonaSensorDescription(
        key="battery_level",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snapshot: (
            snapshot.lock_status.battery_capacity if snapshot.lock_status else None
        ),
    ),
    AnonaSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: (
            (snapshot.lock_status.battery_voltage / 100)
            if snapshot.lock_status and snapshot.lock_status.battery_voltage is not None
            else None
        ),
    ),
    AnonaSensorDescription(
        key="keypad_battery",
        name="Keypad Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: (
            snapshot.lock_status.keypad_battery_capacity
            if snapshot.lock_status
            else None
        ),
    ),
    AnonaSensorDescription(
        key="last_alive",
        name="Last Alive",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: _ts_to_datetime(
            snapshot.online_status.last_alive_ts if snapshot.online_status else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anona telemetry sensors."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, AnonaDeviceCoordinator] = entry_data[DATA_COORDINATORS]

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
        description_name = (
            description.name if isinstance(description.name, str) else None
        )
        super().__init__(
            coordinator,
            unique_suffix=f"sensor_{description.key}",
            name=description_name,
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
