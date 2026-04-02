"""Config flow for the Anona Security integration."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnonaApi, AnonaApiError, AnonaAuthError
from .const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AnonaSecurityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Home Assistant config flow for Anona Security."""

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial credential entry step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            client_uuid = str(uuid4()).upper()
            api = AnonaApi(
                async_get_clientsession(self.hass),
                client_uuid=client_uuid,
            )

            try:
                login_context = await api.login(email, password)
                homes = await api.get_homes()
            except AnonaAuthError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError, TimeoutError:
                errors["base"] = "cannot_connect"
            except AnonaApiError:
                errors["base"] = "unknown"
            except Exception:  # pragma: no cover - defensive Home Assistant guard
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                home_id = api.home_id
                if home_id is None and homes:
                    home_id = homes[0].home_id
                if home_id is None:
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=f"Anona Security ({email})",
                        data={
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                            CONF_CLIENT_UUID: client_uuid,
                            CONF_USER_ID: login_context.user_id,
                            CONF_HOME_ID: home_id,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
