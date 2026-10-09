"""Core module exports for voicevision.

`VoiceVisionConfig` is loaded lazily (PEP 562). Importing it eagerly costs
~420 ms because pydantic-settings pulls in pydantic and its migration shims,
which would make `import voicevision` cost that much for callers who only want
the Protocol interfaces. See B0 in docs/ROADMAP.md.

Protocols and the registry stay eager: they depend only on `typing` and are
effectively free.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from voicevision.core.protocols import (
    CameraBackend,
    LLMBackend,
    STTBackend,
    TTSBackend,
    VisionBackend,
)
from voicevision.core.registry import BackendRegistry

if TYPE_CHECKING:
    from voicevision.core.config import VoiceVisionConfig

_LAZY: dict[str, str] = {
    "VoiceVisionConfig": "voicevision.core.config",
}

__all__ = [
    "BackendRegistry",
    "VoiceVisionConfig",
    "LLMBackend",
    "STTBackend",
    "TTSBackend",
    "VisionBackend",
    "CameraBackend",
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
