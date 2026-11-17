"""Provider Registry with Dependency Injection.

Manages provider registration, instantiation, and lifecycle.
Enables true provider interchangeability via configuration.

Version: 2.0.0 (M1 Core Abstraction)
"""

from __future__ import annotations

import builtins
import contextlib
import threading
from typing import TYPE_CHECKING, Any, ClassVar

from voicevision.core.protocols import (
    ModalityName,
    Provider,
)
from voicevision.errors import ConfigurationError

if TYPE_CHECKING:
    from voicevision.core.config import PipelineConfig


class _ProviderEntry:
    """Internal registry entry for a provider."""

    def __init__(
        self,
        modality: ModalityName,
        name: str,
        provider: Provider | None = None,
        provider_class: type[Provider] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.modality = modality
        self.name = name
        self._instance = provider
        self._provider_class = provider_class
        self._kwargs = kwargs or {}
        self._initialized = False

    def get_instance(self) -> Provider:
        """Get or create provider instance (lazy initialization)."""
        if self._instance is None and self._provider_class is not None:
            self._instance = self._provider_class(**self._kwargs)
        if self._instance is None:
            raise ConfigurationError(
                f"Provider {self.name!r} ({self.modality}) not instantiated",
                field="provider",
                value=self.name,
            )
        return self._instance

    def set_instance(self, provider: Provider) -> None:
        """Set provider instance directly."""
        self._instance = provider
        self._initialized = True

    @property
    def is_lazy(self) -> bool:
        return self._provider_class is not None

    @property
    def provider_class(self) -> type[Provider] | None:
        return self._provider_class


class ProviderRegistry:
    """Registry for managing providers across modalities.

    Supports both eager (instance) and lazy (class + kwargs) registration.
    Thread-safe singleton with testing isolation support.
    """

    _instance: ClassVar[ProviderRegistry | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls) -> ProviderRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._providers: dict[ModalityName, dict[str, _ProviderEntry]] = {}
        self._defaults: dict[ModalityName, str] = {}
        self._init_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> ProviderRegistry:
        """Get the singleton registry instance."""
        if cls._instance is None:
            cls()
        # cls._instance is guaranteed to be set after cls() call
        assert cls._instance is not None
        return cls._instance

    @classmethod
    def for_testing(cls) -> ProviderRegistry:
        """Create a new isolated registry for testing.

        Does not affect the singleton instance.
        """
        # Bypass singleton by creating instance directly
        registry = object.__new__(cls)
        registry._initialize()
        return registry

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset singleton (for testing only)."""
        with cls._lock:
            cls._instance = None

    # -- Registration --------------------------------------------------------

    def register(
        self,
        provider: Provider,
        *,
        modality: ModalityName | None = None,
        name: str | None = None,
        default: bool = False,
    ) -> None:
        """Register a provider instance.

        Args:
            provider: Provider instance implementing the protocol.
            modality: Modality name (defaults to provider.modality).
            name: Provider name (defaults to provider.name).
            default: Set as default for modality.
        """
        modality = modality or provider.modality
        name = name or provider.name

        with self._init_lock:
            if modality not in self._providers:
                self._providers[modality] = {}
            entry = _ProviderEntry(modality, name, provider=provider)
            self._providers[modality][name] = entry
            if default or modality not in self._defaults:
                self._defaults[modality] = name

    def register_class(
        self,
        modality: ModalityName,
        name: str,
        provider_class: type[Provider],
        *,
        default: bool = False,
        **kwargs: Any,
    ) -> None:
        """Register a provider class for lazy instantiation.

        Args:
            modality: Modality name (e.g., "stt", "llm").
            name: Provider name.
            provider_class: Provider class implementing the protocol.
            default: Set as default for modality.
            **kwargs: Constructor arguments for lazy instantiation.
        """
        with self._init_lock:
            if modality not in self._providers:
                self._providers[modality] = {}
            entry = _ProviderEntry(
                modality, name, provider_class=provider_class, kwargs=kwargs
            )
            self._providers[modality][name] = entry
            if default or modality not in self._defaults:
                self._defaults[modality] = name

    # -- Retrieval -----------------------------------------------------------

    def get(self, modality: ModalityName, name: str) -> Provider:
        """Get provider instance by name.

        Args:
            modality: Modality name.
            name: Provider name.

        Returns:
            Initialized provider instance.

        Raises:
            ConfigurationError: If modality or provider not registered.
        """
        with self._init_lock:
            if modality not in self._providers:
                raise ConfigurationError(
                    f"Modality {modality!r} not registered",
                    field="modality",
                    value=modality,
                )
            if name not in self._providers[modality]:
                raise ConfigurationError(
                    f"Provider {name!r} not registered for modality {modality!r}",
                    field="provider",
                    value=name,
                )
            return self._providers[modality][name].get_instance()

    def get_default(self, modality: ModalityName) -> Provider:
        """Get default provider for modality.

        Args:
            modality: Modality name.

        Returns:
            Default provider instance.

        Raises:
            ConfigurationError: If no default configured or modality not registered.
        """
        with self._init_lock:
            if modality not in self._defaults:
                raise ConfigurationError(
                    f"No default provider configured for modality {modality!r}",
                    field="modality",
                    value=modality,
                )
            return self.get(modality, self._defaults[modality])

    # -- Discovery -----------------------------------------------------------

    def list(self, modality: ModalityName) -> builtins.list[str]:
        """List registered provider names for modality."""
        with self._init_lock:
            if modality not in self._providers:
                return []
            return list(self._providers[modality].keys())

    def list_all(self) -> dict[ModalityName, builtins.list[str]]:
        """List all registered providers by modality."""
        with self._init_lock:
            return {mod: list(entries.keys()) for mod, entries in self._providers.items()}

    def get_default_name(self, modality: ModalityName) -> str | None:
        """Get default provider name for modality (or None)."""
        with self._init_lock:
            return self._defaults.get(modality)

    def set_default(self, modality: ModalityName, name: str) -> None:
        """Set default provider for modality."""
        with self._init_lock:
            if modality not in self._providers or name not in self._providers[modality]:
                raise ConfigurationError(
                    f"Provider {name!r} not registered for modality {modality!r}",
                    field="provider",
                    value=name,
                )
            self._defaults[modality] = name

    # -- Lifecycle -----------------------------------------------------------

    def initialize_all(self) -> None:
        """Initialize all registered providers (call lifecycle.initialize)."""
        with self._init_lock:
            for _modality, entries in self._providers.items():
                for entry in entries.values():
                    provider = entry.get_instance()
                    provider.lifecycle().initialize()

    def shutdown_all(self) -> None:
        """Shutdown all providers (call lifecycle.shutdown)."""
        with self._init_lock:
            for _modality, entries in self._providers.items():
                for entry in entries.values():
                    if entry._instance is not None:
                        with contextlib.suppress(Exception):
                            entry._instance.lifecycle().shutdown()

    def health_check_all(self) -> dict[ModalityName, dict[str, bool]]:
        """Health check all providers."""
        with self._init_lock:
            result: dict[ModalityName, dict[str, bool]] = {}
            for modality, entries in self._providers.items():
                result[modality] = {}
                for name, entry in entries.items():
                    try:
                        provider = entry.get_instance()
                        result[modality][name] = provider.lifecycle().health_check()
                    except Exception:
                        result[modality][name] = False
            return result

    # -- Config Factory ------------------------------------------------------

    def create_from_config(self, config: PipelineConfig) -> ProviderRegistry:
        """Create a registry populated from PipelineConfig.

        Args:
            config: PipelineConfig with modality_* fields.

        Returns:
            New ProviderRegistry instance with providers registered.
        """
        # Import here to avoid circular dependency
        from voicevision.backends import (
            LlamaCppBackend,
            MoondreamBackend,
            OnnxVisionBackend,
            PiperBackend,
            SimpleEmotionBackend,
            SimpleSpeakerBackend,
            WebrtcVadBackend,
            WhisperCppBackend,
        )

        registry = ProviderRegistry.for_testing()

        # STT
        if config.stt_model:
            registry.register_class(
                "stt",
                "whisper-cpp",
                WhisperCppBackend,  # type: ignore[arg-type]
                default=True,
                model=config.stt_model,
                language=config.stt_language,
            )

        # LLM
        if config.llm_model:
            registry.register_class(
                "llm",
                "llama-cpp",
                LlamaCppBackend,  # type: ignore[arg-type]
                default=True,
                model=config.llm_model,
                host=config.llm_host,
                port=config.llm_port,
                context_size=config.llm_context_size,
                gpu_layers=config.llm_gpu_layers,
                threads=config.llm_threads,
            )

        # TTS
        if config.tts_model:
            registry.register_class(
                "tts",
                "piper",
                PiperBackend,  # type: ignore[arg-type]
                default=True,
                model=config.tts_model,
                voice=config.tts_voice,
                length_scale=config.tts_length_scale,
            )

        # VAD
        registry.register_class(
            "vad",
            "webrtcvad",
            WebrtcVadBackend,  # type: ignore[arg-type]
            default=True,
            aggressiveness=config.vad_aggressiveness,
            sample_rate=config.vad_sample_rate,
            silence_ms=config.vad_silence_ms,
            max_utterance_ms=config.vad_max_utterance_ms,
        )

        # Vision
        if config.vision_model:
            if config.vision_backend == "onnx":
                registry.register_class(
                    "vision",
                    "onnx",
                    OnnxVisionBackend,  # type: ignore[arg-type]
                    default=True,
                    model=config.vision_model,
                )
            else:
                registry.register_class(
                    "vision",
                    "llama-cpp",
                    MoondreamBackend,  # type: ignore[arg-type]
                    default=True,
                    model=config.vision_model,
                    host=config.vision_host,
                    port=config.vision_port,
                )

        # Emotion
        if config.emotion_enabled:
            registry.register_class(
                "emotion",
                "simple",
                SimpleEmotionBackend,
                default=True,
            )

        # Speaker ID
        if config.speaker_enabled:
            registry.register_class(
                "speakerid",
                "simple",
                SimpleSpeakerBackend,
                default=True,
            )

        return registry

    # -- Validation ----------------------------------------------------------

    def is_registered(self, modality: ModalityName, name: str) -> bool:
        """Check if provider is registered."""
        with self._init_lock:
            return modality in self._providers and name in self._providers[modality]

    def validate_config(self, config: PipelineConfig) -> builtins.list[str]:
        """Validate config against registered providers.

        Returns list of warnings (not errors — providers may register later).
        """
        warnings_list: list[str] = []
        modalities = ("stt", "llm", "tts", "vad", "vision", "emotion", "speakerid")
        for modality in modalities:
            backend_name = getattr(config, f"{modality}_backend", None) or getattr(
                config, f"{modality}_provider", None
            )
            if backend_name and not self.is_registered(modality, backend_name):
                warnings_list.append(
                    f"Provider {backend_name!r} for {modality} not yet registered "
                    f"(available: {self.list(modality)})"
                )
        return warnings_list


# -- Backwards Compatibility -------------------------------------------------

class BackendRegistry:
    """Legacy wrapper for backwards compatibility."""

    @classmethod
    def is_registered(cls, modality: str, name: str) -> bool:
        return ProviderRegistry.get_instance().is_registered(modality, name)

    @classmethod
    def register(cls, modality: str, name: str, backend_class: type) -> None:
        ProviderRegistry.get_instance().register_class(modality, name, backend_class, default=False)

    @classmethod
    def get(cls, modality: str, name: str) -> Any:
        return ProviderRegistry.get_instance().get(modality, name)

    @classmethod
    def list(cls, modality: str) -> list[str]:
        return ProviderRegistry.get_instance().list(modality)

    @classmethod
    def create(cls, modality: str, name: str, **_kwargs: Any) -> Any:
        return ProviderRegistry.get_instance().get(modality, name)
