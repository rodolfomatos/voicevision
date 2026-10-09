"""Tests for voicevision.core.config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from voicevision.core.config import VoiceVisionConfig
from voicevision.core.registry import BackendRegistry


class DummyBackend:
    def generate(self, prompt: str, **kwargs) -> str:
        return "test"


class TestConfig:
    """Test VoiceVisionConfig validation and defaults."""

    def test_defaults(self) -> None:
        config = VoiceVisionConfig()
        assert config.llm_backend == "dummy"
        assert config.stt_backend == "dummy"
        assert config.tts_backend == "dummy"
        assert config.vision_backend == "dummy"
        assert config.camera_backend == "dummy"
        assert config.camera_index == 0
        assert config.camera_resolution == "640x480"
        assert config.camera_resolution_parsed == (640, 480)

    def test_env_var_override(self, monkeypatch) -> None:
        monkeypatch.setenv("VOICEVISION_LLM_BACKEND", "ollama")
        monkeypatch.setenv("VOICEVISION_LLM_MODEL", "qwen3:1.7b")
        config = VoiceVisionConfig()
        assert config.llm_backend == "ollama"
        assert config.llm_model == "qwen3:1.7b"

    def test_env_var_nested(self, monkeypatch) -> None:
        monkeypatch.setenv("VOICEVISION_LLM_PARAMS__TEMPERATURE", "0.7")
        monkeypatch.setenv("VOICEVISION_LLM_PARAMS__MAX_TOKENS", "100")
        config = VoiceVisionConfig()
        assert config.llm_params == {"temperature": "0.7", "max_tokens": "100"}

    def test_camera_resolution_string(self, monkeypatch) -> None:
        monkeypatch.setenv("VOICEVISION_CAMERA_RESOLUTION", "1280x720")
        config = VoiceVisionConfig()
        assert config.camera_resolution == "1280x720"
        assert config.camera_resolution_parsed == (1280, 720)

    def test_camera_resolution_tuple(self, monkeypatch) -> None:
        monkeypatch.setenv("VOICEVISION_CAMERA_RESOLUTION", "[1920, 1080]")
        config = VoiceVisionConfig()
        # JSON format stored as string, parsed correctly
        assert config.camera_resolution == "[1920, 1080]"
        assert config.camera_resolution_parsed == (1920, 1080)

    def test_invalid_resolution_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("VOICEVISION_CAMERA_RESOLUTION", "invalid")
        config = VoiceVisionConfig()
        with pytest.raises(ValueError):
            _ = config.camera_resolution_parsed

    def test_extra_fields_ignored(self, monkeypatch) -> None:
        """Extra env vars are ignored (pydantic-settings behavior)."""
        monkeypatch.setenv("VOICEVISION_UNKNOWN_FIELD", "value")
        # Should not raise - extra fields are ignored
        config = VoiceVisionConfig()
        assert config.llm_backend == "dummy"

    def test_get_backend_kwargs(self) -> None:
        config = VoiceVisionConfig(
            llm_backend="ollama",
            llm_model="qwen3:1.7b",
            llm_params={"temperature": 0.7},
            stt_backend="whisper-cpp",
            stt_model="base",
            stt_language="pt",
            tts_backend="piper",
            tts_voice="pt_BR-faber",
            camera_index=1,
            camera_resolution="1280x720",
        )
        llm_kwargs = config.get_backend_kwargs("llm")
        assert llm_kwargs == {"temperature": 0.7, "model": "qwen3:1.7b"}

        stt_kwargs = config.get_backend_kwargs("stt")
        assert stt_kwargs == {"language": "pt", "model": "base"}

        tts_kwargs = config.get_backend_kwargs("tts")
        assert tts_kwargs == {"voice": "pt_BR-faber"}

        camera_kwargs = config.get_backend_kwargs("camera")
        assert camera_kwargs == {"index": 1, "resolution": (1280, 720)}

    def test_config_with_registered_backends(self) -> None:
        """Config should not fail if backend not yet registered."""
        # Register after config creation (typical usage)
        config = VoiceVisionConfig(llm_backend="ollama")
        BackendRegistry.register("llm", "ollama", DummyBackend)
        # Should be able to create
        instance = BackendRegistry.create("llm", config.llm_backend)
        assert isinstance(instance, DummyBackend)


class TestConfigValidation:
    """Test config validation behavior."""

    def test_camera_index_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            VoiceVisionConfig(camera_index=-1)

    def test_all_param_dicts_default_empty(self) -> None:
        config = VoiceVisionConfig()
        assert config.llm_params == {}
        assert config.stt_params == {}
        assert config.tts_params == {}
        assert config.vision_params == {}
        assert config.camera_params == {}
