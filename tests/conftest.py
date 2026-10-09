"""Pytest configuration and fixtures for voicevision."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest

from voicevision.core.registry import BackendRegistry


@pytest.fixture(autouse=True)
def clean_registry() -> Generator[None, None, None]:
    """Reset registry before each test."""
    BackendRegistry.clear()
    yield
    BackendRegistry.clear()


@pytest.fixture
def dummy_config() -> dict[str, Any]:
    """Minimal config for dummy backends."""
    return {
        "llm_backend": "dummy",
        "stt_backend": "dummy",
        "tts_backend": "dummy",
        "vision_backend": "dummy",
        "camera_backend": "dummy",
    }


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up mock environment variables."""
    env = {
        "VOICEVISION_LLM_BACKEND": "dummy",
        "VOICEVISION_STT_BACKEND": "dummy",
        "VOICEVISION_TTS_BACKEND": "dummy",
        "VOICEVISION_VISION_BACKEND": "dummy",
        "VOICEVISION_CAMERA_BACKEND": "dummy",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all VOICEVISION_ env vars."""
    for key in list(os.environ.keys()):
        if key.startswith("VOICEVISION_"):
            monkeypatch.delenv(key, raising=False)
