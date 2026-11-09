"""Constants for the voicevision Home Assistant integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "voicevision"

CONF_BASE_URL: Final = "base_url"
CONF_TOKEN: Final = "token"
CONF_TIMEOUT: Final = "timeout"

DEFAULT_BASE_URL: Final = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT: Final = 120

EVENT_RESPONSE: Final = "voicevision_response"

SERVICE_CONVERSE: Final = "converse"
SERVICE_TRANSCRIBE: Final = "transcribe"
SERVICE_DESCRIBE: Final = "describe"

MAX_TOKENS: Final = 8192
