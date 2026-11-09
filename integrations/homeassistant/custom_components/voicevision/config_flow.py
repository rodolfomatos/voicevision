"""Config flow for the voicevision integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from voicevision.client import VoiceVisionClient, VoiceVisionClientError

from .const import (
    CONF_BASE_URL,
    CONF_TIMEOUT,
    CONF_TOKEN,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
        vol.Optional(CONF_TOKEN, default=""): str,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            int,
            vol.Range(min=1, max=600),
        ),
    }
)


class VoiceVisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Ask for the server URL and verify it with /health."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> Any:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = VoiceVisionClient(
                base_url=user_input[CONF_BASE_URL],
                token=user_input.get(CONF_TOKEN, ""),
                timeout=user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            )
            try:
                await self.hass.async_add_executor_job(client.health)
            except (VoiceVisionClientError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="voicevision", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
