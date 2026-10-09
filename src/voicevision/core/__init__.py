"""Core module exports for voicevision."""

from voicevision.core.config import VoiceVisionConfig
from voicevision.core.protocols import (
    CameraBackend,
    LLMBackend,
    STTBackend,
    TTSBackend,
    VisionBackend,
)
from voicevision.core.registry import BackendRegistry

__all__ = [
    "VoiceVisionConfig",
    "BackendRegistry",
    "LLMBackend",
    "STTBackend",
    "TTSBackend",
    "VisionBackend",
    "CameraBackend",
]
