"""Tests for voicevision.core.protocols."""

from __future__ import annotations

from voicevision.core.protocols import (
    CameraBackend,
    LLMBackend,
    STTBackend,
    TTSBackend,
    VisionBackend,
)


class DummyLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return "dummy"

    def generate_stream(self, prompt: str, **kwargs):
        yield "dummy"


class DummySTT:
    def transcribe(self, audio_data: bytes, **kwargs) -> str:
        return "dummy"

    def transcribe_stream(self, audio_chunk: bytes, **kwargs):
        yield "dummy"


class DummyTTS:
    def synthesize(self, text: str, **kwargs) -> bytes:
        return b"dummy"

    def synthesize_stream(self, text: str, **kwargs):
        yield b"dummy"


class DummyVision:
    def describe(self, image_data: bytes, prompt: str | None = None, **kwargs) -> str:
        return "dummy"


class DummyCamera:
    def capture(self, **kwargs) -> bytes:
        return b"dummy"

    def capture_stream(self, **kwargs):
        yield b"dummy"

    def close(self) -> None:
        pass


class TestProtocols:
    """Verify Protocol structural subtyping works."""

    def test_llm_backend_protocol(self) -> None:
        dummy = DummyLLM()
        assert isinstance(dummy, LLMBackend)
        assert dummy.generate("test") == "dummy"

    def test_stt_backend_protocol(self) -> None:
        dummy = DummySTT()
        assert isinstance(dummy, STTBackend)
        assert dummy.transcribe(b"audio") == "dummy"

    def test_tts_backend_protocol(self) -> None:
        dummy = DummyTTS()
        assert isinstance(dummy, TTSBackend)
        assert dummy.synthesize("text") == b"dummy"

    def test_vision_backend_protocol(self) -> None:
        dummy = DummyVision()
        assert isinstance(dummy, VisionBackend)
        assert dummy.describe(b"image") == "dummy"

    def test_camera_backend_protocol(self) -> None:
        dummy = DummyCamera()
        assert isinstance(dummy, CameraBackend)
        assert dummy.capture() == b"dummy"
        dummy.close()

    def test_protocol_method_signatures(self) -> None:
        """Verify protocols define expected methods."""
        assert hasattr(LLMBackend, "generate")
        assert hasattr(LLMBackend, "generate_stream")
        assert hasattr(STTBackend, "transcribe")
        assert hasattr(STTBackend, "transcribe_stream")
        assert hasattr(TTSBackend, "synthesize")
        assert hasattr(TTSBackend, "synthesize_stream")
        assert hasattr(VisionBackend, "describe")
        assert hasattr(CameraBackend, "capture")
        assert hasattr(CameraBackend, "capture_stream")
        assert hasattr(CameraBackend, "close")


class TestProtocolSlots:
    """Verify protocols use __slots__ = () for memory efficiency."""

    def test_llm_slots(self) -> None:
        assert LLMBackend.__slots__ == ()

    def test_stt_slots(self) -> None:
        assert STTBackend.__slots__ == ()

    def test_tts_slots(self) -> None:
        assert TTSBackend.__slots__ == ()

    def test_vision_slots(self) -> None:
        assert VisionBackend.__slots__ == ()

    def test_camera_slots(self) -> None:
        assert CameraBackend.__slots__ == ()
