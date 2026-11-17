"""Backend implementations for voicevision."""

from __future__ import annotations

from voicevision.backends.emotion import (
    SimpleEmotionBackend,
    detect_emotion,
    get_emotion_backend,
)
from voicevision.backends.llama_cpp import LlamaCppBackend
from voicevision.backends.onnx_vision import OnnxVisionBackend
from voicevision.backends.piper import PiperBackend
from voicevision.backends.resident import ResidentBackend
from voicevision.backends.speaker import (
    SimpleSpeakerBackend,
    get_speaker_backend,
    identify_speaker,
    reset_speaker_backend,
)
from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.vision import MoondreamBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.core.protocols import EmotionResult

__all__ = [
    "SubprocessBackend",
    "ResidentBackend",
    "WhisperCppBackend",
    "LlamaCppBackend",
    "PiperBackend",
    "WebrtcVadBackend",
    "MoondreamBackend",
    "OnnxVisionBackend",
    "SimpleEmotionBackend",
    "EmotionResult",
    "detect_emotion",
    "get_emotion_backend",
    "SimpleSpeakerBackend",
    "identify_speaker",
    "get_speaker_backend",
    "reset_speaker_backend",
]
