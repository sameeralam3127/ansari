"""The `.ansari/manifest.yaml` a scaffolded repo carries.

The manifest is what lets ANSARI answer two questions later: is this repo behind
the template it came from, and which generated files has a human edited since.
It lives in the repo rather than only in ANSARI's database so that `ansari check`
works offline, and so deleting ANSARI leaves working repos behind.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

MANIFEST_DIR = ".ansari"
MANIFEST_NAME = "manifest.yaml"

_HEADER = """\
# Written by `ansari new`. Tracks which template version this repo came from
# and what was generated, so `ansari check` can detect drift and `ansari sync`
# can upgrade without clobbering hand-edits. Safe to commit; do not hand-edit.
"""


class ManifestError(Exception):
    """A manifest exists but cannot be understood."""


def manifest_path(service_dir: Path) -> Path:
    return service_dir / MANIFEST_DIR / MANIFEST_NAME


def file_digest(path: Path) -> str:
    """Content hash of one generated file, prefixed with its algorithm."""
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


@dataclass(frozen=True)
class Manifest:
    template: str
    version: str
    rendered_at: datetime
    variables: dict[str, str]
    files: dict[str, str]
    """Repo-relative path -> content hash at the moment it was generated."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "version": self.version,
            "rendered_at": self.rendered_at.isoformat(),
            "variables": dict(sorted(self.variables.items())),
            "files": dict(sorted(self.files.items())),
        }

    @classmethod
    def from_dict(cls, raw: object) -> "Manifest":
        if not isinstance(raw, dict):
            raise ManifestError("manifest is not a YAML mapping")

        template = raw.get("template")
        version = raw.get("version")
        if not isinstance(template, str) or not isinstance(version, str):
            raise ManifestError("manifest is missing a string 'template' or 'version'")

        return cls(
            template=template,
            version=version,
            rendered_at=_parse_timestamp(raw.get("rendered_at")),
            variables=_str_mapping(raw.get("variables"), "variables"),
            files=_str_mapping(raw.get("files"), "files"),
        )


def _parse_timestamp(value: object) -> datetime:
    # PyYAML resolves unquoted ISO-8601 scalars to datetime itself, so accept both.
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ManifestError(f"'rendered_at' is not a valid timestamp: {value!r}") from exc
    raise ManifestError("manifest is missing 'rendered_at'")


def _str_mapping(value: object, field: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"'{field}' is not a mapping")
    return {str(k): str(v) for k, v in value.items()}


def write_manifest(service_dir: Path, manifest: Manifest) -> Path:
    path = manifest_path(service_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(manifest.to_dict(), sort_keys=False, default_flow_style=False)
    path.write_text(_HEADER + body)
    return path


def read_manifest(service_dir: Path) -> Manifest | None:
    """Load the manifest, or None if this repo was not scaffolded by ANSARI.

    A malformed manifest raises rather than returning None: "no manifest" and
    "a manifest I can't read" are different situations and deserve different
    messages.
    """
    path = manifest_path(service_dir)
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path} is not valid YAML: {exc}") from exc
    return Manifest.from_dict(raw)


def build_manifest(
    template: str, version: str, variables: dict[str, str], service_dir: Path, paths: list[str]
) -> Manifest:
    """Hash every generated file and record it against the template it came from."""
    return Manifest(
        template=template,
        version=version,
        rendered_at=datetime.now(UTC),
        variables=variables,
        files={path: file_digest(service_dir / path) for path in sorted(paths)},
    )
