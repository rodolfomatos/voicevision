"""Export a voicevision transcript to a Notion page.

Inference stays local: the audio is transcribed by the local voicevision
server (or read from a text file), and only the finished text is sent to
Notion. This is the one integration in the repository that contacts a cloud
service, and it is an explicit operator action.

Usage::

    export NOTION_TOKEN=secret_...
    python voicevision_notion.py --audio note.wav --page-id 1234 --title "Standup"
    python voicevision_notion.py --text-file transcript.txt --database-id 5678

The token is read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

from voicevision.client import VoiceVisionClient, VoiceVisionClientError

#: Notion rejects rich-text content above 2000 characters per block.
MAX_BLOCK_CHARS: Final = 2000

NOTION_PAGES_URL: Final = "https://api.notion.com/v1/pages"
NOTION_VERSION: Final = "2022-06-28"


def split_text(text: str, limit: int = MAX_BLOCK_CHARS) -> list[str]:
    """Split *text* into chunks of at most *limit* characters.

    Paragraph/newline boundaries are preferred, then spaces, and only then a
    hard cut. Empty input produces no blocks.
    """
    stripped = text.strip()
    if not stripped:
        return []
    if limit < 1:
        raise ValueError("limit must be positive")

    chunks: list[str] = []
    remaining = stripped
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def build_page_payload(
    title: str,
    transcript: str,
    parent: dict[str, str],
    *,
    title_property: str = "title",
    limit: int = MAX_BLOCK_CHARS,
) -> dict[str, Any]:
    """Build the JSON body for ``POST /v1/pages``.

    *parent* is ``{"page_id": ...}`` or ``{"database_id": ...}``. For a page
    parent the title property is literally ``title``; for a database it is the
    database's title column name (``Name`` by default in Notion templates).
    """
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
            },
        }
        for chunk in split_text(transcript, limit)
    ]
    return {
        "parent": parent,
        "properties": {
            title_property: {
                "title": [{"type": "text", "text": {"content": title}}],
            },
        },
        "children": children,
    }


def transcript_from_args(args: argparse.Namespace) -> str:
    """Return the transcript named by ``--audio`` or ``--text-file``."""
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8")

    client = VoiceVisionClient(
        base_url=args.server_url,
        token=args.server_token,
    )
    result = client.transcribe(
        Path(args.audio).read_bytes(),
        language=args.language or None,
    )
    transcript = result.get("transcript")
    if not isinstance(transcript, str):
        raise VoiceVisionClientError("server did not return a transcript")
    return transcript


def create_page(payload: dict[str, Any], token: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """POST *payload* to the Notion pages endpoint and return the response."""
    request = urllib.request.Request(
        NOTION_PAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceVisionClientError(f"Notion API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise VoiceVisionClientError(f"cannot reach Notion: {exc.reason}") from exc

    try:
        decoded = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VoiceVisionClientError("Notion returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise VoiceVisionClientError("Notion returned a non-object JSON body")
    return decoded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a voicevision transcript to a Notion page.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio", help="WAV file to transcribe locally")
    source.add_argument("--text-file", help="UTF-8 file with an existing transcript")

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--page-id", help="Parent Notion page id")
    target.add_argument("--database-id", help="Parent Notion database id")

    parser.add_argument("--title", default="voicevision transcript")
    parser.add_argument(
        "--title-property",
        default=None,
        help="Title property name (default: title for a page, Name for a database)",
    )
    parser.add_argument("--language", default="", help="STT language for --audio")
    parser.add_argument("--server-url", default="http://127.0.0.1:8765")
    parser.add_argument("--server-token", default="", help="voicevision bearer token")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without contacting Notion",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.page_id:
        parent = {"page_id": args.page_id}
        title_property = args.title_property or "title"
    else:
        parent = {"database_id": args.database_id}
        title_property = args.title_property or "Name"

    try:
        transcript = transcript_from_args(args)
    except (OSError, VoiceVisionClientError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = build_page_payload(
        args.title,
        transcript,
        parent,
        title_property=title_property,
    )

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("error: NOTION_TOKEN is not set", file=sys.stderr)
        return 1

    try:
        created = create_page(payload, token)
    except VoiceVisionClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    url = created.get("url", "")
    print(url if url else json.dumps(created, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
