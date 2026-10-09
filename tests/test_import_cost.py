"""NFR-1: importing the package must not cost the pydantic tax.

The Protocol interfaces are the reason to depend on this package. A caller who
only imports them should not pay ~200 ms for a settings library they never use.
These tests are the guard against someone "simplifying" the lazy imports back
to eager ones.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


class TestImportCost:
    def test_import_does_not_load_pydantic(self) -> None:
        """The whole point: pydantic must be absent after a bare import."""
        code = (
            "import sys; import voicevision; "
            "assert 'pydantic' not in sys.modules, sorted(sys.modules); "
            "assert 'pydantic_settings' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_protocol_import_stays_cheap(self) -> None:
        """Importing the interfaces alone must not drag in the config."""
        code = (
            "import sys; from voicevision.core.protocols import LLMBackend; "
            "assert 'pydantic_settings' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_core_modules_import_without_config(self) -> None:
        """The whole core must be reachable without touching the settings lib."""
        code = (
            "import voicevision, voicevision.core, voicevision.core.protocols, "
            "voicevision.core.registry, voicevision.errors;"
            "assert 'pydantic_settings' not in __import__('sys').modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr


class TestLazyAttribute:
    def test_config_accessible_as_attribute(self) -> None:
        import voicevision
        from voicevision.core.config import VoiceVisionConfig

        assert voicevision.VoiceVisionConfig is VoiceVisionConfig

    def test_config_importable_by_name(self) -> None:
        from voicevision import VoiceVisionConfig

        assert VoiceVisionConfig.__name__ == "VoiceVisionConfig"

    def test_subpackage_config_also_lazy(self) -> None:
        from voicevision.core import VoiceVisionConfig

        assert VoiceVisionConfig.__name__ == "VoiceVisionConfig"

    def test_eager_attributes_available(self) -> None:
        import voicevision

        for name in ("BackendRegistry", "LLMBackend", "STTBackend", "TTSBackend"):
            assert getattr(voicevision, name) is not None

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        import voicevision

        with pytest.raises(AttributeError, match="no attribute"):
            _ = voicevision.definitely_not_here

    def test_dir_includes_lazy_names(self) -> None:
        import voicevision

        listing = dir(voicevision)
        assert "VoiceVisionConfig" in listing
        assert "__version__" in listing

    def test_lazy_value_is_cached_not_reimported(self) -> None:
        """Second access must not re-run the import machinery."""
        import voicevision

        first = voicevision.VoiceVisionConfig
        second = voicevision.VoiceVisionConfig
        assert first is second

    def test_version_is_exposed(self) -> None:
        import voicevision

        assert voicevision.__version__ == "0.1.0"


class TestErrorExports:
    def test_errors_are_eagerly_available(self) -> None:
        """Callers catch these on every failure path; they must be cheap."""
        import voicevision

        assert issubclass(voicevision.BackendExecutionError, Exception)
        assert issubclass(voicevision.ConfigurationError, Exception)
