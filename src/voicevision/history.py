"""Persistent transcript history stored as JSON Lines.

Why JSON Lines and not a JSON array: every transcription is a single append,
so the file is never rewritten and a crash can at worst truncate the last
line. Readers skip malformed lines instead of failing, which keeps the file
usable after manual edits.

The file contains personal data (what the user said). It is created with mode
``0600`` inside a ``0700`` directory, and persistence can be disabled with
``VOICEVISION_HISTORY_ENABLED=0`` or ``voicevision-listen --no-history``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_HISTORY_PATH = Path.home() / ".voicevision" / "history.jsonl"


def default_history_path() -> Path:
    """Return the history path, honouring ``VOICEVISION_HISTORY_FILE``."""
    override = os.environ.get("VOICEVISION_HISTORY_FILE", "")
    if override:
        return Path(override).expanduser()
    return DEFAULT_HISTORY_PATH


def history_enabled() -> bool:
    """Return whether persistence is enabled (default: enabled)."""
    raw = os.environ.get("VOICEVISION_HISTORY_ENABLED", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


@dataclass
class HistoryEntry:
    """One transcription event."""

    transcript: str
    timestamp: str
    language: str = ""
    audio_duration_seconds: float | None = None
    transcription_ms: float | None = None
    wake_word: str | None = None

    @classmethod
    def now(
        cls,
        transcript: str,
        *,
        language: str = "",
        audio_duration_seconds: float | None = None,
        transcription_ms: float | None = None,
        wake_word: str | None = None,
    ) -> HistoryEntry:
        """Build an entry stamped with the current local time (ISO 8601)."""
        return cls(
            transcript=transcript,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            language=language,
            audio_duration_seconds=audio_duration_seconds,
            transcription_ms=transcription_ms,
            wake_word=wake_word,
        )

    def to_json(self) -> str:
        """Serialize to a single JSON object (no trailing newline)."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> HistoryEntry | None:
        """Parse one line, returning ``None`` when it is not a valid entry."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        transcript = data.get("transcript")
        timestamp = data.get("timestamp")
        if not isinstance(transcript, str) or not isinstance(timestamp, str):
            return None
        return cls(
            transcript=transcript,
            timestamp=timestamp,
            language=str(data.get("language") or ""),
            audio_duration_seconds=_optional_float(data.get("audio_duration_seconds")),
            transcription_ms=_optional_float(data.get("transcription_ms")),
            wake_word=_optional_str(data.get("wake_word")),
        )


@dataclass
class HistoryStore:
    """Append-only store backed by a JSON Lines file."""

    path: Path = field(default_factory=default_history_path)

    def append(self, entry: HistoryEntry) -> None:
        """Append *entry* as one line.

        The file is opened with ``O_APPEND`` and written with a single
        ``os.write`` so concurrent writers do not interleave partial lines.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.suppress(OSError):
            # Best effort: a shared/pre-existing directory may not be ours.
            self.path.parent.chmod(0o700)
        payload = (entry.to_json() + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)

    def read(self, limit: int | None = None) -> list[HistoryEntry]:
        """Return entries oldest-first, skipping malformed lines.

        Args:
            limit: when set, return only the most recent *limit* entries.
        """
        if not self.path.exists():
            return []
        entries: list[HistoryEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                entry = HistoryEntry.from_json(stripped)
                if entry is not None:
                    entries.append(entry)
        if limit is not None:
            return entries[-limit:] if limit > 0 else []
        return entries

    def clear(self) -> None:
        """Truncate the file, keeping its restrictive permissions."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.write_text("", encoding="utf-8")
        with contextlib.suppress(OSError):
            self.path.chmod(0o600)


def main() -> None:
    """CLI: list or clear the transcript history."""
    parser = argparse.ArgumentParser(
        prog="voicevision-history",
        description="Show or clear the voicevision transcript history.",
    )
    parser.add_argument(
        "--file",
        default="",
        help="History file (default: ~/.voicevision/history.jsonl)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Show at most N recent entries (default: 20)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON Lines instead of a table",
    )
    parser.add_argument("--clear", action="store_true", help="Empty the history file")
    args = parser.parse_args()

    store = HistoryStore(Path(args.file).expanduser() if args.file else default_history_path())

    if args.clear:
        store.clear()
        print(f"cleared {store.path}")
        return

    entries = store.read(limit=args.limit)
    if args.json:
        for entry in entries:
            print(entry.to_json())
        return

    if not entries:
        print("no history", file=sys.stderr)
        return

    for entry in entries:
        wake = f" [{entry.wake_word}]" if entry.wake_word else ""
        print(f"{entry.timestamp}\t{entry.language or '-'}{wake}\t{entry.transcript}")


if __name__ == "__main__":
    main()
