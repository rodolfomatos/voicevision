"""Tests for voicevision.backends.vision.

No real model or server are needed: everything is mocked with fakes.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

from voicevision.backends.vision import MoondreamBackend
from voicevision.errors import BackendExecutionError


class TestMoondreamBackend:
    def test_available_false_without_httpx(self, monkeypatch: Any) -> None:
        monkeypatch.setitem(sys.modules, "httpx", None)
        assert MoondreamBackend.available() is False

    def test_available_true_with_httpx(self, monkeypatch: Any) -> None:
        # Inject a fake httpx so the assertion does not depend on the optional
        # dependency being installed in the current environment.
        monkeypatch.setitem(sys.modules, "httpx", MagicMock())

        assert MoondreamBackend.available() is True

    def test_requires_model_path(self) -> None:
        with pytest.raises(ValueError, match="model path is required"):
            MoondreamBackend(model="")

    def test_describe_returns_text(
        self,
        monkeypatch: Any,
    ) -> None:
        backend = MoondreamBackend(model="/models/moondream2-v2-f16.gguf")

        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict[str, Any]:
                return {"content": "A photo of a cat sitting on a mat."}

        fake_client = MagicMock()
        fake_client.post.return_value = FakeResponse()

        fake_httpx = MagicMock()
        fake_httpx.Client.return_value.__enter__.return_value = fake_client

        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

        result = backend.describe(b"\xff\xd8\xff\xe0fake_jpeg", prompt="What is this?")
        assert "cat" in result.lower()

    def test_describe_empty_image_raises(self) -> None:
        backend = MoondreamBackend(model="/models/moondream2-v2-f16.gguf")
        with pytest.raises(BackendExecutionError, match="no image data provided"):
            backend.describe(b"", prompt="What is this?")

    def test_describe_connection_error(
        self,
        monkeypatch: Any,
    ) -> None:
        backend = MoondreamBackend(model="/models/moondream2-v2-f16.gguf")

        fake_client = MagicMock()
        fake_client.post.side_effect = ConnectionError("Connection refused")

        fake_httpx = MagicMock()
        fake_httpx.Client.return_value.__enter__.return_value = fake_client

        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

        with pytest.raises(BackendExecutionError, match="could not connect"):
            backend.describe(b"\xff\xd8\xff\xe0fake_jpeg", prompt="What is this?")

    def test_install_hint(self) -> None:
        assert "moondream" in MoondreamBackend.install_hint.lower()
        assert "gguf" in MoondreamBackend.install_hint.lower()


# -- pipeline integration ------------------------------------------------------


class TestPipelineDescribeAndAnswer:
    def test_describe_and_answer_returns_wav_bytes(
        self,
        monkeypatch: Any,
    ) -> None:
        from voicevision.pipeline import PipelineConfig, VoicePipeline

        config = PipelineConfig(
            llm_model="/models/qwen3-1.7B.Q4_K_M.gguf",
            tts_model="/models/voice.onnx",
            vision_model="/models/moondream2-v2-f16.gguf",
        )

        pipeline = VoicePipeline(config)

        # Mock the vision backend
        fake_vision = MagicMock()
        fake_vision.describe.return_value = "A photo of a red apple on a table."
        pipeline._vision = fake_vision

        # Mock the LLM backend
        fake_llm = MagicMock()
        fake_completion = MagicMock()
        fake_completion.content = "That is a red apple."
        fake_llm.complete.return_value = fake_completion
        pipeline._llm = fake_llm

        # Mock the TTS backend
        fake_tts = MagicMock()
        fake_tts.synthesize.return_value = b"\xff\xd8\xff\xe0fake_wav"
        pipeline._tts = fake_tts

        result = pipeline.describe_and_answer(
            b"\xff\xd8\xff\xe0fake_image",
            "What fruit is this?",
        )
        assert result == b"\xff\xd8\xff\xe0fake_wav"
        fake_vision.describe.assert_called_once()
        fake_llm.complete.assert_called_once()
        fake_tts.synthesize.assert_called_once_with("That is a red apple.")

    def test_describe_and_answer_empty_image_returns_empty(
        self,
    ) -> None:
        from voicevision.pipeline import PipelineConfig, VoicePipeline

        config = PipelineConfig(
            llm_model="/models/qwen3-1.7B.Q4_K_M.gguf",
            tts_model="/models/voice.onnx",
            vision_model="/models/moondream2-v2-f16.gguf",
        )
        pipeline = VoicePipeline(config)
        result = pipeline.describe_and_answer(b"", "What is this?")
        assert result == b""

    def test_describe_and_answer_missing_vision_model_raises(
        self,
    ) -> None:
        from voicevision.pipeline import PipelineConfig, VoicePipeline

        config = PipelineConfig(
            llm_model="/models/qwen3-1.7B.Q4_K_M.gguf",
            tts_model="/models/voice.onnx",
            vision_model="",
        )
        pipeline = VoicePipeline(config)
        with pytest.raises(ValueError, match="vision_model must be configured"):
            pipeline.describe_and_answer(b"\xff\xd8\xff\xe0fake", "What is this?")

    def test_describe_and_answer_empty_description_returns_empty(
        self,
    ) -> None:
        from voicevision.pipeline import PipelineConfig, VoicePipeline

        config = PipelineConfig(
            llm_model="/models/qwen3-1.7B.Q4_K_M.gguf",
            tts_model="/models/voice.onnx",
            vision_model="/models/moondream2-v2-f16.gguf",
        )
        pipeline = VoicePipeline(config)

        fake_vision = MagicMock()
        fake_vision.describe.return_value = ""
        pipeline._vision = fake_vision

        result = pipeline.describe_and_answer(
            b"\xff\xd8\xff\xe0fake_image",
            "What is this?",
        )
        assert result == b""
