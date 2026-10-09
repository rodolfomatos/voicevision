"""Deployment preflight.

Answers one question: why is this not working *right now*, before anything is
attempted. Every message names the fix, because "backend unavailable" is not
actionable and a container makes the usual debugging steps unavailable anyway.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Model paths must exist for the pipeline to run at all.
_MODEL_FIELDS = (
    ("VOICEVISION_LLM_MODEL", "llm"),
    ("VOICEVISION_STT_MODEL", "stt"),
    ("VOICEVISION_TTS_MODEL", "tts"),
)

_EXECUTABLES = (
    ("llama-server", "llamacpp backend"),
    ("whisper-cli", "whispercpp backend"),
    ("piper", "piper backend"),
)


@dataclass
class Report:
    """Collected preflight findings."""

    ok: list[str] = field(default_factory=list)
    problems: list[tuple[str, str]] = field(default_factory=list)

    def passed(self, message: str) -> None:
        self.ok.append(message)

    def failed(self, message: str, fix: str) -> None:
        self.problems.append((message, fix))

    @property
    def exit_code(self) -> int:
        return 1 if self.problems else 0


def check_executables(report: Report) -> None:
    for binary, purpose in _EXECUTABLES:
        path = shutil.which(binary)
        if path:
            report.passed(f"{binary} ({purpose}) at {path}")
        else:
            report.failed(
                f"{binary} not on PATH — {purpose} cannot start",
                "rebuild the image, or install the binary; see README 'Troubleshooting'",
            )


def check_models(report: Report) -> None:
    for env_var, modality in _MODEL_FIELDS:
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            report.failed(
                f"{env_var} is not set — no {modality} model configured",
                f"mount a volume at /models and set {env_var}",
            )
            continue
        path = Path(raw).expanduser()
        if path.is_file():
            size_mb = path.stat().st_size / 1_048_576
            report.passed(f"{modality} model {path.name} ({size_mb:.0f} MB)")
        else:
            report.failed(
                f"{env_var} points at {raw}, which does not exist",
                "models are mounted, not baked in — check the volume mount "
                "(docker/voicevision-compose.yml mounts ./models:/models)",
            )


def check_audio(report: Report) -> None:
    """Container audio needs the host device node passed through (ADR-003 §1)."""
    if not Path("/dev/snd").exists():
        report.failed(
            "/dev/snd is absent — no audio device visible in this container",
            "start the container with `--device /dev/snd`, or with "
            "docker-compose's devices: block already set",
        )
        return
    report.passed("/dev/snd present")
    listing = shutil.which("aplay")
    if listing:
        report.passed("aplay available for device enumeration")


def check_library_imports(report: Report) -> None:
    for module, purpose in (("webrtcvad", "vad"), ("sounddevice", "audio capture")):
        try:
            __import__(module)
        except ImportError:
            report.failed(
                f"{module} is not installed — {purpose} unavailable",
                f"pip install voicevision[extras] including {module}",
            )
        except Exception as exc:
            # Audio libraries fail at import for reasons other than absence.
            # sounddevice, for instance, is a Python package that raises
            # OSError("PortAudio library not found") when the system library is
            # absent — which is exactly the container misconfiguration this
            # preflight exists to catch. Letting that propagate would make the
            # diagnostic tool itself the thing that crashes.
            report.failed(
                f"{module} is installed but failed to load: {type(exc).__name__}: {exc}",
                "check the native system library (PortAudio, ALSA) is present "
                "in the image — see docs/ADR-003-container-deployment.md §1",
            )
        else:
            report.passed(f"{module} importable ({purpose})")


def check_audio_required(report: Report) -> None:
    """Only demand audio when a backend actually needs it."""
    needs_audio = os.environ.get("VOICEVISION_AUDIO_BACKEND", "").lower() in {
        "sounddevice",
        "1",
        "true",
    }
    if needs_audio:
        check_audio(report)


def main() -> int:
    report = Report()
    check_executables(report)
    check_models(report)
    check_library_imports(report)
    check_audio_required(report)

    print("voicevision preflight")
    print("=" * 60)
    for message in report.ok:
        print(f"  OK    {message}")
    for message, fix in report.problems:
        print(f"  FAIL  {message}")
        print(f"        fix: {fix}")
    print("=" * 60)

    if report.problems:
        print(f"{len(report.problems)} problem(s) found.")
        return report.exit_code

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
