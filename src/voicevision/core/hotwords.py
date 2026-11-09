"""Hotword configuration for wake word detection.

Loads a list of wake words from a JSON file or environment variable.
Default is ["Olá Ambrósio"] with threshold 0.5.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOTWORDS: list[str] = []
DEFAULT_THRESHOLD: float = 0.5
ENV_VAR: str = "VOICEVISION_HOTWORDS"
DEFAULT_PATH: Path = Path.home() / ".voicevision" / "hotwords.json"


@dataclass
class HotwordConfig:
    """Configuration for wake word detection.

    Attributes:
        words: List of wake words to match (case-insensitive, normalized).
        threshold: Confidence threshold (0.0-1.0). Not currently used by the
            substring matcher but reserved for future ML-based detection.
    """

    words: list[str] = field(default_factory=lambda: DEFAULT_HOTWORDS.copy())
    threshold: float = DEFAULT_THRESHOLD


def _normalize_text(text: str) -> str:
    """Normalize text for wake word matching.

    Lowercases, decomposes accented characters (NFD), strips combining marks,
    and collapses whitespace. This makes "Olá Ambrósio", "OLÁ AMBRÓSIO" and
    "ola ambrosio" all match the same wake word.
    """
    import unicodedata

    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in text if c.isalnum() or c.isspace())
    return " ".join(stripped.split())


def load_hotwords(
    path: Path | None = None,
    env_var: str | None = ENV_VAR,
) -> HotwordConfig:
    """Load hotword configuration from file or environment.

    Priority:
    1. Explicit *path* argument (if provided)
    2. *env_var* environment variable (default: VOICEVISION_HOTWORDS)
    3. Default path (~/.voicevision/hotwords.json)
    4. Built-in default: ["Olá Ambrósio"] with threshold 0.5

    The JSON file format:
    ```json
    {
      "words": ["Olá Ambrósio", "Hey Ambrósio"],
      "threshold": 0.5
    }
    ```

    Args:
        path: Optional explicit path to the JSON file.
        env_var: Environment variable name to read the path from.

    Returns:
        HotwordConfig with the loaded words and threshold.
    """
    config = HotwordConfig()

    # 1. Explicit path
    if path is not None:
        config_path = path
    # 2. Environment variable
    elif env_var and (env_path := os.environ.get(env_var)):
        config_path = Path(env_path)
    # 3. Default path
    elif DEFAULT_PATH.exists():
        config_path = DEFAULT_PATH
    else:
        return config

    try:
        content = config_path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            return config
        if "words" in data and isinstance(data["words"], list):
            words = [str(w) for w in data["words"] if str(w).strip()]
            if words:
                config.words = words
        if "threshold" in data and isinstance(data["threshold"], (int, float)):
            config.threshold = max(0.0, min(1.0, float(data["threshold"])))
    except (OSError, json.JSONDecodeError):
        # Invalid file: fall back to default
        pass
    return config


def wake_words_detected(transcript: str, config: HotwordConfig) -> tuple[bool, str | None]:
    """Check if any configured wake word is in the transcript.

    Returns:
        Tuple of (detected, matched_word). matched_word is the first matching
        wake word from the config (normalized form), or None if no match.
    """
    if not config.words:
        return False, None
    norm_text = _normalize_text(transcript)
    for word in config.words:
        norm_word = _normalize_text(word)
        if norm_word in norm_text:
            return True, word
    return False, None
