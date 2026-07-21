#!/usr/bin/env python3
"""Portable wrapper for the local repository validation tests."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Run local repository checks without requiring Docker."""
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_repository_validation.py",
        "-m",
        "repository_validation and not hassfest",
        "-v",
    ]
    return subprocess.call(command, cwd=REPOSITORY_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
