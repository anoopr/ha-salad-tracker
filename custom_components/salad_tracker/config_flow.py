"""Config flow to set up the Salad Tracker integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SaladApiClient,
    SaladApiAuthError,
    SaladApiClientError,
)
from .const import (
    CONF_ENABLE_GPU_DEMAND,
    CONF_UPDATE_INTERVAL_MIN,
    DEFAULT_ENABLE_GPU_DEMAND,
    DEFAULT_UPDATE_INTERVAL_MIN,
    DOMAIN,
)

TOKEN_SCHEMA = vol.Schema({vol.Required("token"): str})


async def validate_token(hass: HomeAssistant, token: str) -> None:
    """Verify the auth cookie against the balance endpoint.

    Raises SaladApiAuthError / SaladApiClientError.
    """
    client = SaladApiClient(async_get_clientsession(hass), token)
    await client.async_get_balance()


class SaladConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Salad Tracker config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_token(self.hass, user_input["token"])
            except SaladApiAuthError:
                errors["base"] = "invalid_auth"
            except SaladApiClientError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Salad Tracker",
                    data={"token": user_input["token"]},
                    options={
                        CONF_UPDATE_INTERVAL_MIN: user_input[
                            CONF_UPDATE_INTERVAL_MIN
                        ],
                        CONF_ENABLE_GPU_DEMAND: user_input[
                            CONF_ENABLE_GPU_DEMAND
                        ],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("token"): str,
                    vol.Required(
                        CONF_UPDATE_INTERVAL_MIN,
                        default=DEFAULT_UPDATE_INTERVAL_MIN,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Required(
                        CONF_ENABLE_GPU_DEMAND,
                        default=DEFAULT_ENABLE_GPU_DEMAND,
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        """Handle reauth when the auth cookie expires."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Collect a fresh auth cookie."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if user_input is not None:
            try:
                await validate_token(self.hass, user_input["token"])
            except SaladApiAuthError:
                errors["base"] = "invalid_auth"
            except SaladApiClientError:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, "token": user_input["token"]}
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=TOKEN_SCHEMA,
            errors=errors,
        )


def _defaults(entry) -> dict[str, Any]:
    return entry.options if entry else {}


class SaladOptionsFlow(config_entries.OptionsFlow):
    """Handle options for a Salad Tracker entry."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = _defaults(self.config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL_MIN,
                        default=current.get(
                            CONF_UPDATE_INTERVAL_MIN,
                            DEFAULT_UPDATE_INTERVAL_MIN,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Required(
                        CONF_ENABLE_GPU_DEMAND,
                        default=current.get(
                            CONF_ENABLE_GPU_DEMAND, DEFAULT_ENABLE_GPU_DEMAND
                        ),
                    ): bool,
                }
            ),
        )
