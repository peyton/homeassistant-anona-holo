"""Home Assistant setup for the Anona Security integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnonaApi, AnonaApiError, AnonaAuthError, AnonaSignatureError
from .const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [Platform.LOCK]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Anona Security config entry."""
    api = AnonaApi(
        async_get_clientsession(hass),
        client_uuid=entry.data[CONF_CLIENT_UUID],
        home_id=entry.data.get(CONF_HOME_ID),
        user_id=entry.data.get(CONF_USER_ID),
    )

    try:
        login_context = await api.login(
            entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
        )
        await api.get_homes()
    except AnonaAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (AnonaSignatureError, AnonaApiError, TimeoutError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    updated_data = dict(entry.data)
    updated_data[CONF_USER_ID] = login_context.user_id
    if api.home_id is not None:
        updated_data[CONF_HOME_ID] = api.home_id
    if updated_data != entry.data:
        hass.config_entries.async_update_entry(entry, data=updated_data)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = api
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Anona Security config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
