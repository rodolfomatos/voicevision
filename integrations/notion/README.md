# voicevision → Notion

Export a transcript to a Notion page. Transcription stays local; only the
finished text is sent to Notion, and only when you run this command.

This is the one integration in the repository that contacts a cloud service.
It is opt-in and does not change the offline behaviour of the library.

## Requirements

- `voicevision` installed (the script imports `voicevision.client`)
- A running `voicevision-server` if you use `--audio`
- A Notion internal integration token with access to the target page/database

```bash
export NOTION_TOKEN=secret_...
```

Create an integration at <https://www.notion.so/my-integrations> and share the
target page or database with it.

## Usage

```bash
# Transcribe locally, then create a page under a parent page
python voicevision_notion.py \
  --audio /home/you/note.wav \
  --page-id 0123456789abcdef \
  --title "Standup notes" \
  --language pt

# Export an existing transcript into a database row
python voicevision_notion.py \
  --text-file transcript.txt \
  --database-id 0123456789abcdef \
  --title "Meeting 2026-11-09" \
  --title-property Name

# Inspect the payload without sending anything
python voicevision_notion.py --text-file transcript.txt --page-id abc --dry-run
```

## Options

| Option | Meaning |
|--------|---------|
| `--audio FILE` | WAV to transcribe via the local server |
| `--text-file FILE` | Existing UTF-8 transcript |
| `--page-id ID` | Create the page under a page |
| `--database-id ID` | Create a row in a database |
| `--title TEXT` | Page title (default `voicevision transcript`) |
| `--title-property NAME` | Title column; defaults to `title` for a page and `Name` for a database |
| `--language CODE` | STT language for `--audio` |
| `--server-url URL` | Local server (default `http://127.0.0.1:8765`) |
| `--server-token TOKEN` | Bearer token for the local server |
| `--dry-run` | Print the JSON payload and exit |

## How the text is split

Notion caps each rich-text block at 2000 characters. `split_text` prefers a
newline, then a space, then a hard cut, so paragraphs stay readable.

## Exit codes

- `0` — page created (or `--dry-run` printed the payload)
- `1` — local transcription failed, `NOTION_TOKEN` is missing, or Notion
  returned an error. The error message never includes the token.
