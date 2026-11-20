"""Configuration for voicevision.

Uses pydantic-settings for validation and environment variable loading.
All fields optional with sensible defaults (dummy backends).

Version: 2.0.0 (M1 Core Abstraction)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from voicevision.core.registry import ProviderRegistry

ModalityName = Literal[
    "llm", "stt", "tts", "vision", "camera", "vad", "wakeword", "speakerid", "emotion"
]


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

    # VAD
    vad_backend: str = Field(default="webrtcvad", description="VAD backend name")
    vad_params: dict[str, Any] = Field(default_factory=dict)

    # Camera
    camera_backend: str = Field(default="dummy", description="Camera backend name")
    camera_index: int = Field(default=0, ge=0, description="Camera device index")
    camera_resolution: str = Field(default="640x480", description="Capture resolution as 'WxH'")
    camera_params: dict[str, Any] = Field(default_factory=dict)

    # Wake Word
    wakeword_backend: str = Field(default="dummy", description="Wake word backend name")
    wakeword_params: dict[str, Any] = Field(default_factory=dict)

    # Speaker ID
    speakerid_backend: str = Field(default="simple", description="Speaker ID backend name")
    speakerid_params: dict[str, Any] = Field(default_factory=dict)

    # Emotion
    emotion_backend: str = Field(default="simple", description="Emotion backend name")
    emotion_params: dict[str, Any] = Field(default_factory=dict)

    # Full-duplex audio (T094)
    duplex_enabled: bool = Field(
        default=False, description="Enable simultaneous capture and playback"
    )
    duplex_params: dict[str, Any] = Field(default_factory=dict)

    @property
    def camera_resolution_parsed(self) -> tuple[int, int]:
        """Get camera resolution as parsed tuple."""
        return _parse_resolution(self.camera_resolution)

    @model_validator(mode="after")
    def _validate_backends_registered(self) -> VoiceVisionConfig:
        """Validate that configured backends are registered (or will be)."""
        from voicevision.core.registry import ProviderRegistry

        registry = ProviderRegistry.get_instance()
        for modality in (
            "llm", "stt", "tts", "vision", "camera",
            "vad", "wakeword", "speakerid", "emotion"
        ):
            backend_name = getattr(self, f"{modality}_backend")
            if backend_name and not registry.is_registered(modality, backend_name):
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


# -- PipelineConfig (used by VoicePipeline) ------------------------------------


@dataclass
class PipelineConfig:
    """Configuration for the voice pipeline.

    This is the internal config used by VoicePipeline, distinct from
    VoiceVisionConfig which is the external/env-facing config.
    """

    # VAD
    vad_aggressiveness: int = 2
    vad_sample_rate: int = 16000
    vad_silence_ms: int = 500
    vad_max_utterance_ms: int = 30000

    # STT
    stt_model: str = ""
    stt_language: str = "en"

    # LLM
    llm_model: str = ""
    llm_host: str = "127.0.0.1"
    llm_port: int = 8080
    llm_context_size: int = 2048
    llm_gpu_layers: int = 0
    llm_threads: int = 4
    llm_temperature: float = 0.7
    llm_max_tokens: int = 512

    # TTS
    tts_model: str = ""
    tts_voice: str = ""
    tts_length_scale: float = 1.0

    # Vision
    vision_backend: str = "llama-cpp"
    vision_model: str = ""
    vision_host: str = "127.0.0.1"
    vision_port: int = 8081

    # Filter
    enable_thinking_filter: bool = True

    # Conversation memory
    max_context_utterances: int = 5
    conversation_path: str = ""
    conversation_ttl_days: int = 30
    max_history_size: int = 100

    # Streaming
    streaming_enabled: bool = False

    # Mute TTS
    mute_tts: bool = False

    # Emotion detection
    emotion_enabled: bool = False
    emotion_backend: str = "simple"
    emotion_params: dict[str, Any] = field(default_factory=dict)

    # Speaker identification
    speaker_enabled: bool = False
    speakerid_backend: str = "simple"
    speakerid_params: dict[str, Any] = field(default_factory=dict)

    # Full-duplex audio (T094)
    duplex_enabled: bool = False
    duplex_params: dict[str, Any] = field(default_factory=dict)

    # Provider registry (populated from VoiceVisionConfig)
    _provider_registry: ProviderRegistry | None = field(default=None, repr=False)

    @property
    def provider_registry(self) -> ProviderRegistry:
        """Get or create provider registry."""
        if self._provider_registry is None:
            from voicevision.core.registry import ProviderRegistry
            self._provider_registry = ProviderRegistry.get_instance().create_from_config(self)
        return self._provider_registry

    def validate(self) -> None:
        """Fail-fast validation of required fields."""

        self._validate_required_fields()
        self._validate_numeric_ranges()
        self._validate_vision_config()
        self._validate_provider_availability()

    def _validate_required_fields(self) -> None:
        from voicevision.errors import ConfigurationError

        if not self.stt_model:
            raise ConfigurationError("stt_model is required", field="stt_model")
        if not self.llm_model:
            raise ConfigurationError("llm_model is required", field="llm_model")
        if not self.tts_model:
            raise ConfigurationError("tts_model is required", field="tts_model")

    def _validate_numeric_ranges(self) -> None:
        from voicevision.errors import ConfigurationError

        checks = [
            (
                0 <= self.vad_aggressiveness <= 3,
                "vad_aggressiveness must be 0-3",
                "vad_aggressiveness",
                self.vad_aggressiveness,
            ),
            (
                self.vad_sample_rate in (8000, 16000, 32000, 48000),
                "vad_sample_rate must be 8000, 16000, 32000, or 48000",
                "vad_sample_rate",
                self.vad_sample_rate,
            ),
            (
                self.vad_silence_ms > 0,
                "vad_silence_ms must be positive",
                "vad_silence_ms",
                self.vad_silence_ms,
            ),
            (
                self.vad_max_utterance_ms > 0,
                "vad_max_utterance_ms must be positive",
                "vad_max_utterance_ms",
                self.vad_max_utterance_ms,
            ),
            (
                0 <= self.llm_temperature <= 2,
                "llm_temperature must be 0-2",
                "llm_temperature",
                self.llm_temperature,
            ),
            (
                self.llm_max_tokens > 0,
                "llm_max_tokens must be positive",
                "llm_max_tokens",
                self.llm_max_tokens,
            ),
            (
                self.tts_length_scale > 0,
                "tts_length_scale must be positive",
                "tts_length_scale",
                self.tts_length_scale,
            ),
            (
                self.max_context_utterances >= 0,
                "max_context_utterances must be non-negative",
                "max_context_utterances",
                self.max_context_utterances,
            ),
            (
                self.conversation_ttl_days > 0,
                "conversation_ttl_days must be positive",
                "conversation_ttl_days",
                self.conversation_ttl_days,
            ),
            (
                self.max_history_size > 0,
                "max_history_size must be positive",
                "max_history_size",
                self.max_history_size,
            ),
        ]

        for condition, message, field_name, value in checks:
            if not condition:
                raise ConfigurationError(message, field=field_name, value=value)

    def _validate_vision_config(self) -> None:
        from voicevision.errors import ConfigurationError

        if self.vision_model and self.vision_backend not in ("llama-cpp", "onnx"):
            raise ConfigurationError(
                f"vision_backend must be 'llama-cpp' or 'onnx', got {self.vision_backend!r}",
                field="vision_backend",
                value=self.vision_backend,
            )

    def _validate_provider_availability(self) -> None:
        from voicevision.errors import ConfigurationError

        registry = self.provider_registry
        for modality in ("stt", "llm", "tts", "vad"):
            default_name = registry.get_default_name(modality)
            if default_name:
                try:
                    provider = registry.get_default(modality)
                    if not provider.available():
                        raise ConfigurationError(
                            f"Default {modality} provider {default_name!r} is not available",
                            field=f"{modality}_backend",
                            value=default_name,
                        )
                except Exception as exc:
                    raise ConfigurationError(
                        f"Failed to initialize {modality} provider: {exc}",
                        field=f"{modality}_backend",
                    ) from exc


def create_pipeline_config_from_env() -> PipelineConfig:
    """Create PipelineConfig from VoiceVisionConfig (environment)."""
    from voicevision.core.config import VoiceVisionConfig

    env_config = VoiceVisionConfig()
    return PipelineConfig(
        # VAD
        vad_aggressiveness=env_config.vad_params.get("aggressiveness", 2),
        vad_sample_rate=env_config.vad_params.get("sample_rate", 16000),
        vad_silence_ms=env_config.vad_params.get("silence_ms", 500),
        vad_max_utterance_ms=env_config.vad_params.get("max_utterance_ms", 30000),
        # STT
        stt_model=env_config.stt_model,
        stt_language=env_config.stt_language,
        # LLM
        llm_model=env_config.llm_model,
        llm_host=env_config.llm_params.get("host", "127.0.0.1"),
        llm_port=env_config.llm_params.get("port", 8080),
        llm_context_size=env_config.llm_params.get("context_size", 2048),
        llm_gpu_layers=env_config.llm_params.get("gpu_layers", 0),
        llm_threads=env_config.llm_params.get("threads", 4),
        llm_temperature=env_config.llm_params.get("temperature", 0.7),
        llm_max_tokens=env_config.llm_params.get("max_tokens", 512),
        # TTS
        tts_model=env_config.tts_model,
        tts_voice=env_config.tts_voice,
        tts_length_scale=env_config.tts_params.get("length_scale", 1.0),
        # Vision
        vision_backend=env_config.vision_backend,
        vision_model=env_config.vision_model,
        vision_host=env_config.vision_params.get("host", "127.0.0.1"),
        vision_port=env_config.vision_params.get("port", 8081),
        # Filter
        enable_thinking_filter=True,
        # Conversation
        conversation_path=env_config.camera_params.get("conversation_path", ""),
        # Streaming
        streaming_enabled=False,
        # Mute
        mute_tts=False,
        # Emotion/Speaker
        emotion_enabled=env_config.emotion_backend != "dummy",
        emotion_backend=env_config.emotion_backend,
        emotion_params=dict(env_config.emotion_params),
        speaker_enabled=env_config.speakerid_backend != "dummy",
        speakerid_backend=env_config.speakerid_backend,
        speakerid_params=dict(env_config.speakerid_params),
        # Full-duplex audio
        duplex_enabled=env_config.duplex_enabled,
        duplex_params=dict(env_config.duplex_params),
    )
