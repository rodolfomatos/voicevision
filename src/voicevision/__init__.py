"""voicevision — Modular multimodal AI brick.

Unified interface for LLM, STT, TTS, Vision, and Camera backends.
Target: Ubuntu 22.04+ and Raspberry Pi OS.

Quickstart:
    from voicevision import VoicePipeline, PipelineConfig
    config = PipelineConfig(...)
    with VoicePipeline(config) as vp:
        audio_out = vp.process(audio_in)

Import cost is kept low on purpose: only `typing` is touched at import time.
The Protocol interfaces and the registry are eager because they are free;
`VoiceVisionConfig` is lazy (PEP 562) because pydantic-settings costs ~420 ms
and a caller who only wants the interfaces should not pay it. See B0 in
docs/ROADMAP.md.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from voicevision.core import (
    BackendRegistry,
    CameraBackend,
    LLMBackend,
    STTBackend,
    TTSBackend,
    VisionBackend,
)
from voicevision.errors import (
    BackendExecutionError,
    BackendNotAvailableError,
    ConfigurationError,
    VoiceVisionError,
)
from voicevision.pipeline import PipelineConfig, VoicePipeline

if TYPE_CHECKING:
    from voicevision.core.config import VoiceVisionConfig

_LAZY: dict[str, str] = {
    "VoiceVisionConfig": "voicevision.core.config",
}

__version__ = "0.1.0"

__all__ = [
    "PipelineConfig",
    "VoicePipeline",
    "VoiceVisionConfig",
    "BackendRegistry",
    "LLMBackend",
    "STTBackend",
    "TTSBackend",
    "VisionBackend",
    "CameraBackend",
    "VoiceVisionError",
    "BackendNotAvailableError",
    "BackendExecutionError",
    "ConfigurationError",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Resolve lazy attributes on first access, then cache them."""
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(target), name)
    globals()[name] = value  # cache so the import cost is paid once
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
