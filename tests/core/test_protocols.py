"""Tests for voicevision.core.protocols (M1 Provider Protocols)."""

from __future__ import annotations

from voicevision.core.protocols import (
    Completion,
    EmotionProvider,
    EmotionResult,
    LLMChunk,
    LLMProvider,
    ProviderCapabilities,
    ProviderLifecycle,
    SpeakerIDProvider,
    STTChunk,
    STTProvider,
    TTSChunk,
    TTSProvider,
    VADProvider,
    VisionProvider,
    WakeWordProvider,
)


def _base_provider_methods(name: str, modality: str):
    """Mixin for Provider base protocol methods."""
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

    return type("_ProviderMixin", (), {
        "name": name,
        "modality": modality,
        "capabilities": capabilities,
        "lifecycle": lifecycle,
        "initialize": initialize,
        "shutdown": shutdown,
        "health_check": health_check,
        "available": available,
        "install_hint": install_hint,
    })


class DummyLLM(_base_provider_methods("dummy", "llm")):
    def generate(self, prompt: str, **kwargs: object) -> str:
        return "dummy"

    def generate_stream(self, prompt: str, **kwargs: object):
        yield "dummy"

    def complete(self, prompt: str, **kwargs: object) -> Completion:
        return Completion(content="dummy")


class DummySTT(_base_provider_methods("dummy", "stt")):
    def transcribe(self, audio_data: bytes, **kwargs: object) -> str:
        return "dummy"

    def transcribe_stream(self, audio_chunk: bytes, **kwargs: object):
        yield STTChunk(text="dummy", is_final=True)

    def detect_language(self, audio: bytes, **kwargs: object) -> str:
        return "en"


class DummyTTS(_base_provider_methods("dummy", "tts")):
    def synthesize(self, text: str, **kwargs: object) -> bytes:
        return b"dummy"

    def synthesize_stream(self, text_chunks, **kwargs: object):
        yield TTSChunk(audio=b"dummy", is_final=True)


class DummyVision(_base_provider_methods("dummy", "vision")):
    def describe(self, image: bytes, **kwargs: object) -> str:
        return "dummy"

    def analyze(self, image: bytes, **kwargs: object) -> dict[str, object]:
        return {"task": "describe", "description": "dummy"}


class DummyVAD(_base_provider_methods("dummy", "vad")):
    def process_frame(self, frame: bytes, **kwargs: object) -> bool:
        return True

    def segment(self, audio: bytes, **kwargs: object):
        yield (0, 100)

    @property
    def frame_bytes(self) -> int:
        return 960

    @property
    def frame_ms(self) -> int:
        return 30

    @property
    def sample_rate(self) -> int:
        return 16000

    @property
    def max_utterance_ms(self) -> int:
        return 30000


class DummyWakeWord(_base_provider_methods("dummy", "wakeword")):
    def process_frame(self, frame: bytes, **kwargs: object) -> str | None:
        return None

    def check(self, audio: bytes, **kwargs: object) -> str | None:
        return None

    @property
    def wake_words(self) -> frozenset[str]:
        return frozenset()


class DummySpeakerID(_base_provider_methods("dummy", "speakerid")):
    def identify(self, audio: bytes, **kwargs: object) -> str:
        return "Speaker 1"

    def enroll(self, audio: bytes, label: str, **kwargs: object) -> None:
        pass

    def reset(self) -> None:
        pass

    def remove(self, label: str) -> bool:
        return False

    def identify_stream(self, audio_chunks: object, **kwargs: object) -> object:
        return iter(())

    def diarize(self, audio: bytes, **kwargs: object) -> list:
        return []


class DummyEmotion(_base_provider_methods("dummy", "emotion")):
    def detect(self, text: str, **kwargs: object) -> EmotionResult:
        return EmotionResult(label="neutral", score=0.5)


class TestProtocols:
    """Verify Protocol structural subtyping works."""

    def test_llm_provider_protocol(self) -> None:
        dummy = DummyLLM()
        assert isinstance(dummy, LLMProvider)
        assert dummy.generate("test") == "dummy"
        comp = dummy.complete("test")
        assert isinstance(comp, Completion)
        assert comp.content == "dummy"

    def test_stt_provider_protocol(self) -> None:
        dummy = DummySTT()
        assert isinstance(dummy, STTProvider)
        assert dummy.transcribe(b"audio") == "dummy"
        assert dummy.detect_language(b"audio") == "en"

    def test_tts_provider_protocol(self) -> None:
        dummy = DummyTTS()
        assert isinstance(dummy, TTSProvider)
        assert dummy.synthesize("text") == b"dummy"

    def test_vision_provider_protocol(self) -> None:
        dummy = DummyVision()
        assert isinstance(dummy, VisionProvider)
        assert dummy.describe(b"image") == "dummy"
        assert dummy.analyze(b"image")["task"] == "describe"

    def test_vad_provider_protocol(self) -> None:
        dummy = DummyVAD()
        assert isinstance(dummy, VADProvider)
        assert dummy.process_frame(b"frame") is True
        assert dummy.frame_bytes == 960
        assert dummy.sample_rate == 16000

    def test_wakeword_provider_protocol(self) -> None:
        dummy = DummyWakeWord()
        assert isinstance(dummy, WakeWordProvider)
        assert dummy.process_frame(b"frame") is None
        assert dummy.wake_words == frozenset()

    def test_speakerid_provider_protocol(self) -> None:
        dummy = DummySpeakerID()
        assert isinstance(dummy, SpeakerIDProvider)
        assert dummy.identify(b"audio") == "Speaker 1"

    def test_emotion_provider_protocol(self) -> None:
        dummy = DummyEmotion()
        assert isinstance(dummy, EmotionProvider)
        result = dummy.detect("test")
        assert isinstance(result, EmotionResult)
        assert result.label == "neutral"

    def test_protocol_method_signatures(self) -> None:
        """Verify protocols define expected methods."""
        assert hasattr(LLMProvider, "generate")
        assert hasattr(LLMProvider, "generate_stream")
        assert hasattr(LLMProvider, "complete")
        assert hasattr(STTProvider, "transcribe")
        assert hasattr(STTProvider, "transcribe_stream")
        assert hasattr(STTProvider, "detect_language")
        assert hasattr(TTSProvider, "synthesize")
        assert hasattr(TTSProvider, "synthesize_stream")
        assert hasattr(VisionProvider, "describe")
        assert hasattr(VisionProvider, "analyze")
        assert hasattr(VADProvider, "process_frame")
        assert hasattr(VADProvider, "segment")
        assert hasattr(WakeWordProvider, "process_frame")
        assert hasattr(WakeWordProvider, "check")
        assert hasattr(SpeakerIDProvider, "identify")
        assert hasattr(SpeakerIDProvider, "enroll")
        assert hasattr(SpeakerIDProvider, "reset")
        assert hasattr(EmotionProvider, "detect")


class TestProtocolSlots:
    """Verify protocols use __slots__ = () for memory efficiency."""

    def test_llm_slots(self) -> None:
        assert LLMProvider.__slots__ == ()

    def test_stt_slots(self) -> None:
        assert STTProvider.__slots__ == ()

    def test_tts_slots(self) -> None:
        assert TTSProvider.__slots__ == ()

    def test_vision_slots(self) -> None:
        assert VisionProvider.__slots__ == ()

    def test_vad_slots(self) -> None:
        assert VADProvider.__slots__ == ()

    def test_wakeword_slots(self) -> None:
        assert WakeWordProvider.__slots__ == ()

    def test_speakerid_slots(self) -> None:
        assert SpeakerIDProvider.__slots__ == ()

    def test_emotion_slots(self) -> None:
        assert EmotionProvider.__slots__ == ()


class TestChunkTypes:
    """Test chunk dataclasses."""

    def test_stt_chunk(self) -> None:
        chunk = STTChunk(text="hello", is_final=True, language="en")
        assert chunk.text == "hello"
        assert chunk.is_final is True
        assert chunk.language == "en"

    def test_llm_chunk(self) -> None:
        chunk = LLMChunk(content="hello", thinking="thinking...")
        assert chunk.content == "hello"
        assert chunk.thinking == "thinking..."
        assert chunk.is_final is False

    def test_tts_chunk(self) -> None:
        chunk = TTSChunk(audio=b"audio", is_final=True, sample_rate=16000)
        assert chunk.audio == b"audio"
        assert chunk.is_final is True
        assert chunk.sample_rate == 16000

    def test_completion(self) -> None:
        comp = Completion(content="answer", thinking="thinking", raw={})
        assert comp.content == "answer"
        assert comp.thinking == "thinking"
        assert comp.raw == {}

    def test_emotion_result(self) -> None:
        result = EmotionResult(label="positive", score=0.8)
        assert result.label == "positive"
        assert result.score == 0.8


class TestProviderCapabilities:
    """Test ProviderCapabilities dataclass."""

    def test_defaults(self) -> None:
        caps = ProviderCapabilities()
        assert caps.streaming is False
        assert caps.languages == frozenset()
        assert caps.models == frozenset()
        assert caps.max_concurrent == 1
        assert caps.supports_cancellation is False

    def test_custom(self) -> None:
        caps = ProviderCapabilities(
            streaming=True,
            languages=frozenset({"en", "pt"}),
            models=frozenset({"model1"}),
            max_concurrent=4,
            supports_cancellation=True,
        )
        assert caps.streaming is True
        assert caps.languages == frozenset({"en", "pt"})
        assert caps.models == frozenset({"model1"})
        assert caps.max_concurrent == 4
        assert caps.supports_cancellation is True
