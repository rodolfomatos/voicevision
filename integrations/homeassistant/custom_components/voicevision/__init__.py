"""Home Assistant custom component for voicevision.

The component is a thin adapter: Home Assistant services translate into calls
on :class:`voicevision.client.VoiceVisionClient`, and every result is fired on
the event bus as ``voicevision_response``. Automation authors decide what to do
with the answer (speak it, send it to a phone, store it).

The blocking HTTP calls run in Home Assistant's executor, never on the event
loop.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from voicevision.client import VoiceVisionClient, VoiceVisionClientError

from .const import (
    CONF_BASE_URL,
    CONF_TIMEOUT,
    CONF_TOKEN,
    DEFAULT_TIMEOUT,
    DOMAIN,
    EVENT_RESPONSE,
    MAX_TOKENS,
    SERVICE_CONVERSE,
    SERVICE_DESCRIBE,
    SERVICE_TRANSCRIBE,
)

_LOGGER = logging.getLogger(__name__)

CONVERSE_SCHEMA = vol.Schema(
    {
        vol.Required("text"): str,
        vol.Optional("max_tokens"): vol.All(int, vol.Range(min=1, max=MAX_TOKENS)),
    }
)

TRANSCRIBE_SCHEMA = vol.Schema(
    {
        vol.Required("audio_file"): str,
        vol.Optional("language"): str,
    }
)

DESCRIBE_SCHEMA = vol.Schema(
    {
        vol.Required("image_file"): str,
        vol.Optional("question"): str,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """YAML setup is not supported; entries come from the config flow."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Create one client per config entry and register services once."""
    client = VoiceVisionClient(
        base_url=entry.data.get(CONF_BASE_URL, "http://127.0.0.1:8765"),
        token=entry.data.get(CONF_TOKEN, ""),
        timeout=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    if not hass.services.has_service(DOMAIN, SERVICE_CONVERSE):
        _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Any) -> bool:
    """Forget the client for an unloaded entry."""
    clients = hass.data.get(DOMAIN, {})
    clients.pop(entry.entry_id, None)
    return True


def _client(hass: HomeAssistant) -> VoiceVisionClient:
    clients: dict[str, VoiceVisionClient] = hass.data.get(DOMAIN, {})
    if not clients:
        raise VoiceVisionClientError("no voicevision config entry is loaded")
    # One entry is the common case; with several, the first is the default.
    return next(iter(clients.values()))


def _register_services(hass: HomeAssistant) -> None:
    async def async_converse(call: ServiceCall) -> None:
        client = _client(hass)
        text: str = call.data["text"]
        max_tokens: int | None = call.data.get("max_tokens")
        try:
            result = await hass.async_add_executor_job(
                client.converse,
                text,
                max_tokens,
            )
        except VoiceVisionClientError as exc:
            _LOGGER.error("voicevision converse failed: %s", exc)
            return
        hass.bus.async_fire(
            EVENT_RESPONSE,
            {
                "service": SERVICE_CONVERSE,
                "text": text,
                "response": result.get("response", ""),
            },
        )

    async def async_transcribe(call: ServiceCall) -> None:
        client = _client(hass)
        audio = await hass.async_add_executor_job(
            Path(call.data["audio_file"]).read_bytes
        )
        try:
            result = await hass.async_add_executor_job(
                client.transcribe,
                audio,
                call.data.get("language"),
            )
        except VoiceVisionClientError as exc:
            _LOGGER.error("voicevision transcribe failed: %s", exc)
            return
        hass.bus.async_fire(
            EVENT_RESPONSE,
            {
                "service": SERVICE_TRANSCRIBE,
                "audio_file": call.data["audio_file"],
                **result,
            },
        )

    async def async_describe(call: ServiceCall) -> None:
        client = _client(hass)
        image = await hass.async_add_executor_job(
            Path(call.data["image_file"]).read_bytes
        )
        try:
            result = await hass.async_add_executor_job(
                client.describe,
                image,
                call.data.get("question"),
            )
        except VoiceVisionClientError as exc:
            _LOGGER.error("voicevision describe failed: %s", exc)
            return
        hass.bus.async_fire(
            EVENT_RESPONSE,
            {
                "service": SERVICE_DESCRIBE,
                "image_file": call.data["image_file"],
                **result,
            },
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONVERSE,
        async_converse,
        schema=CONVERSE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRANSCRIBE,
        async_transcribe,
        schema=TRANSCRIBE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DESCRIBE,
        async_describe,
        schema=DESCRIBE_SCHEMA,
    )
