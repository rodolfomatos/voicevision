"""T092 — pyannote-backed speaker identification, persistence and diarization.

pyannote.audio and torch are deliberately absent from the test environment:
embedders and diarizers are injected, so these tests exercise the real matching,
storage and streaming code without a 500 MB model download.
"""

from __future__ import annotations

import builtins
import json
from collections.abc import Generator
from typing import Any

import pytest

from voicevision.backends.speaker_pyannote import (
    UNKNOWN_SPEAKER,
    PyannoteSpeakerBackend,
    SpeakerStore,
    cosine_similarity,
    normalise,
)
from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import (
    ProviderCapabilities,
    SpeakerIDProvider,
    SpeakerSegment,
    SpeakerStoreProtocol,
)
from voicevision.errors import BackendNotAvailableError, PipelineCancelledError

# -- helpers ----------------------------------------------------------------


def _tone_embedder(audio: bytes, sample_rate: int) -> list[float]:
    """Deterministic embedding: one orthogonal vector per leading byte mod 3."""
    index = audio[0] % 3 if audio else 0
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]][index]


def _pcm(tone: int, *, seconds: float = 1.0) -> bytes:
    return bytes([tone]) * int(seconds * 32000)


def _backend(**kwargs: object) -> PyannoteSpeakerBackend:
    return PyannoteSpeakerBackend(embedder=_tone_embedder, **kwargs)


# -- vector maths -----------------------------------------------------------


class TestVectorMath:
    def test_identical_vectors_have_similarity_one(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_have_similarity_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_have_similarity_minus_one(self) -> None:
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    @pytest.mark.parametrize("a,b", [([], []), ([1.0], [1.0, 2.0]), ([0.0], [1.0])])
    def test_degenerate_inputs_return_zero(self, a: list[float], b: list[float]) -> None:
        assert cosine_similarity(a, b) == 0.0

    def test_normalise_produces_unit_vector(self) -> None:
        vector = normalise([3.0, 4.0])
        assert vector == pytest.approx((0.6, 0.8))
        assert sum(value * value for value in vector) == pytest.approx(1.0)

    @pytest.mark.parametrize("bad", [[], [0.0, 0.0]])
    def test_normalise_rejects_invalid_vectors(self, bad: list[float]) -> None:
        with pytest.raises(ValueError, match="embedding"):
            normalise(bad)


# -- store ------------------------------------------------------------------


class TestSpeakerStore:
    def test_in_memory_store(self) -> None:
        store = SpeakerStore()
        store.add("Alice", [1.0, 0.0])
        store.add("Bob", [0.0, 1.0])
        assert store.labels() == ("Alice", "Bob")
        assert store.mean("Alice") == pytest.approx((1.0, 0.0))
        assert store.remove("Alice") is True
        assert store.remove("Alice") is False
        assert store.labels() == ("Bob",)

    def test_re_enrollment_averages_embeddings(self) -> None:
        store = SpeakerStore()
        store.add("Alice", [1.0, 0.0])
        store.add("Alice", [0.0, 1.0])
        assert len(store.vectors("Alice")) == 2
        assert store.mean("Alice") == pytest.approx((2**-0.5, 2**-0.5))

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(ValueError, match="label"):
            SpeakerStore().add("  ", [1.0])

    def test_unknown_mean_is_none(self) -> None:
        assert SpeakerStore().mean("nobody") is None

    def test_clear(self) -> None:
        store = SpeakerStore()
        store.add("Alice", [1.0])
        store.clear()
        assert store.labels() == ()

    @pytest.mark.parametrize("suffix", ["json", "db"])
    def test_persistence_roundtrip(self, tmp_path: Any, suffix: str) -> None:
        path = tmp_path / f"speakers.{suffix}"
        first = SpeakerStore(path)
        first.add("Alice", [1.0, 0.0])
        first.add("Bob", [0.0, 1.0])

        second = SpeakerStore(path)
        assert second.labels() == ("Alice", "Bob")
        assert second.mean("Alice") == pytest.approx((1.0, 0.0))
        second.remove("Bob")
        assert SpeakerStore(path).labels() == ("Alice",)

    def test_corrupt_json_is_ignored(self, tmp_path: Any) -> None:
        path = tmp_path / "speakers.json"
        path.write_text("{not json", encoding="utf-8")
        assert SpeakerStore(path).labels() == ()

    def test_corrupt_sqlite_is_ignored(self, tmp_path: Any) -> None:
        path = tmp_path / "speakers.db"
        path.write_bytes(b"not a database")
        assert SpeakerStore(path).labels() == ()

    def test_store_conforms_to_protocol(self) -> None:
        assert isinstance(SpeakerStore(), SpeakerStoreProtocol)


# -- backend basics ---------------------------------------------------------


class TestBackendConfiguration:
    def test_injected_backend_needs_no_pyannote(self) -> None:
        backend = _backend()
        assert backend.health_check() is True
        assert backend.name == "pyannote"
        assert backend.modality == "speakerid"

    def test_capabilities_advertise_streaming(self) -> None:
        caps = _backend().capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.streaming is True
        assert caps.supports_cancellation is True

    def test_conforms_to_speaker_protocol(self) -> None:
        assert isinstance(_backend(), SpeakerIDProvider)

    def test_available_reflects_missing_dependency(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_import = builtins.__import__

        def no_pyannote(name: str, *args: object, **kwargs: object) -> Any:
            if name.startswith("pyannote"):
                raise ImportError("pyannote is not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_pyannote)
        assert PyannoteSpeakerBackend.available() is False
        backend = _backend()
        assert backend.health_check() is True  # injected embedder still works
        with pytest.raises(BackendNotAvailableError, match="pyannote"):
            PyannoteSpeakerBackend().initialize()

    def test_install_hint_names_the_extra(self) -> None:
        assert "speaker" in PyannoteSpeakerBackend.install_hint()

    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_invalid_threshold_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="threshold"):
            _backend(threshold=bad)

    def test_set_threshold_validates(self) -> None:
        backend = _backend()
        backend.set_threshold(0.9)
        assert backend.threshold == 0.9
        with pytest.raises(ValueError, match="threshold"):
            backend.set_threshold(2.0)

    def test_invalid_chunk_ms_rejected(self) -> None:
        with pytest.raises(ValueError, match="chunk_ms"):
            _backend(chunk_ms=0)


# -- enrollment and identification -----------------------------------------


class TestEnrollmentAndIdentification:
    def test_enroll_then_identify(self) -> None:
        backend = _backend()
        backend.enroll(_pcm(0), label="Alice")
        assert backend.identify(_pcm(0)) == "Alice"
        assert backend.list_speakers() == ("Alice",)

    def test_unknown_speaker_below_threshold(self) -> None:
        backend = _backend(threshold=0.9)
        backend.enroll(_pcm(0), label="Alice")
        assert backend.identify(_pcm(1)) == UNKNOWN_SPEAKER
        match = backend.match(_pcm(1))
        assert match.label == UNKNOWN_SPEAKER
        assert match.score == pytest.approx(0.0)

    def test_threshold_is_configurable(self) -> None:
        backend = _backend(threshold=0.5)
        backend.enroll(_pcm(0), label="Alice")
        assert backend.match(_pcm(2)).score == pytest.approx(0.0)
        backend.set_threshold(0.0)
        # With no threshold, the best (zero-score) candidate still wins.
        assert backend.identify(_pcm(2)) == "Alice"

    def test_remove_speaker(self) -> None:
        backend = _backend()
        backend.enroll(_pcm(0), label="Alice")
        assert backend.remove("Alice") is True
        assert backend.remove("Alice") is False
        assert backend.identify(_pcm(0)) == UNKNOWN_SPEAKER

    def test_match_returns_score(self) -> None:
        backend = _backend()
        backend.enroll(_pcm(0), label="Alice")
        match = backend.match(_pcm(0))
        assert match.label == "Alice"
        assert match.score == pytest.approx(1.0)

    def test_cancellation_is_honoured(self) -> None:
        backend = _backend()
        backend.enroll(_pcm(0), label="Alice")
        token = CancellationToken()
        token.cancel()
        with pytest.raises(PipelineCancelledError):
            backend.identify(_pcm(0), token=token)

    def test_empty_audio_rejected(self) -> None:
        with pytest.raises(ValueError, match="audio"):
            _backend().embed(b"")

    def test_persistence_across_instances(self, tmp_path: Any) -> None:
        path = tmp_path / "speakers.json"
        first = _backend(db_path=path)
        first.enroll(_pcm(0), label="Alice")

        second = _backend(db_path=path)
        assert second.identify(_pcm(0)) == "Alice"
        second.shutdown()

    def test_reset_reloads_persisted_speakers(self, tmp_path: Any) -> None:
        path = tmp_path / "speakers.db"
        backend = _backend(db_path=path)
        backend.enroll(_pcm(0), label="Alice")
        backend.reset()
        assert backend.list_speakers() == ("Alice",)

    def test_reset_clears_in_memory_speakers(self) -> None:
        backend = _backend()
        backend.enroll(_pcm(0), label="Alice")
        backend.reset()
        assert backend.list_speakers() == ()


# -- streaming --------------------------------------------------------------


class TestStreamingIdentification:
    def test_yields_one_segment_per_window(self) -> None:
        backend = _backend(chunk_ms=1000)
        backend.enroll(_pcm(0), label="Alice")
        backend.enroll(_pcm(1), label="Bob")
        chunks = [_pcm(0), _pcm(1), _pcm(0, seconds=0.5)]
        segments = list(backend.identify_stream(iter(chunks)))
        assert [(s.label, s.start_ms, s.end_ms) for s in segments] == [
            ("Alice", 0, 1000),
            ("Bob", 1000, 2000),
            ("Alice", 2000, 2500),
        ]

    def test_window_size_is_configurable(self) -> None:
        backend = _backend(chunk_ms=500)
        backend.enroll(_pcm(0), label="Alice")
        segments = list(backend.identify_stream(iter([_pcm(0)])))
        assert [(s.start_ms, s.end_ms) for s in segments] == [(0, 500), (500, 1000)]

    def test_cancellation_stops_stream(self) -> None:
        backend = _backend()
        token = CancellationToken()
        token.cancel()
        with pytest.raises(PipelineCancelledError):
            list(backend.identify_stream(iter([_pcm(0)]), token=token))


# -- diarization ------------------------------------------------------------


class FakeTurn:
    def __init__(self, start: float, end: float) -> None:
        self.start = start
        self.end = end


class FakeDiarizeOutput:
    """Mimics pyannote's DiarizeOutput.itertracks(yield_label=True)."""

    def itertracks(self, yield_label: bool = False) -> Generator[Any, None, None]:
        if yield_label:
            yield (FakeTurn(0.0, 1.5), 0, "Alice")
            yield (FakeTurn(1.5, 3.0), 1, "Bob")
        else:
            yield FakeTurn(0.0, 1.5)
            yield FakeTurn(1.5, 3.0)


class TestDiarization:
    def test_tuple_output(self) -> None:
        backend = _backend(
            diarizer=lambda _audio, _rate: [(0.0, 1.2, "Alice"), (1.2, 2.5, "Bob")]
        )
        segments = backend.diarize(_pcm(0, seconds=3))
        assert segments == [
            SpeakerSegment("Alice", 0, 1200),
            SpeakerSegment("Bob", 1200, 2500),
        ]

    def test_segment_output(self) -> None:
        backend = _backend(
            diarizer=lambda _audio, _rate: [SpeakerSegment("Alice", 0, 500)]
        )
        assert backend.diarize(_pcm(0)) == [SpeakerSegment("Alice", 0, 500)]

    def test_pyannote_style_output(self) -> None:
        backend = _backend(diarizer=lambda _audio, _rate: FakeDiarizeOutput())
        segments = backend.diarize(_pcm(0))
        assert [segment.label for segment in segments] == ["Alice", "Bob"]
        assert segments[0].start_ms == 0 and segments[0].end_ms == 1500
        assert segments[1].start_ms == 1500 and segments[1].end_ms == 3000

    def test_falls_back_to_streaming_without_model(self) -> None:
        backend = _backend(chunk_ms=1000)
        backend.enroll(_pcm(0), label="Alice")
        segments = backend.diarize(_pcm(0, seconds=2))
        assert [segment.label for segment in segments] == ["Alice", "Alice"]

    def test_cancellation_is_honoured(self) -> None:
        backend = _backend(diarizer=lambda _audio, _rate: [(0.0, 1.0, "Alice")])
        token = CancellationToken()
        token.cancel()
        with pytest.raises(PipelineCancelledError):
            backend.diarize(_pcm(0), token=token)


# -- benchmark-facing helper ------------------------------------------------


def test_store_snapshot_is_json_serialisable() -> None:
    """The persistence layer must never write Python tuples as binary blobs."""
    store = SpeakerStore()
    store.add("Alice", [1.0, 0.0])
    document = {"version": 1, "speakers": store._snapshot()}
    assert json.loads(json.dumps(document))["speakers"]["Alice"] == [[1.0, 0.0]]
