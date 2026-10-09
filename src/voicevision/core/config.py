"""Configuration for voicevision.

Uses pydantic-settings for validation and environment variable loading.
All fields optional with sensible defaults (dummy backends).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ModalityName = Literal["llm", "stt", "tts", "vision", "camera"]


def _parse_resolution(v: str | tuple[int, int]) -> tuple[int, int]:
    """Parse resolution from string 'WxH' or tuple (W, H)."""
    if isinstance(v, str):
        # Try JSON array format first: [W, H]
        if v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
                    return (int(parsed[0]), int(parsed[1]))
            except json.JSONDecodeError:
                pass
        # Try WxH format
        parts = v.split("x")
        if len(parts) == 2:
            return (int(parts[0]), int(parts[1]))
        raise ValueError("camera_resolution string must be 'WxH' or '[W, H]' format")
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (int(v[0]), int(v[1]))
    raise ValueError("camera_resolution must be 'WxH' string or [W, H] tuple")


class VoiceVisionConfig(BaseSettings):
    """Global configuration for VoiceVision facade.

    All fields can be overridden via environment variables with prefix VOICEVISION_.
    Example: VOICEVISION_LLM_BACKEND=ollama VOICEVISION_LLM_MODEL=qwen3:1.7b
    """

    model_config = SettingsConfigDict(
        env_prefix="VOICEVISION_",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # LLM
    llm_backend: str = Field(
        default="dummy", description="LLM backend name (registered in registry)"
    )
    llm_model: str = Field(default="", description="Model identifier (path, name, etc.)")
    llm_params: dict[str, Any] = Field(
        default_factory=dict, description="Backend-specific parameters"
    )

    # STT
    stt_backend: str = Field(default="dummy", description="STT backend name")
    stt_model: str = Field(default="", description="STT model path/identifier")
    stt_language: str = Field(default="en", description="Language code for transcription")
    stt_params: dict[str, Any] = Field(default_factory=dict)

    # TTS
    tts_backend: str = Field(default="dummy", description="TTS backend name")
    tts_voice: str = Field(default="", description="Voice identifier")
    tts_model: str = Field(default="", description="TTS model path")
    tts_params: dict[str, Any] = Field(default_factory=dict)

    # Vision
    vision_backend: str = Field(default="dummy", description="Vision backend name")
    vision_model: str = Field(default="", description="Vision model path")
    vision_params: dict[str, Any] = Field(default_factory=dict)

    # Camera
    camera_backend: str = Field(default="dummy", description="Camera backend name")
    camera_index: int = Field(default=0, ge=0, description="Camera device index")
    camera_resolution: str = Field(default="640x480", description="Capture resolution as 'WxH'")
    camera_params: dict[str, Any] = Field(default_factory=dict)

    @property
    def camera_resolution_parsed(self) -> tuple[int, int]:
        """Get camera resolution as parsed tuple."""
        return _parse_resolution(self.camera_resolution)

    @model_validator(mode="after")
    def _validate_backends_registered(self) -> VoiceVisionConfig:
        """Validate that configured backends are registered (or will be)."""
        from voicevision.core.registry import BackendRegistry

        for modality in ("llm", "stt", "tts", "vision", "camera"):
            backend_name = getattr(self, f"{modality}_backend")
            if backend_name and not BackendRegistry.is_registered(modality, backend_name):
                # Don't fail here — backends may be registered after config creation
                # Validation happens at VoiceVision facade construction
                pass
        return self

    def get_backend_kwargs(self, modality: ModalityName) -> dict[str, Any]:
        """Get kwargs for backend instantiation."""
        base = getattr(self, f"{modality}_params", {}).copy()
        model_field = f"{modality}_model"
        if model_field in self.__class__.model_fields:
            model_val = getattr(self, model_field)
            if model_val:
                base["model"] = model_val
        # Add modality-specific fields
        if modality == "llm":
            pass  # model already handled
        elif modality == "stt":
            if self.stt_language:
                base["language"] = self.stt_language
        elif modality == "tts":
            if self.tts_voice:
                base["voice"] = self.tts_voice
        elif modality == "camera":
            base["index"] = self.camera_index
            base["resolution"] = self.camera_resolution_parsed
        return base
