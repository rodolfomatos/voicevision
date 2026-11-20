"""Speaker embeddings, identification and diarization (T092).

pyannote.audio (and its torch dependency) is heavy and optional. Everything in
this module imports without it: the library is loaded only when a real embedding
or a real diarization pipeline is actually requested. Tests inject a deterministic
``embedder`` callable and need neither torch nor a model download.

The store keeps one or more L2-normalised embeddings per label, matches by cosine
similarity against the mean embedding, and can persist to SQLite or JSON.
"""

from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import threading
from collections.abc import Callable, Generator, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from voicevision.audio import pcm16_to_wav
from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import (
    ProviderCapabilities,
    ProviderLifecycle,
    SpeakerMatch,
    SpeakerSegment,
    SpeakerStoreProtocol,
)
from voicevision.errors import BackendNotAvailableError

if TYPE_CHECKING:
    import pyannote.audio  # noqa: F401

#: Returned when no enrolled speaker clears the configured threshold.
UNKNOWN_SPEAKER = "Speaker ?"

#: Embedding callables receive raw PCM16 and sample rate, and return a vector.
Embedder = Callable[[bytes, int], list[float] | tuple[float, ...]]
#: Diarizers receive raw PCM16 and sample rate, and return labelled spans.
Diarizer = Callable[[bytes, int], Iterable[SpeakerSegment | tuple[float, float, str]]]


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    """Cosine similarity of two vectors. Zero for empty or zero-norm inputs."""
    left = tuple(a)
    right = tuple(b)
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(x * y for x, y in zip(left, right, strict=True))
    norm_a = math.sqrt(sum(x * x for x in left))
    norm_b = math.sqrt(sum(x * x for x in right))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalise(vector: Iterable[float]) -> tuple[float, ...]:
    """Return an L2-normalised copy of ``vector``."""
    values = tuple(float(value) for value in vector)
    if not values:
        raise ValueError("speaker embedding must not be empty")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        raise ValueError("speaker embedding must not be all zeros")
    return tuple(value / norm for value in values)


class SpeakerStore(SpeakerStoreProtocol):
    """Thread-safe embedding store with optional SQLite or JSON persistence.

    ``path=None`` keeps everything in memory. A path ending in ``.json`` uses a
    single JSON document; any other suffix uses SQLite. Missing files are
    created on the first write.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = str(path) if path is not None else None
        self._embeddings: dict[str, list[tuple[float, ...]]] = {}
        self._lock = threading.RLock()
        if self._path:
            self._load()

    @property
    def path(self) -> str | None:
        return self._path

    def add(self, label: str, vector: Iterable[float]) -> None:
        """Enroll (or re-enroll) one embedding for ``label``."""
        if not label or not label.strip():
            raise ValueError("speaker label must not be empty")
        clean = normalise(vector)
        with self._lock:
            self._embeddings.setdefault(label, []).append(clean)
            self._flush()

    def remove(self, label: str) -> bool:
        """Remove a speaker. Returns True when something was removed."""
        with self._lock:
            existed = self._embeddings.pop(label, None) is not None
            if existed:
                self._flush()
            return existed

    def vectors(self, label: str) -> tuple[tuple[float, ...], ...]:
        with self._lock:
            return tuple(self._embeddings.get(label, ()))

    def mean(self, label: str) -> tuple[float, ...] | None:
        """Average all embeddings for a label, re-normalised for cosine matching."""
        vectors = self.vectors(label)
        if not vectors:
            return None
        size = len(vectors[0])
        averaged = tuple(sum(v[index] for v in vectors) / len(vectors) for index in range(size))
        try:
            return normalise(averaged)
        except ValueError:
            return vectors[0]

    def labels(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._embeddings))

    def clear(self) -> None:
        with self._lock:
            self._embeddings.clear()
            self._flush()

    def flush(self) -> None:
        """Persist the current store. No-op for in-memory stores."""
        with self._lock:
            self._flush()

    # -- persistence ---------------------------------------------------------

    def _snapshot(self) -> dict[str, list[list[float]]]:
        return {
            label: [[float(value) for value in vector] for vector in vectors]
            for label, vectors in self._embeddings.items()
        }

    def _flush(self) -> None:
        if not self._path:
            return
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self._snapshot()
        if path.suffix.lower() == ".json":
            path.write_text(
                json.dumps({"version": 1, "speakers": snapshot}, indent=2),
                encoding="utf-8",
            )
            return
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS speakers ("
                "label TEXT PRIMARY KEY, embedding TEXT NOT NULL)"
            )
            connection.execute("DELETE FROM speakers")
            connection.executemany(
                "INSERT INTO speakers (label, embedding) VALUES (?, ?)",
                [(label, json.dumps(vectors)) for label, vectors in snapshot.items()],
            )

    def _load(self) -> None:
        assert self._path is not None
        path = Path(self._path)
        if not path.exists():
            return
        loaded: dict[str, list[list[float]]] = {}
        if path.suffix.lower() == ".json":
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return
            raw = document.get("speakers", {}) if isinstance(document, Mapping) else {}
            if isinstance(raw, Mapping):
                loaded = {
                    str(label): [list(map(float, vector)) for vector in vectors]
                    for label, vectors in raw.items()
                    if isinstance(vectors, list)
                }
        else:
            try:
                with sqlite3.connect(path) as connection:
                    rows = connection.execute("SELECT label, embedding FROM speakers")
                    loaded = {
                        str(label): [list(map(float, vector)) for vector in json.loads(raw)]
                        for label, raw in rows
                    }
            except (sqlite3.Error, ValueError, TypeError):
                return
        self._embeddings = {
            label: [normalise(vector) for vector in vectors if any(vector)]
            for label, vectors in loaded.items()
        }
        self._embeddings = {
            label: vectors for label, vectors in self._embeddings.items() if vectors
        }


class PyannoteSpeakerBackend:
    """Speaker identification and diarization backed by pyannote.audio.

    Args:
        embedding_model: Hugging Face model id for the embedding pipeline.
        diarization_model: Optional model id for diarization. Without it (and
            without an injected diarizer), :meth:`diarize` falls back to
            sliding-window identification.
        threshold: Minimum cosine similarity to accept an identity (0-1).
        db_path: Optional SQLite or ``.json`` file for enrolled embeddings.
        device: Torch device passed to pyannote (``"cpu"`` by default).
        hf_token: Hugging Face token for gated diarization models.
        embedder: Optional callable overriding pyannote (used by tests).
        diarizer: Optional callable overriding the diarization pipeline.
        chunk_ms: Window length used by streaming identification.

    The backend never imports torch or pyannote at construction time.
    """

    _install_hint: ClassVar[str] = (
        "pip install 'voicevision[speaker]' (installs pyannote.audio and torch); "
        "gated models also require a Hugging Face token."
    )

    def __init__(
        self,
        *,
        embedding_model: str = "pyannote/embedding",
        diarization_model: str | None = None,
        threshold: float = 0.7,
        db_path: str | Path | None = None,
        device: str = "cpu",
        hf_token: str | None = None,
        embedder: Embedder | None = None,
        diarizer: Diarizer | None = None,
        chunk_ms: int = 1000,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        self._embedding_model = embedding_model
        self._diarization_model = diarization_model
        self._threshold = float(threshold)
        self._device = device
        self._hf_token = hf_token
        self._chunk_ms = chunk_ms
        self._injected_embedder = embedder
        self._injected_diarizer = diarizer
        self._embedder: Any | None = None
        self._pipeline: Any | None = None
        self._store = SpeakerStore(db_path)

    # -- availability --------------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        """Whether pyannote.audio is importable in this environment."""
        try:
            import pyannote.audio  # noqa: F401
        except ImportError:
            return False
        return True

    @classmethod
    def install_hint(cls) -> str:
        return cls._install_hint

    @property
    def threshold(self) -> float:
        return self._threshold

    def set_threshold(self, value: float) -> None:
        """Update the cosine-similarity acceptance threshold."""
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        self._threshold = float(value)

    @property
    def store(self) -> SpeakerStore:
        return self._store

    # -- embeddings ----------------------------------------------------------

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            try:
                from pyannote.audio import Inference
            except ImportError as exc:
                raise BackendNotAvailableError("pyannote", self.install_hint()) from exc
            self._embedder = Inference(self._embedding_model, device=self._device)
        return self._embedder

    def embed(self, audio: bytes, *, sample_rate: int = 16000) -> tuple[float, ...]:
        """Extract and L2-normalise one embedding from PCM16 audio."""
        if not audio:
            raise ValueError("audio must not be empty")
        if self._injected_embedder is not None:
            return normalise(self._injected_embedder(audio, sample_rate))
        import numpy as np
        import torch

        samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
        waveform = torch.from_numpy(samples).unsqueeze(0)
        raw = self._get_embedder()({"waveform": waveform, "sample_rate": sample_rate})
        if hasattr(raw, "cpu"):
            raw = raw.cpu().numpy()
        return normalise(getattr(raw, "flatten", lambda: raw)())

    # -- SpeakerIDProvider protocol ------------------------------------------

    def identify(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> str:
        """Return the best-matching enrolled label, or ``UNKNOWN_SPEAKER``."""
        return self.match(audio, sample_rate=sample_rate, token=token).label

    def match(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> SpeakerMatch:
        """Identify a speaker and return the cosine similarity score."""
        if token is not None:
            token.throw_if_cancelled()
        embedding = self.embed(audio, sample_rate=sample_rate)
        labels = self._store.labels()
        if not labels:
            return SpeakerMatch(UNKNOWN_SPEAKER, 0.0)
        best_label = UNKNOWN_SPEAKER
        best_score = float("-inf")
        for label in labels:
            if token is not None:
                token.throw_if_cancelled()
            reference = self._store.mean(label)
            score = cosine_similarity(embedding, reference or ())
            if score > best_score:
                best_score = score
                best_label = label
        if best_score < self._threshold:
            return SpeakerMatch(UNKNOWN_SPEAKER, best_score)
        return SpeakerMatch(best_label, best_score)

    def enroll(
        self,
        audio: bytes,
        *,
        label: str,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> None:
        """Enroll (or re-enroll) a speaker from reference audio."""
        if token is not None:
            token.throw_if_cancelled()
        self._store.add(label, self.embed(audio, sample_rate=sample_rate))

    def remove(self, label: str) -> bool:
        """Remove an enrolled speaker."""
        return self._store.remove(label)

    def list_speakers(self) -> tuple[str, ...]:
        return self._store.labels()

    def reset(self) -> None:
        """Clear session state; enrolled speakers with a db_path are reloaded."""
        # Replacing the store (rather than clearing it) avoids overwriting a
        # persisted database with an empty snapshot before reloading it.
        self._store = SpeakerStore(self._store.path)

    # -- streaming and diarization ------------------------------------------

    def identify_stream(
        self,
        audio_chunks: Iterable[bytes],
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> Generator[SpeakerSegment, None, None]:
        """Yield a speaker label per fixed-size window as audio arrives."""
        window_bytes = max(1, self._chunk_ms * sample_rate // 1000 * 2)
        buffer = bytearray()
        offset = 0
        for chunk in audio_chunks:
            if token is not None:
                token.throw_if_cancelled()
            buffer.extend(chunk)
            while len(buffer) >= window_bytes:
                window = bytes(buffer[:window_bytes])
                del buffer[:window_bytes]
                match = self.match(window, sample_rate=sample_rate, token=token)
                start_ms = offset * 1000 // (sample_rate * 2)
                offset += window_bytes
                end_ms = offset * 1000 // (sample_rate * 2)
                yield SpeakerSegment(match.label, start_ms, end_ms, match.score)
        if buffer:
            match = self.match(bytes(buffer), sample_rate=sample_rate, token=token)
            start_ms = offset * 1000 // (sample_rate * 2)
            offset += len(buffer)
            end_ms = offset * 1000 // (sample_rate * 2)
            yield SpeakerSegment(match.label, start_ms, end_ms, match.score)

    def diarize(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> list[SpeakerSegment]:
        """Return labelled speaker turns for multi-speaker audio.

        Uses the injected diarizer or a pyannote diarization pipeline when
        configured. Otherwise falls back to sliding-window identification —
        useful when every speaker is enrolled but no diarization model is
        available.
        """
        if token is not None:
            token.throw_if_cancelled()
        if self._injected_diarizer is not None:
            return self._normalize_segments(self._injected_diarizer(audio, sample_rate))
        if self._diarization_model:
            return self._normalize_segments(
                self._diarize_with_pyannote(audio, sample_rate, token)
            )
        return list(self.identify_stream(iter([audio]), sample_rate=sample_rate, token=token))

    def _diarize_with_pyannote(
        self,
        audio: bytes,
        sample_rate: int,
        token: CancellationToken | None,
    ) -> Any:
        if token is not None:
            token.throw_if_cancelled()
        if self._pipeline is None:
            try:
                from pyannote.audio import Pipeline
            except ImportError as exc:
                raise BackendNotAvailableError("pyannote", self.install_hint()) from exc
            self._pipeline = Pipeline.from_pretrained(
                self._diarization_model, use_auth_token=self._hf_token
            )
        # pyannote's pipeline consumes a file path, not raw bytes.
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            handle.write(pcm16_to_wav(audio, sample_rate=sample_rate))
            handle.flush()
            return self._pipeline(handle.name)

    @staticmethod
    def _normalize_segments(
        output: Iterable[SpeakerSegment | tuple[float, float, str]],
    ) -> list[SpeakerSegment]:
        """Accept SpeakerSegment, (start_s, end_s, label) or pyannote turns."""
        if hasattr(output, "itertracks"):
            tracks: list[SpeakerSegment] = []
            for turn, _track, label in output.itertracks(yield_label=True):
                tracks.append(
                    SpeakerSegment(
                        str(label), round(turn.start * 1000), round(turn.end * 1000)
                    )
                )
            return tracks
        segments: list[SpeakerSegment] = []
        for item in output:
            if isinstance(item, SpeakerSegment):
                segments.append(item)
            else:
                start, end, label = item
                segments.append(SpeakerSegment(str(label), round(start * 1000), round(end * 1000)))
        return segments

    # -- Provider protocol ---------------------------------------------------

    @property
    def name(self) -> str:
        return "pyannote"

    @property
    def modality(self) -> str:
        return "speakerid"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=True,
            languages=frozenset(),
            models=frozenset(
                filter(None, [self._embedding_model, self._diarization_model])
            ),
            max_concurrent=1,
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        if self._injected_embedder is None and not self.available():
            raise BackendNotAvailableError("pyannote", self.install_hint())

    def shutdown(self) -> None:
        self._embedder = None
        self._pipeline = None
        self._store.flush()

    def health_check(self) -> bool:
        return self._injected_embedder is not None or self.available()


__all__ = [
    "UNKNOWN_SPEAKER",
    "PyannoteSpeakerBackend",
    "SpeakerStore",
    "cosine_similarity",
    "normalise",
]
