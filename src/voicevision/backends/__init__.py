"""Backend implementations for voicevision."""

from __future__ import annotations

from voicevision.backends.adaptive_vad import AdaptiveVadBackend
from voicevision.backends.audio_duplex import (
    AudioProcessor,
    BargeInDetector,
    DuplexAudioSession,
    DuplexConfig,
    EchoCanceller,
)
from voicevision.backends.emotion import (
    SimpleEmotionBackend,
    detect_emotion,
    get_emotion_backend,
)
from voicevision.backends.emotion_ml import MLEmotionBackend
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
from voicevision.backends.speaker_pyannote import (
    PyannoteSpeakerBackend,
    SpeakerStore,
    cosine_similarity,
)
from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.vision import MoondreamBackend
from voicevision.backends.wakeword import FuzzyWakeWordBackend, PorcupineWakeWordBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.core.protocols import EmotionResult

__all__ = [
    "SubprocessBackend",
    "ResidentBackend",
    "WhisperCppBackend",
    "LlamaCppBackend",
    "PiperBackend",
    "WebrtcVadBackend",
    "AdaptiveVadBackend",
    "DuplexAudioSession",
    "DuplexConfig",
    "AudioProcessor",
    "EchoCanceller",
    "BargeInDetector",
    "PorcupineWakeWordBackend",
    "FuzzyWakeWordBackend",
    "MoondreamBackend",
    "OnnxVisionBackend",
    "SimpleEmotionBackend",
    "MLEmotionBackend",
    "EmotionResult",
    "detect_emotion",
    "get_emotion_backend",
    "SimpleSpeakerBackend",
    "PyannoteSpeakerBackend",
    "SpeakerStore",
    "cosine_similarity",
    "identify_speaker",
    "get_speaker_backend",
    "reset_speaker_backend",
]
