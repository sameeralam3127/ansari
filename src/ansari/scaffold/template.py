"""Loading a versioned template from its `template.yaml` descriptor.

A template is a directory of Jinja sources plus a descriptor naming its version,
the variables it accepts, and the destination each source renders to. The version
is what a repo can fall behind; the file map is what `ansari check` holds itself
responsible for.

Templates declare their own variables. The alternative -- a table of known
options in the CLI -- meant every new template type required editing
`cli/main.py`, which is the special-casing this fork exists to remove.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

from ansari.scaffold.manifest import VariableValue

DESCRIPTOR_NAME = "template.yaml"
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "cli" / "templates"

NAME_VARIABLE = "name"
"""Supplied by the CLI for every template, never declared by one: it is the
artifact's name, and a template that could rename its own output would break the
destination paths the manifest tracks."""

VARIABLE_TYPES = ("string", "int", "bool", "list")


class TemplateError(Exception):
    """A template is missing, or its descriptor cannot be understood."""


class VariableError(TemplateError):
    """A caller supplied variables a template cannot accept.

    Separate from TemplateError because the fault is the caller's, not the
    template's, and the two want different messages.
    """


@dataclass(frozen=True)
class VariableSpec:
    """One input a template declares."""

    name: str
    type: str = "string"
    default: VariableValue | None = None
    choices: list[str] | None = None
    description: str = ""

    @property
    def required(self) -> bool:
        return self.default is None

    def parse(self, raw: str) -> VariableValue:
        """Coerce one `--var key=value` string into the declared type.

        Values arrive from the command line as text regardless of what the
        template declares, so the declaration is the only thing that knows a
        `3` from a `"3"`.
        """
        if self.type == "int":
            try:
                return int(raw)
            except ValueError as exc:
                raise VariableError(f"'{self.name}' expects an integer, got {raw!r}") from exc
        if self.type == "bool":
            lowered = raw.strip().lower()
            if lowered in ("true", "yes", "1"):
                return True
            if lowered in ("false", "no", "0"):
                return False
            raise VariableError(f"'{self.name}' expects true or false, got {raw!r}")
        if self.type == "list":
            return [item.strip() for item in raw.split(",") if item.strip()]
        return raw

    def validate(self, value: VariableValue) -> None:
        if self.choices is not None and str(value) not in self.choices:
            raise VariableError(
                f"'{self.name}' must be one of {sorted(self.choices)}, got {str(value)!r}"
            )


@dataclass(frozen=True)
class FileSpec:
    """One file a template generates."""

    source: str
    dest: str
    """Destination path, which may itself contain `{{ name }}` and friends."""


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    version: str
    description: str
    files: dict[str, FileSpec]
    """Jinja source (relative to root) -> what it generates."""
    variables: dict[str, VariableSpec]
    root: Path

    def destinations(self, variables: Mapping[str, VariableValue]) -> dict[str, str]:
        """Resolve destination paths for one set of template variables."""
        env = Environment(autoescape=False)  # nosec B701 - renders file paths, not HTML
        return {
            source: env.from_string(spec.dest).render(**variables)
            for source, spec in self.files.items()
        }

    def resolve_variables(self, supplied: Mapping[str, str]) -> dict[str, VariableValue]:
        """Type, validate, and default the variables for one render.

        Unknown names are rejected rather than passed through: a typo in
        `--var databse=postgres` would otherwise silently scaffold the default
        and be discovered much later, in a repo nobody re-reads.
        """
        unknown = sorted(set(supplied) - set(self.variables) - {NAME_VARIABLE})
        if unknown:
            known = sorted([NAME_VARIABLE, *self.variables])
            raise VariableError(
                f"template '{self.name}' has no variable(s) {unknown}. Accepts: {known}"
            )

        resolved: dict[str, VariableValue] = {}
        for key, spec in self.variables.items():
            if key in supplied:
                value = spec.parse(supplied[key])
            elif spec.default is not None:
                value = spec.default
            else:
                raise VariableError(f"template '{self.name}' requires --var {key}=<{spec.type}>")
            spec.validate(value)
            resolved[key] = value
        return resolved


def _parse_variables(raw: object, descriptor: Path) -> dict[str, VariableSpec]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise TemplateError(f"{descriptor}: 'variables' is not a mapping")

    specs: dict[str, VariableSpec] = {}
    for key, body in raw.items():
        name = str(key)
        if name == NAME_VARIABLE:
            raise TemplateError(
                f"{descriptor}: '{NAME_VARIABLE}' is supplied by ANSARI and cannot be declared"
            )
        # A bare scalar is shorthand for a string with that default.
        if not isinstance(body, dict):
            specs[name] = VariableSpec(name=name, default=str(body))
            continue

        declared = body.get("type", "string")
        if declared not in VARIABLE_TYPES:
            raise TemplateError(
                f"{descriptor}: variable '{name}' has unknown type {declared!r}; "
                f"expected one of {list(VARIABLE_TYPES)}"
            )

        choices = body.get("choices")
        if choices is not None:
            if not isinstance(choices, list) or not choices:
                raise TemplateError(f"{descriptor}: variable '{name}' has a non-list 'choices'")
            choices = [str(c) for c in choices]

        default = body.get("default")
        specs[name] = VariableSpec(
            name=name,
            type=str(declared),
            default=default,
            choices=choices,
            description=str(body.get("description", "")),
        )

        if default is not None and choices is not None and str(default) not in choices:
            raise TemplateError(
                f"{descriptor}: variable '{name}' defaults to {default!r}, "
                "which is not among its 'choices'"
            )
    return specs


def _parse_files(raw: object, descriptor: Path) -> dict[str, FileSpec]:
    if not isinstance(raw, dict) or not raw:
        raise TemplateError(f"{descriptor} needs a non-empty 'files' mapping")

    files: dict[str, FileSpec] = {}
    for key, body in raw.items():
        source = str(key)
        # Both forms are accepted. The short form is `source: dest`; the mapping
        # form carries per-file options. Keeping the short form working means no
        # existing descriptor has to change.
        if isinstance(body, dict):
            dest = body.get("dest")
            if not isinstance(dest, str) or not dest:
                raise TemplateError(f"{descriptor}: file '{source}' needs a string 'dest'")
            files[source] = FileSpec(source=source, dest=dest)
        else:
            files[source] = FileSpec(source=source, dest=str(body))
    return files


def load_template(root: Path) -> TemplateSpec:
    descriptor = root / DESCRIPTOR_NAME
    if not descriptor.is_file():
        raise TemplateError(f"no {DESCRIPTOR_NAME} in {root}")

    try:
        raw: Any = yaml.safe_load(descriptor.read_text())
    except yaml.YAMLError as exc:
        raise TemplateError(f"{descriptor} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise TemplateError(f"{descriptor} is not a YAML mapping")

    name, version = raw.get("name"), raw.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise TemplateError(f"{descriptor} needs a string 'name' and 'version'")

    description = raw.get("description")
    return TemplateSpec(
        name=name,
        version=version,
        description=description if isinstance(description, str) else "",
        files=_parse_files(raw.get("files"), descriptor),
        variables=_parse_variables(raw.get("variables"), descriptor),
        root=root,
    )


def available_templates() -> list[str]:
    """Every template this build ships, by name.

    Read from the bundled directory rather than a list in code, so adding a
    template type never means editing the CLI.
    """
    if not BUNDLED_DIR.is_dir():
        return []
    return sorted(
        entry.name
        for entry in BUNDLED_DIR.iterdir()
        if entry.is_dir() and (entry / DESCRIPTOR_NAME).is_file()
    )


def bundled_template(language: str) -> TemplateSpec:
    """Load a template that ships with ANSARI, by language.

    Retained for the `--language` path; resolution by template name is the
    general form. Renaming this is scheduled cleanup, not part of this change.
    """
    root = BUNDLED_DIR / f"{language}-service"
    if not root.is_dir():
        raise TemplateError(f"no bundled template for language '{language}'")
    return load_template(root)


def find_bundled_template(name: str) -> TemplateSpec | None:
    """Load a bundled template by its own name, or None if this build has none.

    This is the resolution path a manifest uses. Every manifest ever written
    records `template:` directly, and the bundled directory is named for the
    template it holds, so this works unchanged on manifests that predate
    multi-template support -- no repo needs migrating for it.

    Returns None rather than raising because "this build ships no such template"
    is a reportable state, not an error: a repo may legitimately carry a template
    from a newer ANSARI.
    """
    # Guard against a manifest steering the lookup out of the bundled directory.
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    root = BUNDLED_DIR / name
    if not root.is_dir():
        return None
    return load_template(root)


def bundled_version(name: str) -> str | None:
    """The version of a bundled template, or None if this build does not ship it."""
    spec = find_bundled_template(name)
    return spec.version if spec else None


def render(spec: TemplateSpec, source: str, variables: Mapping[str, VariableValue]) -> str:
    # autoescape is off deliberately: these render Dockerfile/YAML/Markdown text
    # from local CLI arguments, not HTML from untrusted web input.
    env = Environment(
        loader=FileSystemLoader(spec.root), keep_trailing_newline=True, autoescape=False
    )  # nosec B701
    return env.get_template(source).render(**variables)
