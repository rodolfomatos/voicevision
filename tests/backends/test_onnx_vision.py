"""Tests for OnnxVisionBackend using mocks.

No ONNX model file needed — tests mock onnxruntime, PIL, and numpy imports.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from voicevision.backends.onnx_vision import OnnxVisionBackend
from voicevision.errors import BackendExecutionError


def _fake_onnxruntime_module() -> ModuleType:
    """Create a fake onnxruntime module with a working InferenceSession."""
    import numpy as np

    mod = ModuleType("onnxruntime")

    class InferenceSession:
        def __init__(self, model_path: str, providers: list[str] | None = None) -> None:
            self.model_path = model_path
            self.providers = providers or ["CPUExecutionProvider"]
            self.call_count = 0
            self.inputs = [MagicMock(name="input.0")]
            self.inputs[0].name = "input.0"
            self.outputs = [MagicMock(name="output.0")]
            self.outputs[0].name = "output.0"
            self.last_input: dict[str, Any] = {}

        def run(
            self,
            output_names: list[str],
            input_feed: dict[str, Any],
        ) -> list[Any]:
            self.call_count += 1
            self.last_input = input_feed
            return [np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], dtype=np.float32)]

        def get_inputs(self) -> list[Any]:
            return self.inputs

        def get_outputs(self) -> list[Any]:
            return self.outputs

    mod.InferenceSession = InferenceSession
    return mod


@contextmanager
def _patch_onnxruntime() -> ModuleType:
    """Context manager to patch onnxruntime import."""

    fake = _fake_onnxruntime_module()
    original = sys.modules.get("onnxruntime")
    sys.modules["onnxruntime"] = fake
    try:
        yield fake
    finally:
        if original is None:
            sys.modules.pop("onnxruntime", None)
        else:
            sys.modules["onnxruntime"] = original


def _fake_pillow_module() -> ModuleType:
    """Create a fake PIL.Image module."""
    mod = ModuleType("PIL")

    class Image:
        @classmethod
        def open(cls, _fp: Any) -> MagicMock:
            img = MagicMock()
            img.convert.return_value = img
            img.resize.return_value = img
            # Make the image iterable so list(img) returns pixel values
            img.__iter__ = lambda _: iter([128] * (512 * 512 * 3))  # RGB pixels
            return img

    mod.Image = Image
    return mod


@contextmanager
def _patch_pillow() -> ModuleType:
    """Context manager to patch PIL.Image import."""

    fake = _fake_pillow_module()
    original = sys.modules.get("PIL")
    sys.modules["PIL"] = fake
    try:
        yield fake
    finally:
        if original is None:
            sys.modules.pop("PIL", None)
        else:
            sys.modules["PIL"] = original


def _fake_numpy_module() -> ModuleType:
    """Create a fake numpy module."""
    mod = ModuleType("numpy")

    class ndarray:
        def __init__(self, data: Any, dtype: Any = None) -> None:
            # Always store a simple list of floats to avoid issues with
            # MagicMock objects being iterable in unexpected ways.
            self._data = [0.5]
            self.dtype = dtype
            self.shape = (1,)

        def tolist(self) -> list[Any]:
            return self._data

        def __truediv__(self, other: Any) -> ndarray:
            return ndarray([x / other for x in self._data])

    mod.ndarray = ndarray
    mod.float32 = float
    mod.array = lambda data, dtype=None: ndarray(data, dtype)
    mod.transpose = lambda arr, _axes: ndarray(arr._data if isinstance(arr, ndarray) else arr)
    mod.expand_dims = lambda arr, **_kwargs: ndarray(arr._data if isinstance(arr, ndarray) else arr)
    mod.mean = lambda arr: sum(arr._data if isinstance(arr, ndarray) else list(arr)) / max(
        1, len(arr._data if isinstance(arr, ndarray) else list(arr))
    )
    mod.max = lambda arr: max(arr._data if isinstance(arr, ndarray) else list(arr))
    mod.min = lambda arr: min(arr._data if isinstance(arr, ndarray) else list(arr))
    return mod


@contextmanager
def _patch_numpy() -> ModuleType:
    """Context manager to patch numpy import."""

    fake = _fake_numpy_module()
    original = sys.modules.get("numpy")
    sys.modules["numpy"] = fake
    try:
        yield fake
    finally:
        if original is None:
            sys.modules.pop("numpy", None)
        else:
            sys.modules["numpy"] = original


# -- construction ----------------------------------------------------------


class TestConstruction:
    def test_requires_model_path(self) -> None:
        with pytest.raises(ValueError, match="model path is required"):
            OnnxVisionBackend(model="")

    def test_available_with_onnxruntime(self) -> None:
        # onnxruntime não está instalado no ambiente de teste
        assert OnnxVisionBackend.available() is False

    def test_accepts_custom_providers(self) -> None:
        backend = OnnxVisionBackend(model="/models/vision.onnx", providers=["CPUExecutionProvider"])
        assert backend._providers == ["CPUExecutionProvider"]

    def test_default_providers(self) -> None:
        backend = OnnxVisionBackend(model="/models/vision.onnx")
        assert backend._providers == ["CPUExecutionProvider"]

    def test_stores_model_path(self) -> None:
        backend = OnnxVisionBackend(model="/models/vision.onnx")
        assert backend._model == "/models/vision.onnx"


# -- describe --------------------------------------------------------------


class TestDescribe:
    def test_describe_requires_image_data(self) -> None:
        backend = OnnxVisionBackend(model="/models/vision.onnx")
        with pytest.raises(BackendExecutionError, match="no image data"):
            backend.describe(b"")

    def test_describe_returns_text(self) -> None:

        with _patch_onnxruntime(), _patch_pillow(), _patch_numpy():
            backend = OnnxVisionBackend(model="/models/vision.onnx")
            audio = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            result = backend.describe(audio, question="What is this?")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_describe_without_question(self) -> None:
        with _patch_onnxruntime(), _patch_pillow(), _patch_numpy():
            backend = OnnxVisionBackend(model="/models/vision.onnx")
            result = backend.describe(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        assert isinstance(result, str)
        assert len(result) > 0


class TestClose:
    def test_close_resets_session(self) -> None:
        with _patch_onnxruntime(), _patch_pillow(), _patch_numpy():
            backend = OnnxVisionBackend(model="/models/vision.onnx")
            backend._ensure_session()
            assert backend._session is not None
            backend.close()
            assert backend._session is None


# -- integration with PipelineConfig --------------------------------------


class TestIntegrationWithConfig:
    def test_config_has_vision_backend_field(self) -> None:
        from voicevision.pipeline import PipelineConfig

        config = PipelineConfig()
        assert config.vision_backend == "llama-cpp"

    def test_config_can_set_onnx_backend(self) -> None:
        from voicevision.pipeline import PipelineConfig

        config = PipelineConfig(vision_backend="onnx")
        assert config.vision_backend == "onnx"
