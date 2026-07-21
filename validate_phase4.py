#!/usr/bin/env python3
"""Compatibility wrapper for the complete pytest test command.

Prefer running ``make test``. This script remains only for existing local
workflows and does not contain separate validation logic.
"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Run the complete test suite with mandatory Docker-based Hassfest."""
    environment = os.environ.copy()
    environment.setdefault("REQUIRE_HASSFEST", "1")

    command = [sys.executable, "-m", "pytest", "-v"]
    return subprocess.call(command, cwd=REPOSITORY_ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
