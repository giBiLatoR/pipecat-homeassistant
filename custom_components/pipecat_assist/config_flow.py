"""Config flow for Pipecat Assist."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_URL, DEFAULT_URL, DOMAIN


async def _validate_url(hass: HomeAssistant, url: str) -> None:
    session = async_get_clientsession(hass)
    async with asyncio.timeout(10):
        async with session.get(f"{url.rstrip('/')}/api/assist/status") as response:
            if response.status >= 400:
                raise aiohttp.ClientError(f"Unexpected status {response.status}")


class PipecatAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Pipecat Assist config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                await _validate_url(self.hass, url)
            except (TimeoutError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                data = {CONF_URL: url}
                return self.async_create_entry(title="Pipecat Assist", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=DEFAULT_URL): str,
                }
            ),
            errors=errors,
        )
