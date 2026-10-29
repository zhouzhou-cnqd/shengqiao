"""Fail fast when private data, weights, secrets, or local paths enter the repo."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

BLOCKED_DIRS = {
    "data",
    "dsr_data",
    "recordings",
    "audio",
    "features",
    "weights",
    "checkpoints",
    "outputs",
    "models",
    "random_pool",
    "original",
    "reconstructed",
    "clear",
    "personalized",
}

BLOCKED_SUFFIXES = {
    ".pt", ".pth", ".ckpt", ".onnx", ".safetensors",
    ".parquet", ".npy", ".npz",
    ".wav", ".flac", ".mp3", ".m4a",
    ".tar", ".gz", ".zip",
}

TEXT_SUFFIXES = {
    ".py", ".ps1", ".js", ".ts", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt",
}

SENSITIVE_PATTERNS = {
    "private absolute Linux path": re.compile(r"/mnt/(?:data|home)/", re.I),
    "private Windows user path": re.compile(r"[A-Z]:[\\/]Users[\\/][^\\/\s]+", re.I),
    "private IPv4 address": re.compile(r"\b(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b"),
    "possible access token": re.compile(r"(?:ghp_|github_pat_|sk-)[A-Za-z0-9_\-]{16,}"),
}


def main() -> int:
    problems: list[str] = []

    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts:
            continue

        if path.is_dir():
            if path.name.lower() in BLOCKED_DIRS:
                problems.append(f"blocked directory: {relative}")
            continue

        if path.suffix.lower() in BLOCKED_SUFFIXES or path.name.lower().endswith(".tar.gz"):
            problems.append(f"blocked file type: {relative}")

        if path.name == Path(__file__).name or path.suffix.lower() not in TEXT_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"non-UTF-8 text file: {relative}")
            continue

        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                problems.append(f"{label}: {relative}")

    if problems:
        print("Public release check failed:")
        for problem in sorted(set(problems)):
            print(f"  - {problem}")
        return 1

    print("Public release check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

