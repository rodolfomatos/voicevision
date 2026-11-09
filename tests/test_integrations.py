"""Structural checks for the integrations tree.

Home Assistant, VS Code and Obsidian are not installed in this environment, so
their code cannot be imported. These tests instead guarantee that:

- every integration Python file parses;
- every JSON manifest is valid and has the fields the host application needs;
- every JavaScript entry point passes ``node --check`` when Node is available.

That is a lower bar than running the integration, but it catches the failures
that actually happen in a repository: a typo, a trailing comma, a renamed key.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS = ROOT / "integrations"


def _python_files() -> list[Path]:
    return sorted(INTEGRATIONS.rglob("*.py"))


def _json_files() -> list[Path]:
    return sorted(INTEGRATIONS.rglob("*.json"))


def test_integrations_directory_exists() -> None:
    assert INTEGRATIONS.is_dir()


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_python_files_parse(path: Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


@pytest.mark.parametrize("path", _json_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_json_files_are_valid(path: Path) -> None:
    json.loads(path.read_text(encoding="utf-8"))


class TestHomeAssistant:
    def _component(self) -> Path:
        return INTEGRATIONS / "homeassistant" / "custom_components" / "voicevision"

    def test_manifest(self) -> None:
        manifest = json.loads((self._component() / "manifest.json").read_text())
        assert manifest["domain"] == "voicevision"
        assert manifest["config_flow"] is True
        assert "version" in manifest

    def test_required_files_exist(self) -> None:
        for name in (
            "__init__.py",
            "config_flow.py",
            "const.py",
            "services.yaml",
            "strings.json",
        ):
            assert (self._component() / name).is_file(), name

    def test_services_declared(self) -> None:
        text = (self._component() / "services.yaml").read_text()
        for service in ("converse", "transcribe", "describe"):
            assert f"{service}:" in text

    def test_service_registration_matches_constants(self) -> None:
        init = (self._component() / "__init__.py").read_text()
        for service in ("SERVICE_CONVERSE", "SERVICE_TRANSCRIBE", "SERVICE_DESCRIBE"):
            assert service in init

    def test_strings_are_valid(self) -> None:
        strings = json.loads((self._component() / "strings.json").read_text())
        assert strings["config"]["step"]["user"]["data"]["base_url"]


class TestVSCode:
    def _root(self) -> Path:
        return INTEGRATIONS / "vscode"

    def test_manifest(self) -> None:
        manifest = json.loads((self._root() / "package.json").read_text())
        assert manifest["main"] == "./extension.js"
        assert manifest["engines"]["vscode"]

    def test_commands_are_declared(self) -> None:
        manifest = json.loads((self._root() / "package.json").read_text())
        commands = {
            entry["command"] for entry in manifest["contributes"]["commands"]
        }
        assert commands == {
            "voicevision.dictate",
            "voicevision.transcribeFile",
            "voicevision.ask",
        }

    def test_extension_registers_declared_commands(self) -> None:
        source = (self._root() / "extension.js").read_text()
        for command in (
            "voicevision.dictate",
            "voicevision.transcribeFile",
            "voicevision.ask",
        ):
            assert command in source

    def test_configuration_keys(self) -> None:
        manifest = json.loads((self._root() / "package.json").read_text())
        properties = manifest["contributes"]["configuration"]["properties"]
        for key in (
            "voicevision.serverUrl",
            "voicevision.token",
            "voicevision.language",
            "voicevision.listenCommand",
            "voicevision.listenArgs",
            "voicevision.maxTokens",
        ):
            assert key in properties, key

    def test_readme_exists(self) -> None:
        assert (self._root() / "README.md").is_file()


class TestJavaScript:
    @pytest.mark.parametrize(
        "path",
        sorted(INTEGRATIONS.rglob("*.js")),
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_node_check(self, path: Path) -> None:
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not installed")
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
