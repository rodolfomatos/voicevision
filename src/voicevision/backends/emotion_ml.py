"""ML-based emotion classification for text and audio (T093).

transformers/torch are heavy and optional: this module imports without them and
loads a model only when a real classifier is requested. Tests inject
deterministic ``text_classifier`` / ``audio_classifier`` callables and need
neither torch nor a model download.

Results are multi-label: :attr:`EmotionResult.scores` carries the confidence of
every emotion in the configured taxonomy, while ``label``/``score`` are the
top prediction. Taxonomies: Ekman (6), Plutchik (8) or a custom iterable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, ClassVar

from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import EmotionResult, ProviderCapabilities, ProviderLifecycle
from voicevision.errors import BackendNotAvailableError

#: Ekman's six basic emotions.
EKMAN: tuple[str, ...] = ("anger", "disgust", "fear", "joy", "sadness", "surprise")
#: Plutchik's eight primary emotions (Ekman plus trust and anticipation).
PLUTCHIK: tuple[str, ...] = EKMAN + ("anticipation", "trust")
#: Backwards-compatible sentiment labels used by the keyword backend.
BASIC: tuple[str, ...] = ("positive", "negative", "neutral")

TAXONOMIES: dict[str, tuple[str, ...]] = {
    "ekman": EKMAN,
    "plutchik": PLUTCHIK,
    "basic": BASIC,
}

#: Common model labels mapped onto canonical taxonomy names.
_ALIASES: dict[str, str] = {
    "happy": "joy",
    "happiness": "joy",
    "excited": "joy",
    "amusement": "joy",
    "angry": "anger",
    "mad": "anger",
    "disgusted": "disgust",
    "fearful": "fear",
    "scared": "fear",
    "anxious": "fear",
    "nervous": "fear",
    "sad": "sadness",
    "sorrow": "sadness",
    "surprised": "surprise",
    "surprising": "surprise",
    "trusting": "trust",
    "acceptance": "trust",
    "anticipating": "anticipation",
    "interest": "anticipation",
}

#: Callable shapes accepted by the backend (tests inject simpler versions).
TextClassifier = Callable[[str], Any]
AudioClassifier = Callable[[bytes, int], Any]


def coerce_scores(output: Any) -> dict[str, float]:
    """Normalise the common HuggingFace output shapes into ``{label: score}``.

    Accepts a label/score mapping, a flat list of such mappings, a batch of one
    such list, or a plain ``{label: score}`` dictionary. Unknown shapes yield
    an empty mapping rather than raising — callers fall back to ``neutral``.
    """
    if isinstance(output, Mapping):
        if "label" in output and "score" in output:
            return {str(output["label"]): float(output["score"])}
        try:
            return {str(label): float(score) for label, score in output.items()}
        except (TypeError, ValueError):
            return {}
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
        return {}
    items: Sequence[Any] = output
    # Text pipelines with top_k=None return a one-element batch.
    if items and isinstance(items[0], Sequence) and not isinstance(items[0], Mapping):
        items = items[0]
    scores: dict[str, float] = {}
    for item in items:
        if isinstance(item, Mapping) and "label" in item and "score" in item:
            scores[str(item["label"])] = float(item["score"])
    return scores


class MLEmotionBackend:
    """Transformer-based text and audio emotion classification.

    Args:
        text_model: HuggingFace text-classification model id.
        audio_model: HuggingFace audio-classification model id. Audio detection
            is unavailable when this is None (and no classifier is injected).
        taxonomy: ``"ekman"``, ``"plutchik"``, ``"basic"`` or a custom iterable
            of canonical labels. ``"neutral"`` is always allowed as a fallback.
        device: HuggingFace device id (``-1`` = CPU, ``0`` = first GPU).
        text_classifier: Optional callable overriding the text pipeline.
        audio_classifier: Optional callable overriding the audio pipeline.

    The backend never imports torch or transformers at construction time.
    """

    _install_hint: ClassVar[str] = (
        "pip install 'voicevision[emotion]' (installs transformers and torch); "
        "models download on first use."
    )

    def __init__(
        self,
        *,
        text_model: str = "j-hartmann/emotion-english-distilroberta-base",
        audio_model: str | None = None,
        taxonomy: str | Iterable[str] = "ekman",
        device: int = -1,
        text_classifier: TextClassifier | None = None,
        audio_classifier: AudioClassifier | None = None,
    ) -> None:
        labels = self._resolve_taxonomy(taxonomy)
        self._taxonomy_name = taxonomy if isinstance(taxonomy, str) else "custom"
        self._labels: tuple[str, ...] = tuple(dict.fromkeys((*labels, "neutral")))
        self._text_model = text_model
        self._audio_model = audio_model
        self._device = device
        self._injected_text = text_classifier
        self._injected_audio = audio_classifier
        self._text_pipeline: Any | None = None
        self._audio_pipeline: Any | None = None

    @staticmethod
    def _resolve_taxonomy(taxonomy: str | Iterable[str]) -> tuple[str, ...]:
        if isinstance(taxonomy, str):
            known = TAXONOMIES.get(taxonomy.lower())
            if known is None:
                # Allow "joy,fear,sadness" without a separate config field.
                known = tuple(part.strip() for part in taxonomy.split(",") if part.strip())
            labels = known
        else:
            labels = tuple(str(label) for label in taxonomy)
        if not labels or any(not label.strip() for label in labels):
            raise ValueError("emotion taxonomy must contain non-empty labels")
        return labels

    # -- availability --------------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        """Whether transformers is importable in this environment."""
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    @classmethod
    def install_hint(cls) -> str:
        return cls._install_hint

    @property
    def labels(self) -> tuple[str, ...]:
        """Canonical labels considered by this backend."""
        return self._labels

    @property
    def taxonomy(self) -> str:
        return self._taxonomy_name

    def _to_result(self, raw: Any) -> EmotionResult:
        """Map model scores into the configured taxonomy and pick the top label."""
        filtered: dict[str, float] = {}
        for label, value in coerce_scores(raw).items():
            canonical = _ALIASES.get(label.lower(), label.lower())
            if canonical not in self._labels:
                continue
            # Aggressive dedup: keep the strongest score for aliased labels.
            filtered[canonical] = max(filtered.get(canonical, 0.0), value)
        if not filtered:
            return EmotionResult(label="neutral", score=0.0, scores={})
        label = max(filtered, key=lambda name: filtered[name])
        return EmotionResult(label=label, score=filtered[label], scores=dict(filtered))

    # -- classifiers ---------------------------------------------------------

    def _get_text_pipeline(self) -> Any:
        if self._text_pipeline is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise BackendNotAvailableError("transformers", self.install_hint()) from exc
            self._text_pipeline = pipeline(
                "text-classification", model=self._text_model, device=self._device
            )
        return self._text_pipeline

    def _get_audio_pipeline(self) -> Any:
        if self._audio_pipeline is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise BackendNotAvailableError("transformers", self.install_hint()) from exc
            self._audio_pipeline = pipeline(
                "audio-classification", model=self._audio_model, device=self._device
            )
        return self._audio_pipeline

    def _run_text(self, text: str) -> Any:
        if self._injected_text is not None:
            return self._injected_text(text)
        return self._get_text_pipeline()(text, top_k=None)

    def _run_audio(self, audio: bytes, sample_rate: int) -> Any:
        if self._injected_audio is not None:
            return self._injected_audio(audio, sample_rate)
        import numpy as np

        samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
        return self._get_audio_pipeline()(
            {"array": samples, "sampling_rate": sample_rate}, top_k=None
        )

    # -- EmotionProvider protocol --------------------------------------------

    def detect(
        self,
        text: str,
        *,
        token: CancellationToken | None = None,
    ) -> EmotionResult:
        """Classify text into the configured taxonomy."""
        if token is not None:
            token.throw_if_cancelled()
        if not text or not text.strip():
            return EmotionResult(label="neutral", score=0.0, scores={})
        return self._to_result(self._run_text(text))

    def detect_audio(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> EmotionResult:
        """Classify PCM16 audio into the configured taxonomy."""
        if token is not None:
            token.throw_if_cancelled()
        if not audio:
            return EmotionResult(label="neutral", score=0.0, scores={})
        if self._injected_audio is None and self._audio_model is None:
            raise BackendNotAvailableError(
                "audio emotion", "set audio_model or inject audio_classifier"
            )
        return self._to_result(self._run_audio(audio, sample_rate))

    # -- Provider protocol ---------------------------------------------------

    @property
    def name(self) -> str:
        return "ml"

    @property
    def modality(self) -> str:
        return "emotion"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=False,
            languages=frozenset({"en"}),
            models=frozenset(filter(None, [self._text_model, self._audio_model])),
            max_concurrent=1,  # a single loaded model is not thread-safe
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        need_transformers = (
            self._injected_text is None
            or (self._injected_audio is None and self._audio_model is not None)
        )
        if need_transformers and not self.available():
            raise BackendNotAvailableError("transformers", self.install_hint())

    def shutdown(self) -> None:
        self._text_pipeline = None
        self._audio_pipeline = None

    def health_check(self) -> bool:
        if self._injected_text is not None:
            return True
        return self.available()


__all__ = [
    "BASIC",
    "EKMAN",
    "PLUTCHIK",
    "TAXONOMIES",
    "MLEmotionBackend",
    "coerce_scores",
]
