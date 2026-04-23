"""Home Assistant setup for the Anona Holo integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnonaApi, AnonaApiError, AnonaAuthError
from .const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
    DEVICE_TYPE_LOCK,
    DOMAIN,
)
from .coordinator import AnonaDeviceCoordinator
from .privacy import redact_log_value

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import DeviceContext

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


@dataclass(slots=True)
class AnonaHoloRuntimeData:
    """Runtime data attached to one Anona Holo config entry."""

    api: AnonaApi
    devices: dict[str, DeviceContext]
    coordinators: dict[str, AnonaDeviceCoordinator]


type AnonaConfigEntry = ConfigEntry[AnonaHoloRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: AnonaConfigEntry) -> bool:
    """Set up an Anona Holo config entry."""
    api = AnonaApi(
        async_get_clientsession(hass),
        client_uuid=entry.data[CONF_CLIENT_UUID],
        home_id=entry.data.get(CONF_HOME_ID),
        user_id=entry.data.get(CONF_USER_ID),
    )

    try:
        login_context = await api.login(
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
        )
        await api.get_homes()
        all_devices = await api.get_all_devices()
    except AnonaAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="invalid_auth",
        ) from err
    except (AnonaApiError, TimeoutError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
        ) from err

    updated_data = dict(entry.data)
    updated_data[CONF_USER_ID] = login_context.user_id
    if api.home_id is not None:
        updated_data[CONF_HOME_ID] = api.home_id
    if updated_data != entry.data:
        hass.config_entries.async_update_entry(entry, data=updated_data)

    lock_devices = [
        device for device in all_devices if device.device_type == DEVICE_TYPE_LOCK
    ]
    if not lock_devices:
        _LOGGER.warning("No supported lock devices were discovered for this account")

    try:
        switch_settings_by_device_id = await api.get_device_switch_list_by_home()
    except AnonaAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="invalid_auth",
        ) from err
    except (AnonaApiError, TimeoutError) as err:
        _LOGGER.debug(
            "Initial getDeviceSwitchListByHomeId preload failed: %s",
            redact_log_value(
                str(err),
                extra_values=(api.home_id, api.user_id, api.client_uuid),
            ),
        )
        switch_settings_by_device_id = {}

    coordinators: dict[str, AnonaDeviceCoordinator] = {}
    for device in lock_devices:
        coordinator = AnonaDeviceCoordinator(
            hass,
            api=api,
            device=device,
            config_entry=entry,
            initial_switch_settings=switch_settings_by_device_id.get(device.device_id),
        )
        try:
            await coordinator.async_config_entry_first_refresh()
        except (AnonaApiError, TimeoutError) as err:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        coordinators[device.device_id] = coordinator

    entry.runtime_data = AnonaHoloRuntimeData(
        api=api,
        devices={device.device_id: device for device in lock_devices},
        coordinators=coordinators,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AnonaConfigEntry) -> bool:
    """Unload an Anona Holo config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
