"""Backend registry for voicevision.

Provides global backend discovery and instantiation via a class-level registry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from voicevision.core.protocols import (
    CameraBackend,
    LLMBackend,
    STTBackend,
    TTSBackend,
    VisionBackend,
)

T = TypeVar("T")

# Modality keys (must match config field prefixes)
MODALITIES = ("llm", "stt", "tts", "vision", "camera")

# Protocol mapping for type hints
PROTOCOLS: dict[str, type] = {
    "llm": LLMBackend,
    "stt": STTBackend,
    "tts": TTSBackend,
    "vision": VisionBackend,
    "camera": CameraBackend,
}


class BackendRegistry:
    """Global backend registry (singleton pattern via class methods).

    All methods are classmethods — no instantiation needed.
    Backends are registered by modality and name.
    """

    _registry: dict[str, dict[str, type]] = {modality: {} for modality in MODALITIES}
    _factories: dict[str, dict[str, Callable[..., Any]]] = {modality: {} for modality in MODALITIES}

    @classmethod
    def register(
        cls,
        modality: str,
        name: str,
        backend_class: type[T],
        factory: Callable[..., T] | None = None,
    ) -> None:
        """Register a backend class for a modality.

        Args:
            modality: One of "llm", "stt", "tts", "vision", "camera".
            name: Unique name for this backend (e.g., "ollama", "dummy").
            backend_class: Class implementing the modality's Protocol.
            factory: Optional factory function for custom instantiation.
                     If not provided, `backend_class(**kwargs)` is used.

        Raises:
            ValueError: If modality invalid or name already registered.
        """
        if modality not in MODALITIES:
            raise ValueError(f"Invalid modality: {modality}. Must be one of {MODALITIES}")
        if name in cls._registry[modality]:
            raise ValueError(f"Backend '{name}' already registered for modality '{modality}'")
        cls._registry[modality][name] = backend_class
        if factory is not None:
            cls._factories[modality][name] = factory

    @classmethod
    def get(cls, modality: str, name: str) -> type:
        """Get registered backend class.

        Args:
            modality: Modality key.
            name: Backend name.

        Returns:
            Backend class.

        Raises:
            KeyError: If modality or name not found.
        """
        try:
            return cls._registry[modality][name]
        except KeyError as e:
            raise KeyError(f"Backend '{name}' not found for modality '{modality}'") from e

    @classmethod
    def list(cls, modality: str) -> list[str]:
        """List registered backend names for a modality.

        Args:
            modality: Modality key.

        Returns:
            Sorted list of backend names.

        Raises:
            ValueError: If modality invalid.
        """
        if modality not in MODALITIES:
            raise ValueError(f"Invalid modality: {modality}")
        return sorted(cls._registry[modality].keys())

    @classmethod
    def create(cls, modality: str, name: str, **kwargs: Any) -> Any:
        """Create backend instance.

        Args:
            modality: Modality key.
            name: Backend name.
            **kwargs: Passed to backend constructor or factory.

        Returns:
            Backend instance.

        Raises:
            KeyError: If backend not registered.
            TypeError: If instantiation fails.
        """
        backend_class = cls.get(modality, name)
        factory = cls._factories[modality].get(name)
        if factory is not None:
            return factory(**kwargs)
        return backend_class(**kwargs)

    @classmethod
    def is_registered(cls, modality: str, name: str) -> bool:
        """Check if backend is registered."""
        return modality in cls._registry and name in cls._registry[modality]

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations. For testing only."""
        for modality in MODALITIES:
            cls._registry[modality].clear()
            cls._factories[modality].clear()

    @classmethod
    def get_protocol(cls, modality: str) -> type:
        """Get the Protocol class for a modality."""
        if modality not in PROTOCOLS:
            raise ValueError(f"Invalid modality: {modality}")
        return PROTOCOLS[modality]
