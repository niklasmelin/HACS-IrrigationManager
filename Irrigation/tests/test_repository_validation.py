"""Local repository validation for the Solar Irrigation integration."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
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
    """Load a JSON object with useful assertion messages."""
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


def _validator_output(result: subprocess.CompletedProcess[str]) -> str:
    """Return combined validator output."""
    return "\n".join(
        part
        for part in (
            result.stdout.strip(),
            result.stderr.strip(),
        )
        if part
    )


def _prepare_hassfest_workspace(destination: Path) -> None:
    """Create a clean Hassfest workspace without local virtual environments."""
    source_integration = CUSTOM_COMPONENTS / "solar_irrigation"
    destination_integration = (
        destination
        / "custom_components"
        / "solar_irrigation"
    )

    assert source_integration.is_dir(), (
        f"Integration directory is missing: {source_integration}"
    )

    shutil.copytree(
        source_integration,
        destination_integration,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".pytest_cache",
        ),
    )


@pytest.fixture(scope="session")
def integration_dir() -> Path:
    """Return the single integration directory."""
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
        "Expected exactly one integration under custom_components/. "
        f"Found: {[path.name for path in directories]}"
    )

    return directories[0]


@pytest.mark.repository_validation
def test_repository_layout(integration_dir: Path) -> None:
    """Verify the local repository layout."""
    required_files = [
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "hacs.json",
        integration_dir / "__init__.py",
        integration_dir / "manifest.json",
    ]

    missing = [str(path) for path in required_files if not path.is_file()]

    assert not missing, "Required files are missing:\n" + "\n".join(missing)
    assert (REPOSITORY_ROOT / "README.md").read_text(
        encoding="utf-8"
    ).strip(), "README.md is empty"


@pytest.mark.repository_validation
def test_hacs_metadata(integration_dir: Path) -> None:
    """Validate locally testable HACS metadata."""
    del integration_dir

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

    assert hacs.get("content_in_root") is not True, (
        "content_in_root must not be true when the integration is under "
        "custom_components/"
    )

    if hacs.get("zip_release"):
        assert hacs.get("filename"), (
            "filename is required when zip_release is enabled"
        )


@pytest.mark.repository_validation
def test_manifest_metadata(integration_dir: Path) -> None:
    """Validate required manifest fields."""
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


@pytest.mark.repository_validation
def test_brand_icon(integration_dir: Path) -> None:
    """Verify the local brand icon."""
    icon = integration_dir / "brand" / "icon.png"

    assert icon.is_file(), f"Missing brand icon: {icon}"

    data = icon.read_bytes()

    assert data.startswith(b"\x89PNG\r\n\x1a\n"), (
        f"{icon} is not a valid PNG file"
    )
    assert len(data) > 100, f"{icon} appears empty or corrupt"


@pytest.mark.repository_validation
def test_python_files_parse(integration_dir: Path) -> None:
    """Verify that integration Python files have valid syntax."""
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
def test_hassfest_validation() -> None:
    """Run Hassfest against a clean, isolated integration workspace."""
    docker = shutil.which("docker")
    require_hassfest = os.environ.get("REQUIRE_HASSFEST") == "1"

    if docker is None:
        message = "Docker is required to run Hassfest but was not found."

        if require_hassfest:
            pytest.fail(message)

        pytest.skip(message)

    daemon = subprocess.run(
        [docker, "info"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if daemon.returncode != 0:
        message = (
            "Docker daemon is unavailable.\n"
            f"{_validator_output(daemon)}"
        )

        if require_hassfest:
            pytest.fail(message)

        pytest.skip(message)

    image = os.environ.get(
        "HASSFEST_IMAGE",
        "ghcr.io/home-assistant/hassfest",
    )

    with tempfile.TemporaryDirectory(
        prefix="solar-irrigation-hassfest-"
    ) as temporary_directory:
        workspace = Path(temporary_directory)
        _prepare_hassfest_workspace(workspace)

        result = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "--volume",
                f"{workspace}:/github/workspace:ro",
                image,
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

    assert result.returncode == 0, (
        "Hassfest validation failed.\n\n"
        f"{_validator_output(result) or 'Hassfest produced no output.'}"
    )