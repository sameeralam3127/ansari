"""Loading a versioned template from its `template.yaml` descriptor.

A template is a directory of Jinja sources plus a descriptor naming its version
and the destination each source renders to. The version is what a repo can fall
behind; the file map is what `ansari check` holds itself responsible for.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

DESCRIPTOR_NAME = "template.yaml"
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "cli" / "templates"


class TemplateError(Exception):
    """A template is missing, or its descriptor cannot be understood."""


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    version: str
    description: str
    files: dict[str, str]
    """Jinja source (relative to root) -> destination path, which may itself
    contain `{{ name }}` and friends."""
    root: Path

    def destinations(self, variables: dict[str, str]) -> dict[str, str]:
        """Resolve destination paths for one set of template variables."""
        env = Environment(autoescape=False)  # nosec B701 - renders file paths, not HTML
        return {
            source: env.from_string(dest).render(**variables) for source, dest in self.files.items()
        }


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

    files = raw.get("files")
    if not isinstance(files, dict) or not files:
        raise TemplateError(f"{descriptor} needs a non-empty 'files' mapping")

    description = raw.get("description")
    return TemplateSpec(
        name=name,
        version=version,
        description=description if isinstance(description, str) else "",
        files={str(k): str(v) for k, v in files.items()},
        root=root,
    )


def bundled_template(language: str) -> TemplateSpec:
    """Load a template that ships with ANSARI, by language."""
    root = BUNDLED_DIR / f"{language}-service"
    if not root.is_dir():
        raise TemplateError(f"no bundled template for language '{language}'")
    return load_template(root)


def render(spec: TemplateSpec, source: str, variables: dict[str, str]) -> str:
    # autoescape is off deliberately: these render Dockerfile/YAML/Markdown text
    # from local CLI arguments, not HTML from untrusted web input.
    env = Environment(
        loader=FileSystemLoader(spec.root), keep_trailing_newline=True, autoescape=False
    )  # nosec B701
    return env.get_template(source).render(**variables)
