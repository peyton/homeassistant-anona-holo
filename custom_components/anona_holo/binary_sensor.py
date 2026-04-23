"""Binary sensor platform for the Anona Holo integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .const import DATA_COORDINATORS, DEVICE_TYPE_LOCK, DOMAIN
from .entity import AnonaHoloCoordinatorEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import AnonaDeviceCoordinator, AnonaDeviceSnapshot


@dataclass(slots=True, frozen=True, kw_only=True)
class AnonaBinarySensorDescription(BinarySensorEntityDescription):
    """Description for coordinator-backed Anona binary sensors."""

    value_fn: Callable[[AnonaDeviceSnapshot], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[AnonaBinarySensorDescription, ...] = (
    AnonaBinarySensorDescription(
        key="auto_lock_enabled",
        name="Auto-lock",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda snapshot: (
            snapshot.lock_status.auto_lock_enabled if snapshot.lock_status else None
        ),
    ),
    AnonaBinarySensorDescription(
        key="lock_jam",
        name="Lock Jam",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda snapshot: (
            snapshot.lock_status.has_locking_fail if snapshot.lock_status else None
        ),
    ),
    AnonaBinarySensorDescription(
        key="door_open_too_long",
        name="Door Open Too Long",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda snapshot: (
            snapshot.lock_status.has_door_been_open_long_time
            if snapshot.lock_status
            else None
        ),
    ),
    AnonaBinarySensorDescription(
        key="low_power_mode",
        name="Low Power Mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: (
            snapshot.lock_status.low_power_mode_enabled
            if snapshot.lock_status
            else None
        ),
    ),
    AnonaBinarySensorDescription(
        key="keypad_connected",
        name="Keypad Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: (
            snapshot.lock_status.keypad_connection_status_code > 0
            if snapshot.lock_status
            and snapshot.lock_status.keypad_connection_status_code is not None
            else None
        ),
    ),
    AnonaBinarySensorDescription(
        key="online",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda snapshot: (
            snapshot.online_status.online if snapshot.online_status else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anona binary sensors."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, AnonaDeviceCoordinator] = entry_data[DATA_COORDINATORS]

    entities: list[AnonaHoloBinarySensor] = []
    for coordinator in coordinators.values():
        if coordinator.device.device_type != DEVICE_TYPE_LOCK:
            continue
        entities.extend(
            AnonaHoloBinarySensor(coordinator, description)
            for description in BINARY_SENSOR_DESCRIPTIONS
        )
    async_add_entities(entities)


class AnonaHoloBinarySensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    AnonaHoloCoordinatorEntity,
    BinarySensorEntity,
):
    """Coordinator-backed binary telemetry entity."""

    def __init__(
        self,
        coordinator: AnonaDeviceCoordinator,
        description: AnonaBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        description_name = (
            description.name if isinstance(description.name, str) else None
        )
        super().__init__(
            coordinator,
            unique_suffix=f"binary_sensor_{description.key}",
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
        self._attr_is_on = self._description.value_fn(self.snapshot)
