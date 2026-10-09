"""Tests for the deployment preflight.

A preflight that reports the wrong thing is worse than none, because the
operator trusts it and stops looking. Each test asserts the message names a
fix, not just that it fails.
"""

from __future__ import annotations

import builtins
import os
from pathlib import Path

import pytest

from voicevision.preflight import Report, main


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("VOICEVISION_"):
            monkeypatch.delenv(key, raising=False)


class TestReport:
    def test_empty_report_is_ok(self) -> None:
        assert Report().exit_code == 0

    def test_problem_sets_exit_code(self) -> None:
        report = Report()
        report.failed("broken", "fix it")
        assert report.exit_code == 1

    def test_problem_keeps_the_fix(self) -> None:
        report = Report()
        report.failed("broken", "do the thing")
        assert report.problems == [("broken", "do the thing")]


class TestModelChecks:
    def test_missing_model_names_the_env_var_and_the_fix(self, monkeypatch, tmp_path):
        monkeypatch.setenv("VOICEVISION_LLM_MODEL", str(tmp_path / "absent.gguf"))
        report = Report()
        from voicevision.preflight import check_models

        check_models(report)
        messages = " ".join(m for m, _ in report.problems)
        fixes = " ".join(f for _, f in report.problems)
        assert "VOICEVISION_LLM_MODEL" in messages
        assert "/models" in fixes

    def test_unset_model_is_reported_not_silently_skipped(self):
        from voicevision.preflight import check_models

        report = Report()
        check_models(report)
        # All three modalities unset must produce three findings.
        assert len(report.problems) == 3

    def test_existing_model_passes(self, monkeypatch, tmp_path):
        model = tmp_path / "model.gguf"
        model.write_bytes(b"x" * 2048)
        monkeypatch.setenv("VOICEVISION_LLM_MODEL", str(model))
        monkeypatch.setenv("VOICEVISION_STT_MODEL", str(model))
        monkeypatch.setenv("VOICEVISION_TTS_MODEL", str(model))
        from voicevision.preflight import check_models

        report = Report()
        check_models(report)
        assert report.problems == []
        assert len(report.ok) == 3

    def test_directory_is_not_a_model(self, monkeypatch, tmp_path):
        monkeypatch.setenv("VOICEVISION_LLM_MODEL", str(tmp_path))
        monkeypatch.setenv("VOICEVISION_STT_MODEL", str(tmp_path))
        monkeypatch.setenv("VOICEVISION_TTS_MODEL", str(tmp_path))
        from voicevision.preflight import check_models

        report = Report()
        check_models(report)
        assert len(report.problems) == 3


class TestAudioChecks:
    def test_audio_not_demanded_unless_requested(self):
        """A headless run must not fail because it has no microphone."""
        from voicevision.preflight import check_audio_required

        report = Report()
        check_audio_required(report)
        assert report.problems == []

    def test_missing_snd_when_audio_requested(self, monkeypatch) -> None:
        monkeypatch.setenv("VOICEVISION_AUDIO_BACKEND", "sounddevice")
        monkeypatch.setattr(Path, "exists", lambda _path: False)
        from voicevision.preflight import check_audio_required

        report = Report()
        check_audio_required(report)
        fixes = " ".join(f for _, f in report.problems)
        assert "/dev/snd" in fixes


class TestExecutableChecks:
    def test_missing_binary_names_the_fix(self):
        from voicevision.preflight import check_executables

        report = Report()
        check_executables(report)
        # llama-server / whisper-cli / piper are not on a dev machine, so all
        # three should be reported with a remedy.
        assert len(report.problems) == 3
        for _, fix in report.problems:
            assert fix

    def test_present_binary_is_reported_as_ok(self, monkeypatch):
        monkeypatch.setattr("voicevision.preflight.shutil.which", lambda b: f"/usr/bin/{b}")
        from voicevision.preflight import check_executables

        report = Report()
        check_executables(report)
        assert report.problems == []
        assert len(report.ok) == 3


class TestMain:
    def test_exit_code_nonzero_when_broken(self) -> None:
        assert main() == 1

    def test_output_mentions_the_problem_and_the_fix(self, capsys) -> None:
        main()
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "fix:" in out

    def test_no_model_or_binary_findings_when_all_present(
        self, monkeypatch, tmp_path, capsys
    ) -> None:
        """Everything configured must produce zero model/binary problems.

        `main()` still exits non-zero in CI because webrtcvad and sounddevice
        are not installed, so assert on the specific findings rather than on
        the exit code.
        """
        model = tmp_path / "m.gguf"
        model.write_bytes(b"x")
        for key in (
            "VOICEVISION_LLM_MODEL",
            "VOICEVISION_STT_MODEL",
            "VOICEVISION_TTS_MODEL",
        ):
            monkeypatch.setenv(key, str(model))
        monkeypatch.setattr("voicevision.preflight.shutil.which", lambda b: f"/usr/bin/{b}")
        monkeypatch.delenv("VOICEVISION_AUDIO_BACKEND", raising=False)

        main()
        out = capsys.readouterr().out
        assert "does not exist" not in out
        assert "not on PATH" not in out
        assert "is not set" not in out


class TestLibraryImportFailures:
    """Audio libraries fail at import for more reasons than absence."""

    def test_oserror_is_reported_not_raised(self, monkeypatch) -> None:
        """sounddevice raises OSError("PortAudio library not found"), not
        ImportError. Letting that propagate makes the diagnostic crash."""
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "sounddevice":
                raise OSError("PortAudio library not found")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", fake_import)
        from voicevision.preflight import check_library_imports

        report = Report()
        check_library_imports(report)

        sounddevice_problems = [p for p in report.problems if "sounddevice" in p[0]]
        assert sounddevice_problems, "the OSError must be reported as a finding"
        message, fix = sounddevice_problems[0]
        assert "OSError" in message
        assert "PortAudio" in message
        assert "PortAudio" in fix

    def test_importerror_names_the_extra(self, monkeypatch) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "webrtcvad":
                raise ImportError("No module named 'webrtcvad'")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", fake_import)
        from voicevision.preflight import check_library_imports

        report = Report()
        check_library_imports(report)

        vad_problems = [p for p in report.problems if "webrtcvad" in p[0]]
        assert vad_problems
        assert "not installed" in vad_problems[0][0]
