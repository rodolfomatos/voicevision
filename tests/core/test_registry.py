"""Tests for voicevision.core.registry."""

from __future__ import annotations

import pytest

from voicevision.core.protocols import LLMBackend
from voicevision.core.registry import BackendRegistry


class DummyBackend:
    def generate(self, prompt: str, **kwargs) -> str:
        return "test"


class TestRegistry:
    """Test BackendRegistry CRUD operations."""

    def test_register_and_get(self) -> None:
        BackendRegistry.register("llm", "test", DummyBackend)
        cls = BackendRegistry.get("llm", "test")
        assert cls is DummyBackend

    def test_register_duplicate_raises(self) -> None:
        BackendRegistry.register("llm", "test", DummyBackend)
        with pytest.raises(ValueError, match="already registered"):
            BackendRegistry.register("llm", "test", DummyBackend)

    def test_invalid_modality_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid modality"):
            BackendRegistry.register("invalid", "test", DummyBackend)

    def test_list_backends(self) -> None:
        BackendRegistry.register("llm", "a", DummyBackend)
        BackendRegistry.register("llm", "b", DummyBackend)
        names = BackendRegistry.list("llm")
        assert names == ["a", "b"]

    def test_list_invalid_modality_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid modality"):
            BackendRegistry.list("invalid")

    def test_create_instance(self) -> None:
        BackendRegistry.register("llm", "test", DummyBackend)
        instance = BackendRegistry.create("llm", "test")
        assert isinstance(instance, DummyBackend)
        assert instance.generate("prompt") == "test"

    def test_create_with_kwargs(self) -> None:
        class KwargBackend:
            def __init__(self, custom_param: str = "default"):
                self.custom_param = custom_param

            def generate(self, prompt: str, **kwargs) -> str:
                return self.custom_param

        BackendRegistry.register("llm", "kwarg", KwargBackend)
        instance = BackendRegistry.create("llm", "kwarg", custom_param="custom")
        assert instance.custom_param == "custom"

    def test_create_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="not found"):
            BackendRegistry.create("llm", "unknown")

    def test_is_registered(self) -> None:
        assert not BackendRegistry.is_registered("llm", "test")
        BackendRegistry.register("llm", "test", DummyBackend)
        assert BackendRegistry.is_registered("llm", "test")

    def test_clear_registry(self) -> None:
        BackendRegistry.register("llm", "test", DummyBackend)
        BackendRegistry.clear()
        assert not BackendRegistry.is_registered("llm", "test")
        assert BackendRegistry.list("llm") == []

    def test_get_protocol(self) -> None:
        protocol = BackendRegistry.get_protocol("llm")
        assert protocol is LLMBackend

    def test_get_protocol_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid modality"):
            BackendRegistry.get_protocol("invalid")


class TestRegistryFactory:
    """Test custom factory functions."""

    def test_custom_factory(self) -> None:
        def factory(custom_value: int = 42) -> DummyBackend:
            return DummyBackend()

        BackendRegistry.register("llm", "factory", DummyBackend, factory=factory)
        instance = BackendRegistry.create("llm", "factory", custom_value=100)
        assert isinstance(instance, DummyBackend)

    def test_factory_override(self) -> None:
        """Factory takes precedence over direct instantiation."""
        created = []

        def tracking_factory(**kwargs):
            created.append(kwargs)
            return DummyBackend()

        BackendRegistry.register("llm", "tracked", DummyBackend, factory=tracking_factory)
        BackendRegistry.create("llm", "tracked", foo="bar")
        assert created == [{"foo": "bar"}]
