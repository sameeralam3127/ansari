"""The `.ansari/manifest.yaml` a scaffolded repo carries.

The manifest is what lets ANSARI answer two questions later: is this repo behind
the templates it came from, and which generated files has a human edited since.
It lives in the repo rather than only in ANSARI's database so that `ansari check`
works offline, and so deleting ANSARI leaves working repos behind.

A repo may carry more than one template — a service that also has scaling config
attached is one repo with two provenances — so the record is a list of
`TemplateRecord` entries rather than a single scalar template name. Manifests
written before that change have no `schema` key and a scalar `template`/`version`
pair; they are read as a one-entry list and are never rewritten on read, so a
repo scaffolded by an older ANSARI keeps working untouched.
"""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

MANIFEST_DIR = ".ansari"
MANIFEST_NAME = "manifest.yaml"

SCHEMA_VERSION = 2
"""Shape of the document this build writes. An int, not a semver string: it
versions a document shape, and shapes change discretely."""

LEGACY_SCHEMA_VERSION = 1
"""The implicit version of a manifest with no `schema` key."""

VariableValue = str | int | bool | list[str]
"""What a template variable may hold in a schema-2 manifest. Terraform wants
provider lists and Ansible wants a platforms matrix, so `str` alone is too
narrow. Nested mappings are deliberately excluded — every level of nesting is a
level a future three-way merge would have to reason about."""

_HEADER = """\
# Written by `ansari new`. Tracks which template versions this repo came from
# and what was generated, so `ansari check` can detect drift and `ansari sync`
# can upgrade without clobbering hand-edits. Safe to commit; do not hand-edit.
"""


class ManifestError(Exception):
    """A manifest exists but cannot be understood."""


class ManifestTooNewError(ManifestError):
    """The manifest declares a schema this build does not know how to read.

    Distinct from a malformed manifest: nothing is wrong with the file, this
    ANSARI is simply older than the one that wrote it. Misreading it as a shape
    we do understand would silently drop whatever the newer schema added.
    """


class UnresolvedTemplateError(ManifestError):
    """A write was attempted onto a manifest carrying an unreadable entry.

    Distinct again from both a malformed and a too-new manifest: the document
    parses, but one of its entries names a template this build ships no
    descriptor for, so its file ownership cannot be established.
    """


def manifest_path(repo_dir: Path) -> Path:
    return repo_dir / MANIFEST_DIR / MANIFEST_NAME


def file_digest(path: Path) -> str:
    """Content hash of one generated file, prefixed with its algorithm."""
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


@dataclass(frozen=True)
class TemplateRecord:
    """One template attached to a repo, and what it generated."""

    template: str
    version: str
    rendered_at: datetime
    variables: dict[str, VariableValue]
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
    def from_dict(cls, raw: object, *, coerce_variables: bool) -> "TemplateRecord":
        """Parse one entry.

        `coerce_variables` preserves schema-1 behaviour exactly: those manifests
        were written when every variable was stringified on the way in, so they
        are stringified on the way out too. Widening the type must not change how
        a single already-scaffolded repo is interpreted.
        """
        if not isinstance(raw, dict):
            raise ManifestError("template entry is not a mapping")

        template = raw.get("template")
        version = raw.get("version")
        if not isinstance(template, str) or not isinstance(version, str):
            raise ManifestError("template entry is missing a string 'template' or 'version'")

        return cls(
            template=template,
            version=version,
            rendered_at=_parse_timestamp(raw.get("rendered_at")),
            variables=_variables(raw.get("variables"), coerce=coerce_variables),
            files=_str_mapping(raw.get("files"), "files"),
        )


@dataclass(frozen=True)
class Manifest:
    """Everything a repo records about where it came from."""

    schema: int
    templates: list[TemplateRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "templates": [record.to_dict() for record in self.templates],
        }

    def record_for(self, template: str) -> TemplateRecord | None:
        return next((r for r in self.templates if r.template == template), None)

    def claimed_paths(self) -> dict[str, str]:
        """Every generated path in the repo, mapped to the template that owns it."""
        return {path: record.template for record in self.templates for path in record.files}

    @classmethod
    def from_dict(cls, raw: object) -> "Manifest":
        if not isinstance(raw, dict):
            raise ManifestError("manifest is not a YAML mapping")

        schema = _parse_schema(raw.get("schema"))

        if schema == LEGACY_SCHEMA_VERSION:
            # A schema-1 manifest is the whole document as one entry: the scalar
            # `template`/`version` pair with its variables and files beside them.
            records = [TemplateRecord.from_dict(raw, coerce_variables=True)]
        else:
            entries = raw.get("templates")
            if not isinstance(entries, list) or not entries:
                raise ManifestError("manifest needs a non-empty 'templates' list")
            records = [TemplateRecord.from_dict(e, coerce_variables=False) for e in entries]

        manifest = cls(schema=schema, templates=records)
        # Re-checked on read, not only enforced on write: a hand-merged manifest
        # must not be able to leave two templates owning one file silently.
        conflicts = overlapping_paths(records)
        if conflicts:
            raise ManifestError(
                f"manifest has files claimed by more than one template: {conflicts}"
            )
        return manifest


def overlapping_paths(records: Iterable[TemplateRecord]) -> dict[str, list[str]]:
    """Paths claimed by more than one template, mapped to their claimants.

    Two templates owning one file makes drift undefined and would give a future
    `sync` two owners for the same merge, so it is refused rather than resolved
    by precedence.
    """
    owners: dict[str, list[str]] = {}
    for record in records:
        for path in record.files:
            owners.setdefault(path, []).append(record.template)
    return {path: names for path, names in sorted(owners.items()) if len(names) > 1}


def _parse_schema(value: object) -> int:
    if value is None:
        return LEGACY_SCHEMA_VERSION
    # bool is an int subclass; `schema: true` is a malformed document, not 1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ManifestError(f"'schema' is not an integer: {value!r}")
    if value < LEGACY_SCHEMA_VERSION:
        raise ManifestError(f"'schema' is not a known version: {value!r}")
    if value > SCHEMA_VERSION:
        raise ManifestTooNewError(
            f"manifest declares schema {value}, but this ANSARI understands up to "
            f"{SCHEMA_VERSION}. Upgrade ANSARI to read it."
        )
    return value


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


def _variables(value: object, *, coerce: bool) -> dict[str, VariableValue]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError("'variables' is not a mapping")
    if coerce:
        return {str(k): str(v) for k, v in value.items()}
    return {str(k): _variable_value(k, v) for k, v in value.items()}


def _variable_value(key: object, value: object) -> VariableValue:
    if isinstance(value, str | int | bool) and not isinstance(value, bytes):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ManifestError(f"variable {key!r} has an unsupported type: {type(value).__name__}")


def write_manifest(repo_dir: Path, manifest: Manifest) -> Path:
    """Write the manifest, always in the current schema.

    Only write paths upgrade a repo's manifest on disk. `read_manifest` never
    does, so a repo that is only ever `check`ed keeps the shape it was scaffolded
    with.
    """
    conflicts = overlapping_paths(manifest.templates)
    if conflicts:
        raise ManifestError(
            f"refusing to write: files claimed by more than one template {conflicts}"
        )

    path = manifest_path(repo_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(manifest.to_dict(), sort_keys=False, default_flow_style=False)
    path.write_text(_HEADER + body)
    return path


def read_manifest(repo_dir: Path) -> Manifest | None:
    """Load the manifest, or None if this repo was not scaffolded by ANSARI.

    A malformed manifest raises rather than returning None: "no manifest" and
    "a manifest I can't read" are different situations and deserve different
    messages. A manifest from a newer ANSARI raises `ManifestTooNewError`, which
    is a third situation again — the file is fine, this build is behind.
    """
    path = manifest_path(repo_dir)
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path} is not valid YAML: {exc}") from exc
    return Manifest.from_dict(raw)


def build_record(
    template: str,
    version: str,
    variables: Mapping[str, VariableValue],
    repo_dir: Path,
    paths: Iterable[str],
) -> TemplateRecord:
    """Hash every generated file and record it against the template it came from."""
    return TemplateRecord(
        template=template,
        version=version,
        rendered_at=datetime.now(UTC),
        variables=dict(variables),
        files={path: file_digest(repo_dir / path) for path in sorted(paths)},
    )


def build_manifest(
    template: str,
    version: str,
    variables: Mapping[str, VariableValue],
    repo_dir: Path,
    paths: Iterable[str],
) -> Manifest:
    """Build a single-template manifest — what `ansari new` produces."""
    return Manifest(
        schema=SCHEMA_VERSION,
        templates=[build_record(template, version, variables, repo_dir, paths)],
    )


def attach_record(manifest: Manifest, record: TemplateRecord) -> Manifest:
    """Add a template to an existing manifest, upgrading it to the current schema.

    Refuses when the new record's paths collide with paths an existing template
    already owns. Callers must separately refuse to attach onto a manifest with
    unresolved entries — this function cannot see that, since resolvability is a
    property of the running build's templates, not of the manifest.
    """
    combined = [*manifest.templates, record]
    conflicts = overlapping_paths(combined)
    if conflicts:
        raise ManifestError(
            f"cannot attach {record.template}: it would claim files already owned "
            f"by another template: {conflicts}"
        )
    return Manifest(schema=SCHEMA_VERSION, templates=combined)
