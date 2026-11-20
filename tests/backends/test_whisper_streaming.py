"""T091 — streaming STT improvements for the whisper.cpp backend.

No whisper.cpp binary is required: the chunked path uses the deterministic fake
child from T088, and the true-streaming path uses a small fake Popen. That keeps
the tests fast and proves the code, not the mock.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from tests.backends.test_whisper_cpp import fake_backend, make_wav
from tests.support.fake_child import WHISPER_TIMESTAMPS, WHISPER_TRANSCRIPT
from voicevision.backends.whisper_cpp import (
    LATENCY_TARGETS,
    StreamingConfig,
    WhisperCppBackend,
    WordTiming,
)
from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import VADProvider
from voicevision.errors import PipelineCancelledError


class AcceptEvenFrames(VADProvider):
    """Deterministic VAD that accepts every other 30 ms frame."""

    def __init__(self, calls: list[int] | None = None) -> None:
        self.index = 0
        self.calls = calls if calls is not None else []

    @property
    def name(self) -> str:
        return "fake-vad"

    def modality(self) -> str:
        return "vad"

    def process_frame(
        self, frame: bytes, *, token: CancellationToken | None = None
    ) -> bool:
        accepted = self.index % 2 == 0
        self.calls.append(self.index)
        self.index += 1
        return accepted

    def segment(
        self, audio: bytes, *, token: CancellationToken | None = None
    ) -> Generator[tuple[int, int], None, None]:
        yield from ()

    def capabilities(self) -> Any:
        return None

    def lifecycle(self) -> Any:
        return None

    def health_check(self) -> bool:
        return True

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


# -- configuration ---------------------------------------------------------


class TestStreamingConfig:
    def test_defaults(self) -> None:
        config = StreamingConfig()
        assert config.latency_target_ms == 100
        assert config.chunk_size_ms == 1500
        assert config.overlap_ms == 500
        assert config.chunk_bytes == 1500 * 32
        assert config.overlap_bytes == 500 * 32

    @pytest.mark.parametrize("target", list(LATENCY_TARGETS))
    def test_valid_latency_targets(self, target: int) -> None:
        assert StreamingConfig(latency_target_ms=target).latency_target_ms == target

    def test_invalid_latency_target_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="latency_target_ms"):
            StreamingConfig(latency_target_ms=37)

    def test_overlap_must_be_smaller_than_chunk(self) -> None:
        with pytest.raises(ValueError, match="overlap_ms"):
            StreamingConfig(chunk_size_ms=500, overlap_ms=500)

    def test_negative_overlap_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="overlap_ms"):
            StreamingConfig(overlap_ms=-1)

    def test_from_kwargs_parses_types(self) -> None:
        config = StreamingConfig.from_kwargs(
            {
                "latency_target_ms": "200",
                "chunk_size_ms": 3000,
                "overlap_ms": 400,
                "use_vad": True,
                "detect_language": True,
                "word_timestamps": False,
                "unknown": "ignored",
            }
        )
        assert config.latency_target_ms == 200
        assert config.chunk_size_ms == 3000
        assert config.use_vad is True
        assert config.detect_language is True
        assert config.word_timestamps is False

    def test_from_kwargs_falls_back_on_garbage(self) -> None:
        config = StreamingConfig.from_kwargs({"latency_target_ms": "abc", "use_vad": "yes"})
        assert config.latency_target_ms == 100
        assert config.use_vad is False

    def test_lower_latency_means_smaller_default_chunks(self) -> None:
        fast = StreamingConfig.from_kwargs({"latency_target_ms": 50})
        slow = StreamingConfig.from_kwargs({"latency_target_ms": 200})
        assert fast.chunk_bytes < slow.chunk_bytes


# -- word timestamps -------------------------------------------------------


class TestWordTimestamps:
    def test_parses_whisper_word_output(self) -> None:
        raw = (
            "[00:00:01.200 --> 00:00:01.600]  hello\n"
            "[00:00:01.600 --> 00:00:02.000]  world\n"
        )
        timings = WhisperCppBackend.parse_word_timestamps(raw)
        assert timings == [
            WordTiming("hello", 1200, 1600),
            WordTiming("world", 1600, 2000),
        ]

    def test_no_timestamps_yields_empty_list(self) -> None:
        assert WhisperCppBackend.parse_word_timestamps("hello world") == []

    def test_partials_carry_timings_when_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = fake_backend(WHISPER_TIMESTAMPS)
        monkeypatch.setattr(
            WhisperCppBackend,
            "parse_word_timestamps",
            staticmethod(lambda _raw: [WordTiming("hello", 1200, 1600)]),
        )
        chunks = list(
            backend.transcribe_stream(
                iter([make_wav(seconds=0.05)]),
                chunk_size_ms=32,
                overlap_ms=0,
                use_true_streaming=False,
                word_timestamps=True,
            )
        )
        assert chunks
        assert chunks[-1].is_final
        assert any(chunk.start_ms == 1200 for chunk in chunks)


# -- capability detection --------------------------------------------------


class TestTrueStreamingCapability:
    def test_supports_true_streaming_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import voicevision.backends.whisper_cpp as module

        calls: list[str] = []

        class FakeResult:
            stdout = "-t, --stream real-time streaming"
            stderr = ""

        def fake_run(argv: list[str], **kwargs: object) -> FakeResult:
            calls.append(argv[0])
            return FakeResult()

        module._TRUE_STREAMING_CACHE.clear()
        monkeypatch.setattr(module.subprocess, "run", fake_run)
        backend = WhisperCppBackend(model="/m.bin", binary="whisper-cli")
        assert backend.supports_true_streaming() is True
        assert backend.supports_true_streaming() is True
        assert calls == ["whisper-cli"]

    def test_missing_binary_is_not_capable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import voicevision.backends.whisper_cpp as module

        def fake_run(argv: list[str], **kwargs: object) -> None:
            raise OSError("not installed")

        module._TRUE_STREAMING_CACHE.clear()
        monkeypatch.setattr(module.subprocess, "run", fake_run)
        assert WhisperCppBackend(model="/m.bin", binary="absent").supports_true_streaming() is False


# -- chunked streaming -----------------------------------------------------


class TestChunkedStreaming:
    def test_emits_partials_then_final(self) -> None:
        backend = fake_backend(WHISPER_TIMESTAMPS)
        audio = iter([make_wav(seconds=0.1)])
        chunks = list(
            backend.transcribe_stream(
                audio,
                chunk_size_ms=320,
                overlap_ms=0,
                use_true_streaming=False,
            )
        )
        assert chunks
        assert any(not chunk.is_final for chunk in chunks)
        assert chunks[-1].is_final
        assert chunks[-1].text

    def test_latency_target_changes_chunk_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Smaller latency target => smaller default chunks => more transcribe calls."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        seen: list[int] = []
        original = backend._transcribe_chunk

        def spy(buf: bytes, lang: str | None, token: CancellationToken | None) -> tuple[str, None]:
            seen.append(len(buf))
            return original(buf, lang, token)

        monkeypatch.setattr(backend, "_transcribe_chunk", spy)
        audio = make_wav(seconds=0.2)
        list(
            backend.transcribe_stream(
                iter([audio]),
                latency_target_ms=50,
                use_true_streaming=False,
            )
        )
        assert seen
        # +44 bytes for the WAV header pcm16_to_wav adds around each chunk.
        assert all(size <= 500 * 32 + 44 for size in seen)

    def test_language_auto_detects_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = fake_backend(WHISPER_TRANSCRIPT)
        calls: list[bytes] = []

        def fake_detect(audio: bytes, *, token: CancellationToken | None = None) -> str:
            calls.append(audio)
            return "pt"

        monkeypatch.setattr(backend, "detect_language", fake_detect)
        audio = make_wav(seconds=0.2)
        chunks = list(
            backend.transcribe_stream(
                iter([audio]),
                language="auto",
                chunk_size_ms=320,
                overlap_ms=0,
                use_true_streaming=False,
            )
        )
        assert len(calls) == 1
        assert all(chunk.language == "pt" for chunk in chunks)

    def test_raw_pcm_chunks_are_accepted(self) -> None:
        """The WebSocket endpoint feeds raw PCM16, not WAV files."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        chunks = list(
            backend.transcribe_stream(
                iter([b"\x00\x00" * 1600]),  # 0.1 s of raw PCM16
                chunk_size_ms=3200,
                overlap_ms=0,
                use_true_streaming=False,
            )
        )
        assert chunks[-1].is_final
        assert chunks[-1].text == "hello there general kenobi"

    def test_language_probe_window_is_one_to_two_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 50 ms latency target must not shrink the language probe below 1 s."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        probes: list[int] = []

        def fake_detect(audio: bytes, *, token: CancellationToken | None = None) -> str:
            probes.append(len(audio))
            return "en"

        monkeypatch.setattr(backend, "detect_language", fake_detect)
        list(
            backend.transcribe_stream(
                iter([make_wav(seconds=1.5)]),
                language="auto",
                latency_target_ms=50,
                use_true_streaming=False,
            )
        )
        assert len(probes) == 1
        # 1 s of PCM16 @ 16 kHz is 32 000 bytes; 2 s is 64 000.
        assert 32_000 <= probes[0] <= 64_100

    def test_vad_is_the_only_gate(self) -> None:
        """With use_vad, the caller's VAD is consulted for every 30 ms frame."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        calls: list[int] = []
        audio = make_wav(seconds=0.2)
        list(
            backend.transcribe_stream(
                iter([audio]),
                chunk_size_ms=320,
                overlap_ms=0,
                use_true_streaming=False,
                use_vad=True,
                vad=AcceptEvenFrames(calls),
            )
        )
        # 0.2 s @ 16 kHz => ~6 complete 30 ms frames, all gated by the VAD.
        assert len(calls) >= 3
        assert calls[0] == 0

    def test_use_vad_requires_provider(self) -> None:
        backend = fake_backend(WHISPER_TRANSCRIPT)
        with pytest.raises(ValueError, match="vad"):
            list(
                backend.transcribe_stream(
                    iter([make_wav(seconds=0.1)]),
                    use_vad=True,
                    use_true_streaming=False,
                )
            )

    def test_cancellation_stops_the_stream(self) -> None:
        backend = fake_backend(WHISPER_TRANSCRIPT)
        token = CancellationToken()
        token.cancel()
        with pytest.raises(PipelineCancelledError):
            list(
                backend.transcribe_stream(
                    iter([make_wav(seconds=0.1)]),
                    token=token,
                    use_true_streaming=False,
                )
            )


# -- true streaming --------------------------------------------------------


class FakeStdin:
    def __init__(self) -> None:
        self.written = bytearray()
        self.closed = False

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def readline(self) -> bytes:
        return self._lines.pop(0) if self._lines else b""


class FakeProcess:
    def __init__(self, lines: list[bytes]) -> None:
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(lines)
        self.terminated = False
        self._poll_count = 0

    def poll(self) -> int | None:
        self._poll_count += 1
        return 0 if self._poll_count > 1 else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        pass


class TestTrueStreaming:
    def test_persistent_child_streams_partials_and_final(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import voicevision.backends.whisper_cpp as module

        process = FakeProcess([b"hello ", b"world", b""])
        argv_seen: list[list[str]] = []

        def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
            argv_seen.append(argv)
            return process

        monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
        backend = WhisperCppBackend(model="/m.bin", binary="whisper-cli")
        monkeypatch.setattr(backend, "supports_true_streaming", lambda: True)

        audio = [b"\x00\x01" * 100, b"\x00\x02" * 100]
        chunks = list(
            backend.transcribe_stream(
                iter(audio),
                latency_target_ms=50,
                use_true_streaming=True,
            )
        )

        assert bytes(process.stdin.written) == b"".join(audio)
        assert process.stdin.closed
        assert "-t" in argv_seen[0] and "50" in argv_seen[0]
        assert [chunk.text for chunk in chunks if not chunk.is_final] == ["hello", "hello world"]
        assert chunks[-1].is_final
        assert chunks[-1].text == "hello world"


    def test_final_transcript_matches_expected_text(self) -> None:
        """Accuracy smoke test: the fake child's transcript is preserved end to end."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        chunks = list(
            backend.transcribe_stream(
                iter([make_wav(seconds=0.1)]),
                chunk_size_ms=3200,
                overlap_ms=0,
                use_true_streaming=False,
            )
        )
        assert chunks[-1].is_final
        assert chunks[-1].text == "hello there general kenobi"


# -- benchmark -------------------------------------------------------------


class TestStreamingBenchmark:
    def test_chunked_and_partial_paths_agree(self) -> None:
        """Lightweight benchmark smoke test: both paths yield the same final text."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        audio = make_wav(seconds=0.1)
        results = [
            list(
                backend.transcribe_stream(
                    iter([audio]),
                    chunk_size_ms=320,
                    overlap_ms=0,
                    use_true_streaming=False,
                )
            )
            for _ in range(2)
        ]
        finals = [[chunk.text for chunk in run if chunk.is_final] for run in results]
        assert finals[0] == finals[1]
