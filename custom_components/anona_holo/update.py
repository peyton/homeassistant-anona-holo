"""Update platform for the Anona Holo integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity

from .api import is_firmware_update_available
from .const import DATA_COORDINATORS, DEVICE_TYPE_LOCK, DOMAIN
from .entity import AnonaHoloCoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import AnonaDeviceCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up firmware update entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, AnonaDeviceCoordinator] = entry_data[DATA_COORDINATORS]
    entities = [
        AnonaHoloFirmwareUpdate(coordinator)
        for coordinator in coordinators.values()
        if coordinator.device.device_type == DEVICE_TYPE_LOCK
    ]
    async_add_entities(entities)


class AnonaHoloFirmwareUpdate(  # pyright: ignore[reportIncompatibleVariableOverride]
    AnonaHoloCoordinatorEntity,
    UpdateEntity,
):
    """Firmware metadata entity from checkNewRomFromApp."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE

    def __init__(self, coordinator: AnonaDeviceCoordinator) -> None:
        """Initialize the firmware update entity."""
        super().__init__(
            coordinator,
            unique_suffix="update_firmware",
            name="Firmware",
        )
        self._apply_snapshot()

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and refresh Home Assistant attributes."""
        self._apply_snapshot()
        super()._handle_coordinator_update()

    def _apply_snapshot(self) -> None:
        """Apply latest coordinator snapshot fields to entity attributes."""
        snapshot = self.snapshot
        firmware_context = snapshot.firmware_update_context
        info_context = snapshot.device_info_context

        installed_version = None
        if firmware_context and firmware_context.installed_version:
            installed_version = firmware_context.installed_version
        elif info_context is not None:
            installed_version = info_context.firmware_version

        latest_version = firmware_context.latest_version if firmware_context else None
        self._attr_installed_version = installed_version
        self._attr_latest_version = latest_version
        self._attr_release_summary = (
            firmware_context.release_notes if firmware_context else None
        )
        self._attr_release_url = (
            firmware_context.release_url if firmware_context else None
        )
        self._attr_available = bool(
            firmware_context
            and is_firmware_update_available(
                installed_version,
                latest_version,
                new_version=firmware_context.new_version,
            )
        )
