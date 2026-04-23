"""Config flow for the Anona Holo integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AnonaApi, AnonaApiError, AnonaAuthError, AnonaConnectionError
from .const import (
    CONF_CLIENT_UUID,
    CONF_EMAIL,
    CONF_HOME_ID,
    CONF_PASSWORD,
    CONF_USER_ID,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigFlowResult

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.EMAIL,
                autocomplete="username",
            )
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD,
                autocomplete="current-password",
            )
        ),
    }
)


@dataclass(slots=True, frozen=True)
class ValidatedAuth:
    """Validated credentials and identifiers for one config entry."""

    email: str
    normalized_email: str
    password: str
    client_uuid: str
    user_id: str
    home_id: str


def _entry_title(email: str) -> str:
    """Return the config-entry title for the supplied account."""
    return f"Anona Holo ({email})"


def _normalize_email(email: str) -> str:
    """Normalize an email address for use as a config-entry unique ID."""
    return email.strip().lower()


class AnonaHoloConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Home Assistant config flow for Anona Holo."""

    VERSION = 2
    MINOR_VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial credential entry step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                validated = await self._async_validate_auth(user_input)
            except AnonaAuthError:
                errors["base"] = "invalid_auth"
            except AnonaConnectionError, TimeoutError:
                errors["base"] = "cannot_connect"
            except AnonaApiError:
                errors["base"] = "unknown"
            except Exception:  # pragma: no cover - defensive Home Assistant guard
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(validated.normalized_email)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_entry_title(validated.email),
                    data={
                        CONF_EMAIL: validated.email,
                        CONF_PASSWORD: validated.password,
                        CONF_CLIENT_UUID: validated.client_uuid,
                        CONF_USER_ID: validated.user_id,
                        CONF_HOME_ID: validated.home_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(AUTH_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Handle a flow initialized after an authentication failure."""
        _ = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reauthentication for an existing config entry."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                validated = await self._async_validate_auth(
                    user_input,
                    client_uuid=entry.data[CONF_CLIENT_UUID],
                    home_id=entry.data.get(CONF_HOME_ID),
                    user_id=entry.data.get(CONF_USER_ID),
                )
            except AnonaAuthError:
                errors["base"] = "invalid_auth"
            except AnonaConnectionError, TimeoutError:
                errors["base"] = "cannot_connect"
            except AnonaApiError:
                errors["base"] = "unknown"
            except Exception:  # pragma: no cover - defensive Home Assistant guard
                _LOGGER.exception("Unexpected error during reauth flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(validated.normalized_email)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    title=_entry_title(validated.email),
                    data_updates={
                        CONF_EMAIL: validated.email,
                        CONF_PASSWORD: validated.password,
                        CONF_CLIENT_UUID: validated.client_uuid,
                        CONF_USER_ID: validated.user_id,
                        CONF_HOME_ID: validated.home_id,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                AUTH_SCHEMA,
                self._suggested_auth_values(entry, user_input),
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle a user-initiated reconfiguration flow."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                validated = await self._async_validate_auth(
                    user_input,
                    client_uuid=entry.data[CONF_CLIENT_UUID],
                    home_id=entry.data.get(CONF_HOME_ID),
                    user_id=entry.data.get(CONF_USER_ID),
                )
            except AnonaAuthError:
                errors["base"] = "invalid_auth"
            except AnonaConnectionError, TimeoutError:
                errors["base"] = "cannot_connect"
            except AnonaApiError:
                errors["base"] = "unknown"
            except Exception:  # pragma: no cover - defensive Home Assistant guard
                _LOGGER.exception("Unexpected error during reconfigure flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(validated.normalized_email)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    title=_entry_title(validated.email),
                    data_updates={
                        CONF_EMAIL: validated.email,
                        CONF_PASSWORD: validated.password,
                        CONF_CLIENT_UUID: validated.client_uuid,
                        CONF_USER_ID: validated.user_id,
                        CONF_HOME_ID: validated.home_id,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                AUTH_SCHEMA,
                self._suggested_auth_values(entry, user_input),
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def _async_validate_auth(
        self,
        user_input: Mapping[str, Any],
        *,
        client_uuid: str | None = None,
        home_id: str | None = None,
        user_id: str | None = None,
    ) -> ValidatedAuth:
        """Validate credentials and return normalized config-entry data."""
        email = str(user_input[CONF_EMAIL]).strip()
        password = str(user_input[CONF_PASSWORD])
        resolved_client_uuid = client_uuid or str(uuid4()).upper()
        api = AnonaApi(
            async_get_clientsession(self.hass),
            client_uuid=resolved_client_uuid,
            home_id=home_id,
            user_id=user_id,
        )

        login_context = await api.login(email, password)
        homes = await api.get_homes()
        resolved_home_id = api.home_id
        if resolved_home_id is None and homes:
            resolved_home_id = homes[0].home_id
        if resolved_home_id is None:
            message = "No home was discovered for this account"
            raise AnonaApiError(message)

        return ValidatedAuth(
            email=email,
            normalized_email=_normalize_email(email),
            password=password,
            client_uuid=resolved_client_uuid,
            user_id=login_context.user_id,
            home_id=resolved_home_id,
        )

    def _suggested_auth_values(
        self,
        entry: config_entries.ConfigEntry,
        user_input: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Return safe suggested auth values for reauth and reconfigure forms."""
        suggested_values: dict[str, Any] = {
            CONF_EMAIL: entry.data[CONF_EMAIL],
        }
        if user_input is not None:
            suggested_values.update(user_input)
        return suggested_values
