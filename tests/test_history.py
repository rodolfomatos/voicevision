"""Tests for voicevision.history — append-only JSON Lines transcript store."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import pytest

from voicevision.history import (
    HistoryEntry,
    HistoryStore,
    default_history_path,
    history_enabled,
)


def make_entry(transcript: str = "ola mundo") -> HistoryEntry:
    return HistoryEntry.now(
        transcript,
        language="pt",
        audio_duration_seconds=1.5,
        transcription_ms=42.0,
    )


class TestEntry:
    def test_to_json_round_trip(self) -> None:
        entry = make_entry()
        restored = HistoryEntry.from_json(entry.to_json())
        assert restored == entry

    def test_now_sets_iso_timestamp(self) -> None:
        entry = HistoryEntry.now("hello")
        # YYYY-MM-DDTHH:MM:SS
        assert len(entry.timestamp) == 19
        assert entry.timestamp[4] == "-"
        assert entry.timestamp[10] == "T"

    def test_from_json_rejects_invalid_json(self) -> None:
        assert HistoryEntry.from_json("{not json") is None

    def test_from_json_rejects_non_object(self) -> None:
        assert HistoryEntry.from_json('["a", "b"]') is None

    def test_from_json_rejects_missing_fields(self) -> None:
        assert HistoryEntry.from_json('{"transcript": "hi"}') is None
        assert HistoryEntry.from_json('{"timestamp": "2026-01-01T00:00:00"}') is None

    def test_from_json_tolerates_bad_optionals(self) -> None:
        entry = HistoryEntry.from_json(
            json.dumps(
                {
                    "transcript": "hi",
                    "timestamp": "2026-01-01T00:00:00",
                    "audio_duration_seconds": "not-a-number",
                    "transcription_ms": None,
                }
            )
        )
        assert entry is not None
        assert entry.audio_duration_seconds is None
        assert entry.transcription_ms is None

    def test_wake_word_is_preserved(self) -> None:
        entry = HistoryEntry.now("turn on lights", wake_word="Olá Ambrósio")
        restored = HistoryEntry.from_json(entry.to_json())
        assert restored is not None
        assert restored.wake_word == "Olá Ambrósio"


class TestStore:
    def test_append_creates_parent_and_file(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "nested" / "history.jsonl")
        store.append(make_entry())
        assert store.path.exists()

    def test_file_permissions_are_restrictive(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "history.jsonl")
        store.append(make_entry())
        mode = stat.S_IMODE(store.path.stat().st_mode)
        assert mode == 0o600

    def test_parent_directory_permissions(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "private" / "history.jsonl")
        store.append(make_entry())
        mode = stat.S_IMODE(store.path.parent.stat().st_mode)
        assert mode == 0o700

    def test_append_is_one_line_per_entry(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "history.jsonl")
        store.append(make_entry("first"))
        store.append(make_entry("second"))
        lines = store.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["transcript"] == "first"
        assert json.loads(lines[1])["transcript"] == "second"

    def test_read_returns_entries_in_order(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "history.jsonl")
        store.append(make_entry("first"))
        store.append(make_entry("second"))
        assert [e.transcript for e in store.read()] == ["first", "second"]

    def test_read_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert HistoryStore(tmp_path / "absent.jsonl").read() == []

    def test_read_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        path.write_text(
            '{"transcript": "ok", "timestamp": "2026-01-01T00:00:00"}\n'
            "garbage\n"
            "\n"
            '{"transcript": "also ok", "timestamp": "2026-01-01T00:00:01"}\n',
            encoding="utf-8",
        )
        entries = HistoryStore(path).read()
        assert [e.transcript for e in entries] == ["ok", "also ok"]

    def test_read_limit_returns_most_recent(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "history.jsonl")
        for text in ("one", "two", "three"):
            store.append(make_entry(text))
        assert [e.transcript for e in store.read(limit=2)] == ["two", "three"]

    def test_read_limit_zero_returns_empty(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "history.jsonl")
        store.append(make_entry())
        assert store.read(limit=0) == []

    def test_clear_truncates_and_keeps_permissions(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "history.jsonl")
        store.append(make_entry())
        store.clear()
        assert store.read() == []
        mode = stat.S_IMODE(store.path.stat().st_mode)
        assert mode == 0o600


class TestEnvironment:
    def test_default_path_uses_home(
        self,
        monkeypatch: Any,
    ) -> None:
        monkeypatch.delenv("VOICEVISION_HISTORY_FILE", raising=False)
        assert default_history_path() == Path.home() / ".voicevision" / "history.jsonl"

    def test_path_override(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_HISTORY_FILE", "/tmp/custom.jsonl")
        assert default_history_path() == Path("/tmp/custom.jsonl")

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE"])
    def test_disabled_values(self, monkeypatch: Any, value: str) -> None:
        monkeypatch.setenv("VOICEVISION_HISTORY_ENABLED", value)
        assert history_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", ""])
    def test_enabled_values(self, monkeypatch: Any, value: str) -> None:
        monkeypatch.setenv("VOICEVISION_HISTORY_ENABLED", value)
        assert history_enabled() is True
