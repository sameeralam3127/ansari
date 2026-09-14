"""Loading a versioned template from its `template.yaml` descriptor, and writing it.

A template is a directory of Jinja sources plus a descriptor naming its version,
the variables it accepts, and the destination each source renders to. The version
is what a repo can fall behind; the file map is what `ansari check` holds itself
responsible for.

Templates declare their own variables. The alternative -- a table of known
options in the CLI -- meant every new template type required editing
`cli/main.py`, which is the special-casing this fork exists to remove.

Templates also choose how their files are rendered. Output that is itself Jinja
-- Ansible above all -- would otherwise have to escape its own braces on nearly
every line, so a template can move ANSARI's markers aside, copy a file verbatim,
set its permission bits, or generate it only when a variable asks for it.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment, FileSystemLoader

from ansari.scaffold.manifest import VariableValue

DESCRIPTOR_NAME = "template.yaml"
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "cli" / "templates"

NAME_VARIABLE = "name"
"""Supplied by the CLI for every template, never declared by one: it is the
artifact's name, and a template that could rename its own output would break the
destination paths the manifest tracks."""

VARIABLE_TYPES = ("string", "int", "bool", "list")
RENDER_MODES = ("jinja", "copy")
_OCTAL_MODE = re.compile(r"^0?[0-7]{3}$")


class TemplateError(Exception):
    """A template is missing, or its descriptor cannot be understood."""


class VariableError(TemplateError):
    """A caller supplied variables a template cannot accept.

    Separate from TemplateError because the fault is the caller's, not the
    template's, and the two want different messages.
    """


@dataclass(frozen=True)
class Delimiters:
    """The markers ANSARI's own rendering pass responds to."""

    variable_start: str = "{{"
    variable_end: str = "}}"
    block_start: str = "{%"
    block_end: str = "%}"
    comment_start: str = "{#"
    comment_end: str = "#}"


DELIMITER_PRESETS: dict[str, Delimiters] = {
    "jinja": Delimiters(),
    # For output that is itself Jinja. ANSARI's markers move aside so that
    # `{{ ansible_facts }}`, `{% if %}` and `{# #}` pass through untouched and the
    # source stays valid, lintable Ansible. Comments have to move as well: left
    # alone, a `{# ... #}` in a task file would be silently eaten.
    "alternate": Delimiters("[[", "]]", "[%", "%]", "[#", "#]"),
}


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
    render: str = "jinja"
    """`jinja` renders the source; `copy` writes its bytes untouched."""
    mode: int | None = None
    """Permission bits applied after writing, e.g. 0o755. Drift tracks content,
    so a later chmod on the generated file is not reported."""
    when: str | None = None
    """A declared bool variable; the file is generated only when it is true."""


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    version: str
    description: str
    files: dict[str, FileSpec]
    """Source (relative to root) -> what it generates."""
    variables: dict[str, VariableSpec]
    root: Path
    delimiters: Delimiters = field(default_factory=Delimiters)

    def environment(self, *, loader: BaseLoader | None = None) -> Environment:
        # autoescape is off deliberately: these render Dockerfile/YAML/HCL text
        # from local CLI arguments, not HTML from untrusted web input.
        d = self.delimiters
        return Environment(  # nosec B701
            loader=loader,
            autoescape=False,
            keep_trailing_newline=True,
            variable_start_string=d.variable_start,
            variable_end_string=d.variable_end,
            block_start_string=d.block_start,
            block_end_string=d.block_end,
            comment_start_string=d.comment_start,
            comment_end_string=d.comment_end,
        )

    def included(self, variables: Mapping[str, VariableValue]) -> dict[str, FileSpec]:
        """The files this set of variables actually generates.

        A `when` gate is satisfied only by a real `True`: failing closed means a
        malformed value omits an optional file rather than adding one nobody
        asked for.
        """
        return {
            source: spec
            for source, spec in self.files.items()
            if spec.when is None or variables.get(spec.when) is True
        }

    def destinations(self, variables: Mapping[str, VariableValue]) -> dict[str, str]:
        """Resolve destination paths for one set of template variables."""
        env = self.environment()
        return {
            source: env.from_string(spec.dest).render(**variables)
            for source, spec in self.included(variables).items()
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


def _parse_mode(value: object, source: str, descriptor: Path) -> int | None:
    if value is None:
        return None
    # YAML reads an unquoted 0755 as the integer 493 and 755 as seven hundred and
    # fifty-five, so an unquoted mode cannot be trusted to mean what it looks like.
    if not isinstance(value, str) or not _OCTAL_MODE.match(value):
        raise TemplateError(
            f"{descriptor}: file '{source}' mode must be a quoted octal string "
            f"like '0755', got {value!r}"
        )
    return int(value, 8)


def _parse_files(raw: object, descriptor: Path) -> dict[str, FileSpec]:
    if not isinstance(raw, dict) or not raw:
        raise TemplateError(f"{descriptor} needs a non-empty 'files' mapping")

    files: dict[str, FileSpec] = {}
    for key, body in raw.items():
        source = str(key)
        # Both forms are accepted. The short form is `source: dest`; the mapping
        # form carries per-file options. Keeping the short form working means no
        # existing descriptor has to change.
        if not isinstance(body, dict):
            files[source] = FileSpec(source=source, dest=str(body))
            continue

        dest = body.get("dest")
        if not isinstance(dest, str) or not dest:
            raise TemplateError(f"{descriptor}: file '{source}' needs a string 'dest'")

        render = body.get("render", "jinja")
        if render not in RENDER_MODES:
            raise TemplateError(
                f"{descriptor}: file '{source}' has unknown render mode {render!r}; "
                f"expected one of {list(RENDER_MODES)}"
            )

        when = body.get("when")
        if when is not None and not isinstance(when, str):
            raise TemplateError(f"{descriptor}: file '{source}' has a non-string 'when'")

        files[source] = FileSpec(
            source=source,
            dest=dest,
            render=str(render),
            mode=_parse_mode(body.get("mode"), source, descriptor),
            when=when,
        )
    return files


def _parse_render(raw: object, descriptor: Path) -> Delimiters:
    if raw is None:
        return DELIMITER_PRESETS["jinja"]
    if not isinstance(raw, dict):
        raise TemplateError(f"{descriptor}: 'render' is not a mapping")

    unknown = sorted(str(k) for k in raw if k != "delimiters")
    if unknown:
        raise TemplateError(f"{descriptor}: 'render' has unknown key(s) {unknown}")

    preset = raw.get("delimiters", "jinja")
    if not isinstance(preset, str) or preset not in DELIMITER_PRESETS:
        raise TemplateError(
            f"{descriptor}: unknown delimiters {preset!r}; "
            f"expected one of {sorted(DELIMITER_PRESETS)}"
        )
    return DELIMITER_PRESETS[preset]


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

    variables = _parse_variables(raw.get("variables"), descriptor)
    files = _parse_files(raw.get("files"), descriptor)

    # Checked at load time rather than at the first scaffold that happens to hit
    # it: a `when` naming a typo would otherwise just never generate its file.
    for spec in files.values():
        if spec.when is None:
            continue
        gate = variables.get(spec.when)
        if gate is None or gate.type != "bool":
            raise TemplateError(
                f"{descriptor}: file '{spec.source}' has when: {spec.when!r}, "
                "which is not a declared bool variable"
            )

    description = raw.get("description")
    return TemplateSpec(
        name=name,
        version=version,
        description=description if isinstance(description, str) else "",
        files=files,
        variables=variables,
        root=root,
        delimiters=_parse_render(raw.get("render"), descriptor),
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
    """Render one Jinja source with the template's own delimiters."""
    env = spec.environment(loader=FileSystemLoader(spec.root))
    return env.get_template(source).render(**variables)


def generate(
    spec: TemplateSpec, variables: Mapping[str, VariableValue], repo_dir: Path
) -> list[str]:
    """Write every file this set of variables generates; return the paths written.

    Every destination is resolved and checked before anything is written, so a
    refused path leaves no half-scaffolded repo behind. Refused: a destination
    outside the repo (a `--var` value can reach a destination path), two sources
    writing the same file, and a source the template does not actually contain.
    """
    root = repo_dir.resolve()
    plan: list[tuple[FileSpec, str]] = []
    claimed: dict[str, str] = {}

    for source, dest in spec.destinations(variables).items():
        file = spec.files[source]
        target = (repo_dir / dest).resolve()
        if target == root or not target.is_relative_to(root):
            raise TemplateError(f"'{source}' would write outside the repo: {dest!r}")
        if dest in claimed:
            raise TemplateError(f"'{claimed[dest]}' and '{source}' both write {dest!r}")
        if not (spec.root / source).is_file():
            raise TemplateError(f"template '{spec.name}' has no source file '{source}'")
        claimed[dest] = source
        plan.append((file, dest))

    written: list[str] = []
    for file, dest in plan:
        target = repo_dir / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.render == "copy":
            target.write_bytes((spec.root / file.source).read_bytes())
        else:
            target.write_text(render(spec, file.source, variables))
        if file.mode is not None:
            target.chmod(file.mode)
        written.append(dest)
    return written
