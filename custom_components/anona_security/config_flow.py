"""Config flow for the Anona-backed lock integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnonaApi, AnonaAuthError
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntegrationBlueprintConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the lock integration."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial config flow step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            api = AnonaApi(async_get_clientsession(self.hass))

            try:
                await api.login(email, password)
            except AnonaAuthError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError, TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive Home Assistant guard
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Anona Holo ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        "access_token": api.access_token,
                        "user_id": api.user_id,
                        "home_id": api.home_id,
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
