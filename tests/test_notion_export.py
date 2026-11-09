"""Tests for the Notion export helper.

The module lives outside the package, so it is loaded from its path. Only pure
helpers and the request/response handling are exercised; no network call is
made.
"""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "notion"
    / "voicevision_notion.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("voicevision_notion", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notion = _load()


class TestSplitText:
    def test_empty_returns_no_blocks(self) -> None:
        assert notion.split_text("") == []
        assert notion.split_text("   \n  ") == []

    def test_short_text_is_one_block(self) -> None:
        assert notion.split_text("hello") == ["hello"]

    def test_splits_on_newline(self) -> None:
        text = "first line\nsecond line\nthird line"
        assert notion.split_text(text, limit=15) == ["first line", "second line", "third line"]

    def test_splits_on_space_when_no_newline(self) -> None:
        chunks = notion.split_text("alpha beta gamma delta", limit=12)
        assert all(len(chunk) <= 12 for chunk in chunks)
        assert " ".join(chunks) == "alpha beta gamma delta"

    def test_hard_cut_without_boundaries(self) -> None:
        chunks = notion.split_text("x" * 25, limit=10)
        assert chunks == ["x" * 10, "x" * 10, "x" * 5]

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            notion.split_text("hello", limit=0)

    def test_every_chunk_respects_limit(self) -> None:
        text = " ".join(["word"] * 500)
        chunks = notion.split_text(text, limit=50)
        assert all(len(chunk) <= 50 for chunk in chunks)


class TestBuildPagePayload:
    def test_page_parent_uses_title_property(self) -> None:
        payload = notion.build_page_payload(
            "My note",
            "hello world",
            {"page_id": "abc"},
        )
        assert payload["parent"] == {"page_id": "abc"}
        assert payload["properties"]["title"]["title"][0]["text"]["content"] == "My note"
        assert len(payload["children"]) == 1
        assert payload["children"][0]["type"] == "paragraph"

    def test_database_parent_uses_custom_title_property(self) -> None:
        payload = notion.build_page_payload(
            "Row",
            "text",
            {"database_id": "db"},
            title_property="Name",
        )
        assert payload["parent"] == {"database_id": "db"}
        assert "Name" in payload["properties"]

    def test_long_transcript_produces_multiple_blocks(self) -> None:
        payload = notion.build_page_payload(
            "T",
            "a" * 25,
            {"page_id": "abc"},
            limit=10,
        )
        assert len(payload["children"]) == 3

    def test_empty_transcript_produces_no_children(self) -> None:
        payload = notion.build_page_payload("T", "  ", {"page_id": "abc"})
        assert payload["children"] == []


class TestCreatePage:
    def test_success_returns_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"url": "https://notion.so/page"}).encode()

        captured: dict[str, Any] = {}

        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            captured["auth"] = request.get_header("Authorization")
            captured["body"] = json.loads(request.data)
            return FakeResponse()

        monkeypatch.setattr(
            "urllib.request.urlopen",
            fake_urlopen,
        )
        result = notion.create_page({"parent": {"page_id": "abc"}}, "secret")
        assert result["url"] == "https://notion.so/page"
        assert captured["auth"] == "Bearer secret"

    def test_http_error_is_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_urlopen(request: Any, timeout: float) -> Any:
            raise urllib.error.HTTPError(
                "https://api.notion.com/v1/pages",
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"message": "bad parent"}'),
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(notion.VoiceVisionClientError, match="Notion API error 400"):
            notion.create_page({}, "secret")

    def test_url_error_is_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_urlopen(request: Any, timeout: float) -> Any:
            raise urllib.error.URLError("no dns")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(notion.VoiceVisionClientError, match="cannot reach Notion"):
            notion.create_page({}, "secret")

    def test_invalid_json_is_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b"{not json"

        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *_args, **_kwargs: FakeResponse(),
        )
        with pytest.raises(notion.VoiceVisionClientError, match="invalid JSON"):
            notion.create_page({}, "secret")

    def test_non_object_json_is_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b"[]"

        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *_args, **_kwargs: FakeResponse(),
        )
        with pytest.raises(notion.VoiceVisionClientError, match="non-object"):
            notion.create_page({}, "secret")


class TestTranscriptSource:
    def test_text_file(self, tmp_path: Path) -> None:
        path = tmp_path / "transcript.txt"
        path.write_text("already transcribed", encoding="utf-8")
        args = notion._parser().parse_args(["--text-file", str(path), "--page-id", "abc"])
        assert notion.transcript_from_args(args) == "already transcribed"

    def test_audio_uses_local_client(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio = tmp_path / "note.wav"
        audio.write_bytes(b"RIFFfake")
        calls: dict[str, Any] = {}

        class FakeClient:
            def __init__(self, base_url: str, token: str) -> None:
                calls["base_url"] = base_url
                calls["token"] = token

            def transcribe(self, data: bytes, language: str | None = None) -> dict[str, Any]:
                calls["language"] = language
                return {"transcript": "from server"}

        monkeypatch.setattr(notion, "VoiceVisionClient", FakeClient)
        args = notion._parser().parse_args(
            ["--audio", str(audio), "--page-id", "abc", "--language", "pt"]
        )
        assert notion.transcript_from_args(args) == "from server"
        assert calls["language"] == "pt"

    def test_missing_transcript_is_an_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio = tmp_path / "note.wav"
        audio.write_bytes(b"RIFFfake")

        class FakeClient:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            def transcribe(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {}

        monkeypatch.setattr(notion, "VoiceVisionClient", FakeClient)
        args = notion._parser().parse_args(["--audio", str(audio), "--page-id", "abc"])
        with pytest.raises(notion.VoiceVisionClientError, match="transcript"):
            notion.transcript_from_args(args)


class TestMain:
    def test_dry_run_prints_payload(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = tmp_path / "t.txt"
        path.write_text("hello", encoding="utf-8")
        code = notion.main(["--text-file", str(path), "--page-id", "abc", "--dry-run"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["parent"] == {"page_id": "abc"}

    def test_missing_token_returns_1(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        path = tmp_path / "t.txt"
        path.write_text("hello", encoding="utf-8")
        code = notion.main(["--text-file", str(path), "--page-id", "abc"])
        assert code == 1
        assert "NOTION_TOKEN" in capsys.readouterr().err

    def test_success_prints_url(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("NOTION_TOKEN", "secret")
        monkeypatch.setattr(
            notion,
            "create_page",
            lambda _payload, _token: {"url": "https://notion.so/page"},
        )
        path = tmp_path / "t.txt"
        path.write_text("hello", encoding="utf-8")
        code = notion.main(["--text-file", str(path), "--page-id", "abc"])
        assert code == 0
        assert capsys.readouterr().out.strip() == "https://notion.so/page"

    def test_local_failure_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = notion.main(
            ["--text-file", str(tmp_path / "missing.txt"), "--page-id", "abc"]
        )
        assert code == 1
        assert "error:" in capsys.readouterr().err

    def test_notion_failure_returns_1(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("NOTION_TOKEN", "secret")

        def fail(payload: Any, token: str) -> Any:
            raise notion.VoiceVisionClientError("Notion API error 400: bad")

        monkeypatch.setattr(notion, "create_page", fail)
        path = tmp_path / "t.txt"
        path.write_text("hello", encoding="utf-8")
        code = notion.main(["--text-file", str(path), "--page-id", "abc"])
        assert code == 1
        assert "Notion API error 400" in capsys.readouterr().err
