#!/usr/bin/env python3
"""Perform portable static validation of the local integration repository."""

from __future__ import annotations

import compileall
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INTEGRATION = ROOT / "custom_components" / "solar_irrigation"


def main() -> int:
    """Validate required files, JSON documents, and Python syntax."""
    required = [
        ROOT / "hacs.json",
        ROOT / "README.md",
        INTEGRATION / "__init__.py",
        INTEGRATION / "manifest.json",
        INTEGRATION / "strings.json",
        INTEGRATION / "translations" / "en.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("Missing required files:")
        print("\n".join(missing))
        return 1
    for path in (
        ROOT / "hacs.json",
        INTEGRATION / "manifest.json",
        INTEGRATION / "strings.json",
        INTEGRATION / "translations" / "en.json",
    ):
        json.loads(path.read_text(encoding="utf-8"))
    if not compileall.compile_dir(INTEGRATION, quiet=1):
        return 1
    print("Static integration validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
