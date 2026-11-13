#!/usr/bin/env python3
"""
download-models.py — Download all required models for voicevision
Uses huggingface_hub for reliable downloads with resume support.
"""

import os
import sys
import argparse
from pathlib import Path
from huggingface_hub import hf_hub_download

MODELS_DIR = Path("/models")

MODELS = {
    "whisper-base": {
        "repo_id": "ggerganov/whisper.cpp",
        "filename": "ggml-base.bin",
        "description": "whisper.cpp STT model (base, ~142 MB)",
    },
    "qwen3-1.7b-q8": {
        "repo_id": "Qwen/Qwen3-1.7B-GGUF",
        "filename": "Qwen3-1.7B-Q8_0.gguf",
        "description": "Qwen3 1.7B LLM (Q8_0, ~1.7 GB)",
    },
    "piper-en-us-lessac-medium": {
        "repo_id": "rhasspy/piper-voices",
        "filename": "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "description": "Piper TTS voice (en_US lessac medium, ~63 MB)",
    },
    "piper-en-us-lessac-medium-config": {
        "repo_id": "rhasspy/piper-voices",
        "filename": "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "description": "Piper TTS voice config (en_US lessac medium, ~5 KB)",
    },
    "moondream-text": {
        "repo_id": "moondream/moondream2-gguf",
        "filename": "moondream2-text-model-f16.gguf",
        "description": "Moondream vision text model (f16, ~2.8 GB)",
    },
    "moondream-mmproj": {
        "repo_id": "moondream/moondream2-gguf",
        "filename": "moondream2-mmproj-f16.gguf",
        "description": "Moondream vision projection model (f16, ~910 MB)",
    },
}

MODEL_GROUPS = {
    "all": list(MODELS.keys()),
    "stt": ["whisper-base"],
    "llm": ["qwen3-1.7b-q8"],
    "tts": ["piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config"],
    "vision": ["moondream-text", "moondream-mmproj"],
    "voice-loop": ["whisper-base", "qwen3-1.7b-q8", "piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config"],
    "full": ["whisper-base", "qwen3-1.7b-q8", "piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config", "moondream-text", "moondream-mmproj"],
}


def download_model(key: str, models_dir: Path, force: bool = False):
    """Download a single model. Returns True if downloaded, False if skipped, None if failed."""
    if key not in MODELS:
        print(f"  ❌ Unknown model: {key}")
        return None

    info = MODELS[key]
    local_path = models_dir / info["filename"]

    # Ensure parent directory exists
    local_path.parent.mkdir(parents=True, exist_ok=True)

    if local_path.exists() and not force:
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"  ⏭  {info['description']} — already exists ({size_mb:.1f} MB)")
        return False

    print(f"  ⬇  Downloading {info['description']}...")
    try:
        hf_hub_download(
            repo_id=info["repo_id"],
            filename=info["filename"],
            local_dir=models_dir,
            local_dir_use_symlinks=False,
            force_download=force,
        )
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"  ✅  {info['description']} downloaded ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"  ❌  Failed to download {key}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Download voicevision models")
    parser.add_argument(
        "models",
        nargs="*",
        default=["voice-loop"],
        help="Models to download (default: voice-loop). Options: " + ", ".join(MODEL_GROUPS.keys()) + " or individual model keys: " + ", ".join(MODELS.keys()),
    )
    parser.add_argument("--models-dir", default="/models", help="Directory to save models (default: /models)")
    parser.add_argument("--force", action="store_true", help="Force re-download even if file exists")
    parser.add_argument("--list", action="store_true", help="List available models and groups")
    args = parser.parse_args()

    if args.list:
        print("Available model groups:")
        for group, keys in MODEL_GROUPS.items():
            print(f"  {group}: {', '.join(keys)}")
        print("\nAvailable individual models:")
        for key, info in MODELS.items():
            print(f"  {key}: {info['description']}")
        return 0

    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Resolve model keys from groups
    to_download = []
    for arg in args.models:
        if arg in MODEL_GROUPS:
            to_download.extend(MODEL_GROUPS[arg])
        elif arg in MODELS:
            to_download.append(arg)
        else:
            print(f"  ⚠️  Unknown model/group: {arg}", file=sys.stderr)

    # Deduplicate while preserving order
    seen = set()
    to_download = [x for x in to_download if not (x in seen or seen.add(x))]

    print(f"Downloading {len(to_download)} model(s) to {models_dir}...")
    print()

    downloaded = 0
    skipped = 0
    failed = 0
    for key in to_download:
        result = download_model(key, Path(args.models_dir), args.force)
        if result is True:
            downloaded += 1
        elif result is False:
            skipped += 1
        else:
            failed += 1

    print()
    print(f"Done: {downloaded} downloaded, {skipped} skipped, {failed} failed")
    if failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())