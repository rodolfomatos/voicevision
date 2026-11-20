"""T093 — ML-based emotion classification for text and audio.

transformers/torch are deliberately absent from the test environment:
classifiers are injected, so these tests exercise the real taxonomy mapping,
multi-label scoring, cancellation and latency paths without a model download.
"""

from __future__ import annotations

import builtins
import time
from typing import Any

import pytest

from voicevision.backends.emotion import SimpleEmotionBackend
from voicevision.backends.emotion_ml import (
    BASIC,
    EKMAN,
    PLUTCHIK,
    MLEmotionBackend,
    coerce_scores,
)
from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import EmotionProvider, EmotionResult, ProviderCapabilities
from voicevision.errors import BackendNotAvailableError, PipelineCancelledError

# -- helpers ----------------------------------------------------------------


def _text_backend(scores: dict[str, float] | None = None, **kwargs: object) -> MLEmotionBackend:
    payload = scores if scores is not None else {"joy": 0.8, "sadness": 0.2}
    return MLEmotionBackend(text_classifier=lambda _text: payload, **kwargs)


def _audio_backend(scores: dict[str, float] | None = None, **kwargs: object) -> MLEmotionBackend:
    payload = scores if scores is not None else {"anger": 0.7, "fear": 0.3}
    return MLEmotionBackend(audio_classifier=lambda _audio, _rate: payload, **kwargs)


def _pcm(seconds: float = 1.0) -> bytes:
    return b"\x00\x00" * int(seconds * 16000)


# -- score normalisation ----------------------------------------------------


class TestScoreNormalization:
    def test_flat_list_of_label_score_dicts(self) -> None:
        assert coerce_scores([{"label": "joy", "score": 0.9}]) == {"joy": 0.9}

    def test_single_batch_is_unwrapped(self) -> None:
        output = [[{"label": "joy", "score": 0.9}, {"label": "fear", "score": 0.1}]]
        assert coerce_scores(output) == {"joy": 0.9, "fear": 0.1}

    def test_plain_mapping(self) -> None:
        assert coerce_scores({"joy": 0.9, "fear": 0.1}) == {"joy": 0.9, "fear": 0.1}

    def test_single_label_score_mapping(self) -> None:
        assert coerce_scores({"label": "joy", "score": 0.9}) == {"joy": 0.9}

    @pytest.mark.parametrize("bad", [None, "joy", b"joy", 42, [1, 2, 3], {"joy": "high"}])
    def test_unknown_shapes_return_empty(self, bad: object) -> None:
        assert coerce_scores(bad) == {}


# -- taxonomy ---------------------------------------------------------------


class TestTaxonomy:
    def test_default_is_ekman(self) -> None:
        backend = _text_backend()
        assert backend.taxonomy == "ekman"
        assert backend.labels == EKMAN + ("neutral",)

    def test_plutchik_adds_trust_and_anticipation(self) -> None:
        backend = _text_backend(taxonomy="plutchik")
        assert backend.labels == PLUTCHIK + ("neutral",)
        assert "trust" in backend.labels and "anticipation" in backend.labels

    def test_basic_taxonomy(self) -> None:
        assert _text_backend(taxonomy="basic").labels == BASIC

    def test_custom_iterable(self) -> None:
        backend = _text_backend(taxonomy=["calm", "focused"])
        assert backend.taxonomy == "custom"
        assert backend.labels == ("calm", "focused", "neutral")

    def test_comma_separated_string(self) -> None:
        assert _text_backend(taxonomy="joy, fear").labels == ("joy", "fear", "neutral")

    @pytest.mark.parametrize("bad", ["", "  ", [], ["ok", "  "]])
    def test_invalid_taxonomy_rejected(self, bad: object) -> None:
        with pytest.raises(ValueError, match="taxonomy"):
            MLEmotionBackend(taxonomy=bad)  # type: ignore[arg-type]


# -- text classification ----------------------------------------------------


class TestTextDetection:
    def test_top_label_and_confidence(self) -> None:
        result = _text_backend({"joy": 0.8, "sadness": 0.2}).detect("what a great day")
        assert result.label == "joy"
        assert result.score == pytest.approx(0.8)
        assert result.scores == pytest.approx({"joy": 0.8, "sadness": 0.2})

    def test_multi_label_scores_are_preserved(self) -> None:
        scores = {"anger": 0.45, "fear": 0.35, "joy": 0.2}
        assert _text_backend(scores).detect("test").scores == pytest.approx(scores)

    def test_model_aliases_are_canonicalised(self) -> None:
        result = _text_backend({"happy": 0.9}).detect("test")
        assert result.label == "joy"
        assert result.scores == pytest.approx({"joy": 0.9})

    def test_alias_collision_keeps_strongest_score(self) -> None:
        result = _text_backend({"happy": 0.4, "joy": 0.9}).detect("test")
        assert result.scores["joy"] == pytest.approx(0.9)

    def test_labels_outside_taxonomy_are_dropped(self) -> None:
        result = _text_backend({"calm": 0.9, "joy": 0.2}).detect("test")
        assert result.label == "joy"
        assert "calm" not in result.scores

    def test_all_labels_outside_taxonomy_falls_back_to_neutral(self) -> None:
        result = _text_backend({"calm": 0.9}).detect("test")
        assert result == EmotionResult(label="neutral", score=0.0, scores={})

    @pytest.mark.parametrize("text", ["", "   "])
    def test_empty_text_is_neutral(self, text: str) -> None:
        assert _text_backend().detect(text) == EmotionResult("neutral", 0.0, {})

    def test_cancellation_is_honoured(self) -> None:
        token = CancellationToken()
        token.cancel()
        with pytest.raises(PipelineCancelledError):
            _text_backend().detect("test", token=token)

    def test_conforms_to_emotion_protocol(self) -> None:
        assert isinstance(_text_backend(), EmotionProvider)

    def test_capabilities(self) -> None:
        caps = _text_backend().capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.streaming is False
        assert caps.supports_cancellation is True
        assert caps.max_concurrent == 1

    def test_provider_metadata(self) -> None:
        backend = _text_backend()
        assert backend.name == "ml"
        assert backend.modality == "emotion"
        assert backend.health_check() is True
        backend.initialize()
        backend.shutdown()

    def test_lifecycle_with_injected_classifier_needs_no_transformers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_import = builtins.__import__

        def no_transformers(name: str, *args: object, **kwargs: object) -> Any:
            if name.startswith("transformers"):
                raise ImportError("transformers is not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_transformers)
        assert MLEmotionBackend.available() is False
        backend = _text_backend()
        backend.initialize()
        assert backend.health_check() is True
        assert backend.detect("test").label == "joy"

        with pytest.raises(BackendNotAvailableError, match="transformers"):
            MLEmotionBackend().initialize()

    def test_real_pipeline_missing_dependency(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_import = builtins.__import__

        def no_transformers(name: str, *args: object, **kwargs: object) -> Any:
            if name.startswith("transformers"):
                raise ImportError("transformers is not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_transformers)
        with pytest.raises(BackendNotAvailableError, match="transformers"):
            MLEmotionBackend().detect("test")

    def test_install_hint_names_the_extra(self) -> None:
        assert "emotion" in MLEmotionBackend.install_hint()


# -- audio classification ---------------------------------------------------


class TestAudioDetection:
    def test_top_label_and_confidence(self) -> None:
        result = _audio_backend({"anger": 0.7, "fear": 0.3}).detect_audio(_pcm())
        assert result.label == "anger"
        assert result.score == pytest.approx(0.7)
        assert result.scores == pytest.approx({"anger": 0.7, "fear": 0.3})

    def test_empty_audio_is_neutral(self) -> None:
        assert _audio_backend().detect_audio(b"") == EmotionResult("neutral", 0.0, {})

    def test_no_audio_model_raises(self) -> None:
        backend = _text_backend()
        with pytest.raises(BackendNotAvailableError, match="audio"):
            backend.detect_audio(_pcm())

    def test_cancellation_is_honoured(self) -> None:
        token = CancellationToken()
        token.cancel()
        with pytest.raises(PipelineCancelledError):
            _audio_backend().detect_audio(_pcm(), token=token)

    def test_audio_model_advertised_in_capabilities(self) -> None:
        caps = _audio_backend(audio_model="wav2vec2-emotion").capabilities()
        assert "wav2vec2-emotion" in caps.models


# -- real-time targets ------------------------------------------------------


class TestLatency:
    def test_text_detection_under_50ms(self) -> None:
        backend = _text_backend()
        start = time.perf_counter()
        for _ in range(20):
            backend.detect("I am so happy and excited about this wonderful news")
        assert (time.perf_counter() - start) / 20 < 0.05

    def test_audio_detection_under_200ms(self) -> None:
        backend = _audio_backend()
        start = time.perf_counter()
        for _ in range(5):
            backend.detect_audio(_pcm())
        assert (time.perf_counter() - start) / 5 < 0.2


# -- keyword backend conformance -------------------------------------------


class TestSimpleBackendConformance:
    def test_keyword_backend_is_still_emotion_provider(self) -> None:
        assert isinstance(SimpleEmotionBackend(), EmotionProvider)

    def test_keyword_backend_has_no_audio_model(self) -> None:
        with pytest.raises(NotImplementedError, match="text-only"):
            SimpleEmotionBackend().detect_audio(_pcm())
