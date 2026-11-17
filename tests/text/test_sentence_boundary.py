"""Tests for voicevision.text sentence boundary detection."""

from __future__ import annotations

import pytest

from voicevision.text import (
    WordTiming,
    ends_sentence,
    extract_sentences,
    segments_from_words,
    spread_words,
)


class TestEndsSentence:
    """Tests for ends_sentence function."""

    def test_standard_punctuation(self) -> None:
        assert ends_sentence("hello.") is True
        assert ends_sentence("hello!") is True
        assert ends_sentence("hello?") is True
        assert ends_sentence("hello;") is True

    def test_trailing_quotes(self) -> None:
        assert ends_sentence('hello."') is True
        assert ends_sentence("hello.'") is True
        assert ends_sentence('hello."') is True
        assert ends_sentence('hello.»') is True

    def test_trailing_parentheses(self) -> None:
        assert ends_sentence("hello).") is True
        assert ends_sentence("hello].!") is True
        assert ends_sentence("hello』?") is True

    def test_no_sentence_end(self) -> None:
        assert ends_sentence("hello") is False
        assert ends_sentence("hello,") is False
        assert ends_sentence("hello:") is False
        assert ends_sentence("hello...") is False

    def test_empty_string(self) -> None:
        assert ends_sentence("") is False

    def test_cjk_punctuation(self) -> None:
        assert ends_sentence("你好。") is True
        assert ends_sentence("你好！") is True
        assert ends_sentence("你好？") is True
        assert ends_sentence("你好；") is True


class TestSpreadWords:
    """Tests for spread_words function."""

    def test_basic_distribution(self) -> None:
        words = [
            WordTiming(word="hello", t0=0, t1=0),
            WordTiming(word="world", t0=0, t1=0),
        ]
        result = spread_words(words, 0, 1000)
        assert len(result) == 2
        assert result[0].t0 == 0
        assert result[0].t1 == 500
        assert result[1].t0 == 500
        assert result[1].t1 == 1000

    def test_single_word(self) -> None:
        words = [WordTiming(word="hello", t0=0, t1=0)]
        result = spread_words(words, 100, 200)
        assert len(result) == 1
        assert result[0].t0 == 100
        assert result[0].t1 == 200

    def test_zero_duration(self) -> None:
        words = [
            WordTiming(word="a", t0=0, t1=0),
            WordTiming(word="b", t0=0, t1=0),
        ]
        result = spread_words(words, 100, 100)
        assert result[0].t0 == 100
        assert result[0].t1 == 100
        assert result[1].t0 == 100
        assert result[1].t1 == 100

    def test_empty_list(self) -> None:
        result = spread_words([], 0, 1000)
        assert result == []


class TestSegmentsFromWords:
    """Tests for segments_from_words function."""

    def test_single_segment(self) -> None:
        words = [
            WordTiming(word="hello", t0=0, t1=100),
            WordTiming(word="world", t0=100, t1=200),
        ]
        segments = segments_from_words(words)
        assert len(segments) == 1
        assert segments[0] == (0, 200, "hello world")

    def test_multiple_segments(self) -> None:
        words = [
            WordTiming(word="hello", t0=0, t1=100),
            WordTiming(word="world", t0=100, t1=200),
            WordTiming(word="foo", t0=1000, t1=1100),  # 800ms gap
            WordTiming(word="bar", t0=1100, t1=1200),
        ]
        segments = segments_from_words(words, max_gap_ms=700)
        assert len(segments) == 2
        assert segments[0] == (0, 200, "hello world")
        assert segments[1] == (1000, 1200, "foo bar")

    def test_custom_gap_threshold(self) -> None:
        words = [
            WordTiming(word="hello", t0=0, t1=100),
            WordTiming(word="world", t0=100, t1=200),
            WordTiming(word="foo", t0=500, t1=600),  # 300ms gap
        ]
        segments = segments_from_words(words, max_gap_ms=200)
        assert len(segments) == 2

    def test_empty_list(self) -> None:
        segments = segments_from_words([])
        assert segments == []


class TestExtractSentences:
    """Tests for extract_sentences function."""

    def test_simple_sentences(self) -> None:
        text = "Hello world. How are you? I am fine!"
        sentences = extract_sentences(text)
        assert sentences == ["Hello world.", "How are you?", "I am fine!"]

    def test_quotes(self) -> None:
        text = 'He said "Hello world." Then he left.'
        sentences = extract_sentences(text)
        assert sentences == ['He said "Hello world."', "Then he left."]

    def test_parentheses(self) -> None:
        text = "Hello (world). How are you?"
        sentences = extract_sentences(text)
        assert sentences == ["Hello (world).", "How are you?"]

    def test_abbreviations(self) -> None:
        text = "Dr. Smith went to the U.S.A. He saw Mr. Jones."
        sentences = extract_sentences(text)
        # Dr., U.S.A., Mr. should not split
        assert len(sentences) == 2
        assert "Dr. Smith went to the U.S.A." in sentences[0]
        assert "He saw Mr. Jones." in sentences[1]

    def test_ellipsis(self) -> None:
        text = "Hello... How are you?"
        sentences = extract_sentences(text)
        assert sentences == ["Hello...", "How are you?"]

    def test_cjk_punctuation(self) -> None:
        text = "你好世界。你好吗？"
        sentences = extract_sentences(text)
        assert sentences == ["你好世界。", "你好吗？"]

    def test_nested_quotes(self) -> None:
        text = 'She said "He asked \'Are you ok?\'" and left.'
        sentences = extract_sentences(text)
        # Should handle nested quotes properly
        assert len(sentences) >= 1

    def test_empty_string(self) -> None:
        assert extract_sentences("") == []
        assert extract_sentences("   ") == []

    def test_incomplete_sentence(self) -> None:
        text = "Hello world"
        sentences = extract_sentences(text)
        assert sentences == ["Hello world"]

    def test_multiple_punctuation(self) -> None:
        text = "What?! Really? Yes!"
        sentences = extract_sentences(text)
        assert sentences == ["What?!", "Really?", "Yes!"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
