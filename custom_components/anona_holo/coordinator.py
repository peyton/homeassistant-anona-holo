"""Shared per-device coordinators for Anona Holo entities."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AnonaApi,
    AnonaApiError,
    DeviceContext,
    DeviceInfoContext,
    DeviceSwitchSettings,
    FirmwareUpdateContext,
    LockStatus,
    OnlineStatus,
)
from .const import DETAILS_REFRESH_INTERVAL_SECONDS, DOMAIN, UPDATE_INTERVAL_SECONDS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AnonaDeviceSnapshot:
    """Latest aggregated state for one Anona device."""

    device: DeviceContext
    online_status: OnlineStatus | None = None
    lock_status: LockStatus | None = None
    device_info_context: DeviceInfoContext | None = None
    switch_settings: DeviceSwitchSettings | None = None
    firmware_update_context: FirmwareUpdateContext | None = None


class AnonaDeviceCoordinator(DataUpdateCoordinator[AnonaDeviceSnapshot]):
    """Coordinator that polls fast lock state and slower device details."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api: AnonaApi,
        device: DeviceContext,
        config_entry: ConfigEntry | None = None,
        initial_switch_settings: DeviceSwitchSettings | None = None,
    ) -> None:
        """Initialize the coordinator for one physical lock."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device.device_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
            config_entry=config_entry,
        )
        self._api = api
        self._device = device
        self._details_refresh_interval = DETAILS_REFRESH_INTERVAL_SECONDS
        self._force_details_refresh = False
        self._last_details_refresh_monotonic: float | None = None
        self._data = AnonaDeviceSnapshot(
            device=device,
            switch_settings=initial_switch_settings,
        )

    @property
    def api(self) -> AnonaApi:
        """Return the API client bound to this coordinator."""
        return self._api

    @property
    def device(self) -> DeviceContext:
        """Return the device context bound to this coordinator."""
        return self._device

    async def async_request_details_refresh(self) -> None:
        """Schedule an immediate details refresh on the next coordinator poll."""
        self._force_details_refresh = True
        await self.async_request_refresh()

    async def _async_update_data(  # noqa: PLR0912, PLR0915
        self,
    ) -> AnonaDeviceSnapshot:
        """Refresh fast lock telemetry and slower diagnostics/settings payloads."""
        snapshot = self.data if self.data is not None else self._data

        online_status = snapshot.online_status
        lock_status = snapshot.lock_status
        device_info_context = snapshot.device_info_context
        switch_settings = snapshot.switch_settings
        firmware_update_context = snapshot.firmware_update_context

        try:
            online_status = await self._api.get_device_online_status(self._device)
        except AnonaApiError as err:
            _LOGGER.debug(
                "Fast online poll failed for %s: %s",
                self._device.device_id,
                err,
            )

        try:
            lock_status = await self._api.get_device_status(self._device)
        except AnonaApiError as err:
            _LOGGER.debug(
                "Fast lock-status poll failed for %s: %s",
                self._device.device_id,
                err,
            )

        if online_status is None and lock_status is None:
            message = f"Unable to fetch status for {self._device.device_id}"
            raise UpdateFailed(message)

        now_monotonic = time.monotonic()
        if self._should_refresh_details(
            now_monotonic,
            device_info_context=device_info_context,
            switch_settings=switch_settings,
            firmware_update_context=firmware_update_context,
        ):
            details_refreshed = False

            try:
                device_info_context = await self._api.get_device_info_context(
                    self._device
                )
            except AnonaApiError as err:
                _LOGGER.debug(
                    "Detail poll getDeviceInfo failed for %s: %s",
                    self._device.device_id,
                    err,
                )
            else:
                details_refreshed = True

            try:
                switch_settings = await self._api.get_device_switch_settings(
                    self._device
                )
            except AnonaApiError as err:
                _LOGGER.debug(
                    "Detail poll getDeviceSwitch failed for %s: %s",
                    self._device.device_id,
                    err,
                )
                # Fallback to the list-by-home endpoint when single-device lookup
                # fails transiently.
                try:
                    switches_by_device = (
                        await self._api.get_device_switch_list_by_home()
                    )
                except AnonaApiError as list_err:
                    _LOGGER.debug(
                        "Detail poll getDeviceSwitchListByHomeId failed for %s: %s",
                        self._device.device_id,
                        list_err,
                    )
                else:
                    maybe_settings = switches_by_device.get(self._device.device_id)
                    if maybe_settings is not None:
                        switch_settings = maybe_settings
                        details_refreshed = True
            else:
                details_refreshed = True

            try:
                firmware_update_context = await self._api.get_firmware_update_context(
                    self._device
                )
            except AnonaApiError as err:
                _LOGGER.debug(
                    "Detail poll checkNewRomFromApp failed for %s: %s",
                    self._device.device_id,
                    err,
                )
            else:
                details_refreshed = True

            if details_refreshed:
                self._last_details_refresh_monotonic = now_monotonic
            self._force_details_refresh = False

        return AnonaDeviceSnapshot(
            device=self._device,
            online_status=online_status,
            lock_status=lock_status,
            device_info_context=device_info_context,
            switch_settings=switch_settings,
            firmware_update_context=firmware_update_context,
        )

    def _should_refresh_details(
        self,
        now_monotonic: float,
        *,
        device_info_context: DeviceInfoContext | None,
        switch_settings: DeviceSwitchSettings | None,
        firmware_update_context: FirmwareUpdateContext | None,
    ) -> bool:
        """Return whether detail endpoints should be refreshed on this cycle."""
        if self._force_details_refresh:
            return True
        if (
            device_info_context is None
            or switch_settings is None
            or firmware_update_context is None
        ):
            return True
        if self._last_details_refresh_monotonic is None:
            return True
        elapsed = now_monotonic - self._last_details_refresh_monotonic
        return elapsed >= self._details_refresh_interval
