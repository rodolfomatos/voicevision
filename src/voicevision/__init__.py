"""voicevision — Modular multimodal AI brick.

Unified interface for LLM, STT, TTS, Vision, and Camera backends.
Cross-platform: Ubuntu, Raspberry Pi, Android (Termux/ChaQuopy).

Quickstart:
    from voicevision import VoiceVision
    vv = VoiceVision()
    print(vv.llm.generate("Hello!"))
    vv.close()
"""

from voicevision.core import (
    BackendRegistry,
    CameraBackend,
    LLMBackend,
    STTBackend,
    TTSBackend,
    VisionBackend,
    VoiceVisionConfig,
)

__version__ = "0.1.0"

__all__ = [
    "VoiceVisionConfig",
    "BackendRegistry",
    "LLMBackend",
    "STTBackend",
    "TTSBackend",
    "VisionBackend",
    "CameraBackend",
    "__version__",
]
