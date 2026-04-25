"""Shared entity helpers for Anona Holo platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import UNDEFINED, UndefinedType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AnonaDeviceCoordinator, AnonaDeviceSnapshot


class AnonaHoloCoordinatorEntity(CoordinatorEntity[AnonaDeviceCoordinator]):
    """Base coordinator-backed entity for one Anona lock."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AnonaDeviceCoordinator,
        *,
        unique_suffix: str,
        name: str | None | UndefinedType = UNDEFINED,
        translation_key: str | None = None,
    ) -> None:
        """Initialize a shared coordinator-backed entity."""
        super().__init__(coordinator)
        self._device = coordinator.device
        self._api = coordinator.api
        if name is not UNDEFINED:
            self._attr_name = name
        if translation_key is not None:
            self._attr_translation_key = translation_key
        self._attr_unique_id = f"{DOMAIN}_{self._device.device_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            manufacturer="Anona Holo",
            model=self._device.model,
            name=self._device.nickname,
            serial_number=self._device.serial_number,
        )

    @property
    def snapshot(self) -> AnonaDeviceSnapshot:
        """Return the latest coordinator snapshot."""
        snapshot = self.coordinator.data
        if snapshot is None:
            message = "Coordinator snapshot is not available yet"
            raise RuntimeError(message)
        return snapshot
