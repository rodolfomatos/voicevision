"""Tests for voicevision.core.registry (M1 ProviderRegistry)."""

from __future__ import annotations

import pytest

from voicevision.core.protocols import ProviderCapabilities, ProviderLifecycle
from voicevision.core.registry import BackendRegistry, ProviderRegistry


class DummyLLM:
    name = "dummy"
    modality = "llm"

    def generate(self, prompt: str, **kwargs: object) -> str:
        return "test"

    def generate_stream(self, prompt: str, **kwargs: object):
        yield "test"

    def complete(self, prompt: str, **kwargs: object):
        from voicevision.core.protocols import Completion
        return Completion(content="test")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        return True

    @classmethod
    def available(cls) -> bool:
        return True

    @classmethod
    def install_hint(cls) -> str:
        return "Built-in"


class DummyLLMWithKwargs:
    name = "dummy"
    modality = "llm"

    def __init__(self, custom_param: str = "default"):
        self.custom_param = custom_param

    def generate(self, prompt: str, **kwargs: object) -> str:
        return self.custom_param

    def generate_stream(self, prompt: str, **kwargs: object):
        yield self.custom_param

    def complete(self, prompt: str, **kwargs: object):
        from voicevision.core.protocols import Completion
        return Completion(content=self.custom_param)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        return True

    @classmethod
    def available(cls) -> bool:
        return True

    @classmethod
    def install_hint(cls) -> str:
        return "Built-in"


class TestProviderRegistry:
    """Test ProviderRegistry CRUD operations."""

    def test_register_and_get_instance(self) -> None:
        registry = ProviderRegistry.for_testing()
        provider = DummyLLM()
        registry.register(provider, modality="llm", name="test")
        retrieved = registry.get("llm", "test")
        assert retrieved is provider

    def test_register_class_lazy(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "test", DummyLLM, default=True)
        # Should not instantiate yet
        assert registry._providers["llm"]["test"]._instance is None
        # Now get should instantiate
        instance = registry.get("llm", "test")
        assert isinstance(instance, DummyLLM)
        assert instance.generate("prompt") == "test"

    def test_register_class_with_kwargs(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class(
            "llm",
            "kwarg",
            DummyLLMWithKwargs,
            custom_param="custom_value",
        )
        instance = registry.get("llm", "kwarg")
        assert isinstance(instance, DummyLLMWithKwargs)
        assert instance.custom_param == "custom_value"

    def test_get_default(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "test", DummyLLM, default=True)
        default = registry.get_default("llm")
        assert isinstance(default, DummyLLM)

    def test_list_backends(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "a", DummyLLM)
        registry.register_class("llm", "b", DummyLLM)
        names = registry.list("llm")
        assert set(names) == {"a", "b"}

    def test_list_all(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "a", DummyLLM)
        registry.register_class("stt", "b", DummyLLM)
        all_mods = registry.list_all()
        assert "llm" in all_mods
        assert "stt" in all_mods

    def test_set_default(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "a", DummyLLM)
        registry.register_class("llm", "b", DummyLLM, default=True)
        assert registry.get_default_name("llm") == "b"
        registry.set_default("llm", "a")
        assert registry.get_default_name("llm") == "a"

    def test_is_registered(self) -> None:
        registry = ProviderRegistry.for_testing()
        assert not registry.is_registered("llm", "test")
        registry.register_class("llm", "test", DummyLLM)
        assert registry.is_registered("llm", "test")

    def test_clear_registry(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "test", DummyLLM)
        ProviderRegistry.reset_singleton()
        # New singleton should be empty
        new_registry = ProviderRegistry.get_instance()
        assert new_registry.list("llm") == []

    def test_health_check_all(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "test", DummyLLM)
        health = registry.health_check_all()
        assert health["llm"]["test"] is True

    def test_initialize_all(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "test", DummyLLM)
        # Should not raise
        registry.initialize_all()

    def test_shutdown_all(self) -> None:
        registry = ProviderRegistry.for_testing()
        registry.register_class("llm", "test", DummyLLM)
        registry.get("llm", "test")  # Instantiate
        # Should not raise
        registry.shutdown_all()


class TestProviderRegistryConfigFactory:
    """Test create_from_config factory."""

    def test_create_from_pipeline_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from voicevision.core.config import PipelineConfig

        # Mock the backend classes to not require actual model files
        monkeypatch.setattr(
            "voicevision.backends.whisper_cpp.WhisperCppBackend.__init__",
            lambda _self, _model, **_kwargs: None,
        )
        monkeypatch.setattr(
            "voicevision.backends.llama_cpp.LlamaCppBackend.__init__",
            lambda _self, _model, **_kwargs: None,
        )
        monkeypatch.setattr(
            "voicevision.backends.piper.PiperBackend.__init__",
            lambda _self, _model, **_kwargs: None,
        )

        config = PipelineConfig(
            stt_model="/models/whisper-base.bin",
            llm_model="/models/qwen3-1.7b.gguf",
            tts_model="/models/voice.onnx",
        )
        registry = ProviderRegistry.get_instance().create_from_config(config)

        # Should have registered providers
        assert registry.is_registered("stt", "whisper-cpp")
        assert registry.is_registered("llm", "llama-cpp")
        assert registry.is_registered("tts", "piper")
        assert registry.is_registered("vad", "webrtcvad")


class TestBackwardsCompatibility:
    """Test BackendRegistry wrapper for backwards compatibility."""

    def test_is_registered(self) -> None:
        ProviderRegistry.get_instance().register_class("llm", "test", DummyLLM)
        assert BackendRegistry.is_registered("llm", "test")

    def test_get(self) -> None:
        ProviderRegistry.get_instance().register_class("llm", "test", DummyLLM)
        provider = BackendRegistry.get("llm", "test")
        assert isinstance(provider, DummyLLM)

    def test_list(self) -> None:
        ProviderRegistry.get_instance().register_class("llm", "a", DummyLLM)
        ProviderRegistry.get_instance().register_class("llm", "b", DummyLLM)
        names = BackendRegistry.list("llm")
        assert set(names) == {"a", "b"}

    def test_create(self) -> None:
        ProviderRegistry.get_instance().register_class("llm", "test", DummyLLM)
        provider = BackendRegistry.create("llm", "test")
        assert isinstance(provider, DummyLLM)
