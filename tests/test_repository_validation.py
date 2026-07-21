"""Local repository validation for a Home Assistant custom integration."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = REPOSITORY_ROOT / "custom_components"

DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

HACS_ALLOWED_KEYS = {
    "name",
    "content_in_root",
    "zip_release",
    "filename",
    "hide_default_branch",
    "country",
    "homeassistant",
    "hacs",
    "persistent_directory",
}

HACS_BOOLEAN_KEYS = {
    "content_in_root",
    "zip_release",
    "hide_default_branch",
}

HACS_STRING_KEYS = {
    "name",
    "filename",
    "homeassistant",
    "hacs",
    "persistent_directory",
}

REQUIRED_MANIFEST_KEYS = {
    "domain",
    "documentation",
    "issue_tracker",
    "codeowners",
    "name",
    "version",
}


def _load_json(path: Path) -> dict:
    """Load a JSON object and provide a useful assertion message."""
    assert path.is_file(), f"Required file is missing: {path}"

    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        pytest.fail(f"Invalid JSON in {path}: {err}")

    assert isinstance(content, dict), f"{path} must contain a JSON object"
    return content


def _is_web_url(value: object) -> bool:
    """Return whether a value is an absolute HTTP or HTTPS URL."""
    if not isinstance(value, str):
        return False

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@pytest.fixture(scope="session")
def integration_dir() -> Path:
    """Return the single integration directory in the repository."""
    assert CUSTOM_COMPONENTS.is_dir(), (
        f"Missing integration directory: {CUSTOM_COMPONENTS}"
    )

    directories = sorted(
        path
        for path in CUSTOM_COMPONENTS.iterdir()
        if path.is_dir()
        and path.name != "__pycache__"
        and not path.name.startswith(".")
    )

    assert len(directories) == 1, (
        "A HACS integration repository must contain exactly one directory "
        f"under custom_components/. Found: {[path.name for path in directories]}"
    )

    return directories[0]


@pytest.mark.repository_validation
def test_repository_layout(integration_dir: Path) -> None:
    """Verify the local repository layout expected by HACS."""
    required_files = [
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "hacs.json",
        integration_dir / "__init__.py",
        integration_dir / "manifest.json",
    ]

    missing = [str(path) for path in required_files if not path.is_file()]

    assert not missing, "Required files are missing:\n" + "\n".join(missing)

    readme = REPOSITORY_ROOT / "README.md"
    assert readme.read_text(encoding="utf-8").strip(), "README.md is empty"


@pytest.mark.repository_validation
def test_hacs_metadata(integration_dir: Path) -> None:
    """Validate the locally testable parts of hacs.json."""
    hacs = _load_json(REPOSITORY_ROOT / "hacs.json")

    unsupported_keys = set(hacs) - HACS_ALLOWED_KEYS
    assert not unsupported_keys, (
        f"Unsupported hacs.json keys: {sorted(unsupported_keys)}"
    )

    assert isinstance(hacs.get("name"), str)
    assert hacs["name"].strip(), "hacs.json name must not be empty"

    for key in HACS_BOOLEAN_KEYS:
        if key in hacs:
            assert isinstance(hacs[key], bool), f"{key} must be a boolean"

    for key in HACS_STRING_KEYS:
        if key in hacs:
            assert isinstance(hacs[key], str), f"{key} must be a string"
            assert hacs[key].strip(), f"{key} must not be empty"

    # This repository uses the standard custom_components layout.
    assert hacs.get("content_in_root") is not True, (
        "content_in_root must not be true when the integration is located "
        "under custom_components/"
    )

    if hacs.get("zip_release"):
        assert hacs.get("filename"), (
            "filename is required when zip_release is enabled"
        )

    if "persistent_directory" in hacs:
        persistent_directory = Path(hacs["persistent_directory"])

        assert not persistent_directory.is_absolute(), (
            "persistent_directory must be a relative path"
        )
        assert ".." not in persistent_directory.parts, (
            "persistent_directory must remain inside the integration directory"
        )

    if "country" in hacs:
        countries = hacs["country"]
        if isinstance(countries, str):
            countries = [countries]

        assert isinstance(countries, list), (
            "country must be a two-letter code or a list of two-letter codes"
        )
        assert countries, "country must not be an empty list"

        for country in countries:
            assert isinstance(country, str)
            assert re.fullmatch(r"[A-Z]{2}", country), (
                f"Invalid country code: {country!r}"
            )


@pytest.mark.repository_validation
def test_manifest_metadata(integration_dir: Path) -> None:
    """Validate manifest fields required for a HACS integration."""
    manifest = _load_json(integration_dir / "manifest.json")

    missing_keys = REQUIRED_MANIFEST_KEYS - set(manifest)
    assert not missing_keys, (
        f"manifest.json is missing keys: {sorted(missing_keys)}"
    )

    domain = manifest["domain"]
    assert isinstance(domain, str)
    assert DOMAIN_PATTERN.fullmatch(domain), f"Invalid domain: {domain!r}"
    assert domain == integration_dir.name, (
        f"Manifest domain {domain!r} must match directory "
        f"{integration_dir.name!r}"
    )

    for key in ("name", "version"):
        assert isinstance(manifest[key], str), f"{key} must be a string"
        assert manifest[key].strip(), f"{key} must not be empty"

    for key in ("documentation", "issue_tracker"):
        assert _is_web_url(manifest[key]), (
            f"{key} must be an absolute HTTP or HTTPS URL"
        )

    codeowners = manifest["codeowners"]
    assert isinstance(codeowners, list), "codeowners must be a list"
    assert codeowners, "codeowners must contain at least one entry"
    assert all(
        isinstance(owner, str) and owner.strip()
        for owner in codeowners
    ), "Every codeowner must be a non-empty string"

    if "config_flow" in manifest:
        assert isinstance(manifest["config_flow"], bool), (
            "config_flow must be a boolean"
        )

    if "requirements" in manifest:
        assert isinstance(manifest["requirements"], list)
        assert all(
            isinstance(requirement, str) and requirement.strip()
            for requirement in manifest["requirements"]
        )


@pytest.mark.repository_validation
def test_brand_icon(integration_dir: Path) -> None:
    """Verify that the integration contains a local brand icon."""
    icon = integration_dir / "brand" / "icon.png"

    assert icon.is_file(), f"Missing brand icon: {icon}"

    data = icon.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), (
        f"{icon} is not a valid PNG file"
    )
    assert len(data) > 100, f"{icon} appears to be empty or corrupt"


@pytest.mark.repository_validation
def test_python_files_parse(integration_dir: Path) -> None:
    """Verify that every integration Python file has valid syntax."""
    python_files = sorted(integration_dir.rglob("*.py"))
    assert python_files, "The integration contains no Python files"

    errors: list[str] = []

    for path in python_files:
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
            )
        except (SyntaxError, UnicodeDecodeError) as err:
            errors.append(f"{path}: {err}")

    assert not errors, "Python source validation failed:\n" + "\n".join(errors)


@pytest.mark.repository_validation
@pytest.mark.hassfest
def test_hassfest_validation(integration_dir: Path) -> None:
    """Run Hassfest from a local Home Assistant Core checkout."""
    core_path_value = os.environ.get("HOME_ASSISTANT_CORE_PATH")

    if not core_path_value:
        message = (
            "HOME_ASSISTANT_CORE_PATH is not set. It must point to a local "
            "Home Assistant Core development directory."
        )

        if os.environ.get("REQUIRE_EXTERNAL_VALIDATORS") == "1":
            pytest.fail(message)

        pytest.skip(message)

    core_path = Path(core_path_value).expanduser().resolve()
    hassfest_module = core_path / "script" / "hassfest" / "__main__.py"

    assert core_path.is_dir(), (
        f"HOME_ASSISTANT_CORE_PATH does not exist: {core_path}"
    )
    assert hassfest_module.is_file(), (
        f"Hassfest was not found under: {core_path}"
    )

    python_executable = os.environ.get("HASSFEST_PYTHON", sys.executable)

    result = subprocess.run(
        [
            python_executable,
            "-m",
            "script.hassfest",
            "--action",
            "validate",
            "--integration-path",
            str(integration_dir),
        ],
        cwd=core_path,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    output = "\n".join(
        section
        for section in (
            result.stdout.strip(),
            result.stderr.strip(),
        )
        if section
    )

    assert result.returncode == 0, (
        "Hassfest validation failed.\n\n"
        f"{output or 'Hassfest produced no output.'}"
    )