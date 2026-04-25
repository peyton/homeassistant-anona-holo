"""Switch platform for the Anona Holo integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import AnonaApiError
from .const import (
    DEFAULT_SILENT_OTA_TIME_WINDOW,
    DEVICE_TYPE_LOCK,
    DOMAIN,
)
from .entity import AnonaHoloCoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import AnonaConfigEntry
    from .api import DeviceInfoContext, DeviceSwitchSettings
    from .coordinator import AnonaDeviceCoordinator

SwitchFieldName = Literal[
    "main_switch",
    "ugent_notify_switch",
    "important_notify_switch",
    "normal_notify_switch",
]


@dataclass(slots=True, frozen=True, kw_only=True)
class AnonaSwitchDescription(SwitchEntityDescription):
    """Description for writable notification switch entities."""

    field_name: SwitchFieldName


NOTIFICATION_SWITCHES: tuple[AnonaSwitchDescription, ...] = (
    AnonaSwitchDescription(
        key="allow_notifications",
        translation_key="allow_notifications",
        has_entity_name=True,
        field_name="main_switch",
    ),
    AnonaSwitchDescription(
        key="abnormal_notifications",
        translation_key="abnormal_notifications",
        has_entity_name=True,
        field_name="ugent_notify_switch",
    ),
    AnonaSwitchDescription(
        key="event_notifications",
        translation_key="event_notifications",
        has_entity_name=True,
        field_name="important_notify_switch",
    ),
    AnonaSwitchDescription(
        key="other_notifications",
        translation_key="other_notifications",
        has_entity_name=True,
        field_name="normal_notify_switch",
    ),
)

SILENT_OTA_SWITCH = AnonaSwitchDescription(
    key="silent_ota",
    translation_key="silent_ota",
    has_entity_name=True,
    field_name="main_switch",
)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AnonaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable switch entities for an entry."""
    coordinators: dict[str, AnonaDeviceCoordinator] = entry.runtime_data.coordinators

    entities: list[SwitchEntity] = []
    for coordinator in coordinators.values():
        if coordinator.device.device_type != DEVICE_TYPE_LOCK:
            continue
        entities.extend(
            AnonaNotificationSwitch(coordinator, description)
            for description in NOTIFICATION_SWITCHES
        )
        entities.append(AnonaSilentOTASwitch(coordinator))
    async_add_entities(entities)


class AnonaNotificationSwitch(  # pyright: ignore[reportIncompatibleVariableOverride]
    AnonaHoloCoordinatorEntity,
    SwitchEntity,
):
    """Writable notification switch backed by updateDeviceSwitch."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AnonaDeviceCoordinator,
        description: AnonaSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator,
            unique_suffix=f"switch_{description.key}",
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
        settings = self.snapshot.switch_settings
        self._attr_is_on = (
            bool(getattr(settings, self._description.field_name))
            if settings is not None
            else None
        )

    async def async_turn_on(self, **_: Any) -> None:
        """Enable the selected switch."""
        await self._async_apply_state(state="on")

    async def async_turn_off(self, **_: Any) -> None:
        """Disable the selected switch."""
        await self._async_apply_state(state="off")

    async def _async_apply_state(self, *, state: Literal["on", "off"]) -> None:
        """Apply a merged switch payload to avoid wiping other toggles."""
        settings = await self._async_get_switch_settings()
        enabled = state == "on"
        payload = {
            "main_switch": settings.main_switch,
            "ugent_notify_switch": settings.ugent_notify_switch,
            "important_notify_switch": settings.important_notify_switch,
            "normal_notify_switch": settings.normal_notify_switch,
        }
        payload[self._description.field_name] = enabled

        try:
            await self._api.update_device_switch_settings(
                self._device,
                main_switch=payload["main_switch"],
                ugent_notify_switch=payload["ugent_notify_switch"],
                important_notify_switch=payload["important_notify_switch"],
                normal_notify_switch=payload["normal_notify_switch"],
            )
        except AnonaApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_switch_failed",
            ) from err
        await self.coordinator.async_request_details_refresh()

    async def _async_get_switch_settings(self) -> DeviceSwitchSettings:
        """Get current switch settings, triggering detail refresh when needed."""
        settings = self.snapshot.switch_settings
        if settings is not None:
            return settings

        await self.coordinator.async_request_details_refresh()
        refreshed_settings = self.snapshot.switch_settings
        if refreshed_settings is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="missing_switch_settings",
            )
        return refreshed_settings


class AnonaSilentOTASwitch(  # pyright: ignore[reportIncompatibleVariableOverride]
    AnonaHoloCoordinatorEntity,
    SwitchEntity,
):
    """Writable silent OTA toggle backed by setSilentOTA."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AnonaDeviceCoordinator) -> None:
        """Initialize the silent OTA switch."""
        super().__init__(
            coordinator,
            unique_suffix="switch_silent_ota",
            translation_key=SILENT_OTA_SWITCH.translation_key,
        )
        self.entity_description = SILENT_OTA_SWITCH
        self._apply_snapshot()

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and refresh Home Assistant attributes."""
        self._apply_snapshot()
        super()._handle_coordinator_update()

    def _apply_snapshot(self) -> None:
        """Apply latest coordinator snapshot fields to entity attributes."""
        info_context = self.snapshot.device_info_context
        self._attr_is_on = info_context.silent_ota_enabled if info_context else None

    async def async_turn_on(self, **_: Any) -> None:
        """Enable silent OTA updates."""
        await self._async_set_state(state="on")

    async def async_turn_off(self, **_: Any) -> None:
        """Disable silent OTA updates."""
        await self._async_set_state(state="off")

    async def _async_set_state(self, *, state: Literal["on", "off"]) -> None:
        """Persist the silent OTA switch state."""
        info_context = await self._async_get_info_context()
        enabled = state == "on"
        silent_ota_time = (
            info_context.silent_ota_time
            if info_context and info_context.silent_ota_time
            else DEFAULT_SILENT_OTA_TIME_WINDOW
        )
        try:
            await self._api.set_silent_ota(
                self._device,
                enabled=enabled,
                silent_ota_time=silent_ota_time,
            )
        except AnonaApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="silent_ota_update_failed",
            ) from err
        await self.coordinator.async_request_details_refresh()

    async def _async_get_info_context(self) -> DeviceInfoContext | None:
        """Fetch info context if not present in the current snapshot."""
        info_context = self.snapshot.device_info_context
        if info_context is not None:
            return info_context

        await self.coordinator.async_request_details_refresh()
        return self.snapshot.device_info_context
