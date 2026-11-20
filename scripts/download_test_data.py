#!/usr/bin/env python3
"""Download test data for benchmarks.

Downloads:
- Common Voice dataset (subset for pt/en)
- CHiME noise corpus (subset)
- Synthetic test audio generation
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import urllib.request
from pathlib import Path


def download_file(url: str, dest: Path, desc: str = "") -> None:
    """Download a file with progress bar."""
    print(f"Downloading {desc}...")
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  Saved to {dest}")
    except Exception as e:
        print(f"  Failed to download {desc}: {e}")
        raise


def download_common_voice(output_dir: Path, languages: list[str] = ["en", "pt"]) -> None:
    """Download Common Voice dataset subsets."""
    base_url = "https://common-voice.s3.amazonaws.com"
    
    for lang in languages:
        print(f"\nDownloading Common Voice {lang}...")
        # Download a small subset (dev set)
        url = f"{base_url}/cv-corpus-13.0-2023-06-23/{lang}.tar.gz"
        dest = Path(f"/tmp/cv-{lang}.tar.gz")
        download_file(url, dest, f"Common Voice {lang}")
        
        # Extract
        print(f"  Extracting...")
        with tarfile.open(dest, "r:gz") as tar:
            tar.extractall(Path("/tmp/cv_extract") / lang)
        print(f"  Extracted to /tmp/cv_extract/{lang}")


def download_chime_noise(output_dir: Path) -> None:
    """Download CHiME noise corpus."""
    print("Downloading CHiME noise corpus...")
    url = "https://zenodo.org/record/1113666/files/CHiME3.zip"
    dest = Path("/tmp/CHiME3.zip")
    download_file(url, dest, "CHiME noise")
    
    # Extract
    print("  Extracting...")
    with tarfile.open(dest, "r") as tar:
        tar.extractall("/tmp/chime_noise")
    print("  Extracted to /tmp/chime_noise")


def generate_synthetic_test_data(output_dir: Path, duration_seconds: int = 30) -> None:
    """Generate synthetic test audio for benchmarking."""
    import numpy as np
    
    print(f"Generating {duration_seconds}s of synthetic test audio...")
    
    sample_rate = 16000
    duration = duration_seconds
    samples = duration * 16000
    
    # Generate various test signals
    t = np.arange(samples) / 16000
    
    # Speech-like signal (multiple tones)
    signal1 = 0.3 * np.sin(2 * np.pi * 440 * t)  # A4
    signal2 = 0.2 * np.sin(2 * np.pi * 880 * t)  # A5
    signal3 = 0.1 * np.sin(2 * np.pi * 220 * t)  # A3
    speech_like = signal1 + signal2 + signal3
    
    # Silence
    silence = np.zeros(int(16000 * 2))  # 2 seconds
    
    # Noise
    noise = 0.1 * np.random.randn(samples)
    
    # Save as WAV files
    import wave
    
    def save_wav(path: Path, data: np.ndarray, sr: int = 16000):
        data_int16 = (data * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(data_int16.tobytes())
    
    output_dir = Path("/tmp/voicevision_test_audio")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    save_wav(output_dir / "speech_like.wav", speech_like)
    save_wav(output_dir / "silence.wav", silence)
    save_wav(output_dir / "noise.wav", noise)
    save_wav(output_dir / "mixed.wav", 0.7 * speech_like + 0.3 * noise)
    
    print(f"  Generated test audio in {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download test data for voicevision benchmarks")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/voicevision_test_data"))
    parser.add_argument("--common-voice", action="store_true", help="Download Common Voice dataset")
    parser.add_argument("--chime", action="store_true", help="Download CHiME noise corpus")
    parser.add_argument("--synthetic", action="store_true", help="Generate synthetic test data")
    parser.add_argument("--all", action="store_true", help="Download all test data")
    args = parser.parse_args()

    if args.all:
        args.common_voice = True
        args.chime = True
        args.synthetic = True

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.synthetic:
        generate_synthetic_test_data(output_dir)

    if args.common_voice:
        download_common_voice(output_dir)

    if args.chime:
        download_chime_noise(output_dir)

    print("\nDone! Test data available at:", output_dir)


if __name__ == "__main__":
    import numpy as np
    import wave
    main()