"""`make demo`: seed a fleet, drift it the ways real fleets drift, report on it.

Every repo is written by the same code `ansari new` and `ansari attach` run, and
committed to git so `ansari sync` has real history to merge against. The drift is
then made the way it happens in practice -- an old scaffold nobody upgraded, a
hand-tuned value, a deleted example, a manifest mangled in a merge -- so the fleet
report, the dry-run sync and the dashboard all run on nothing faked.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from ansari.scaffold import (
    Manifest,
    TemplateSpec,
    VariableValue,
    attach_template,
    build_manifest,
    bundled_version,
    find_bundled_template,
    generate,
    load_template,
    manifest_path,
    read_manifest,
    write_manifest,
)
from ansari.scaffold.template import NAME_VARIABLE

MARKER = ".ansari-demo"
"""Left in the seeded directory, so a re-run may replace it and nothing else."""

OLD_PYTHON_SERVICE = Path(__file__).resolve().parent / "python-service-1.0.0"
"""python-service 1.0.0's descriptor and the two sources 1.1.0 changed. Laid over
the current template they rebuild 1.0.0 byte for byte, which a test holds against
the golden hashes."""


class DemoError(Exception):
    """The demo can't seed where it was pointed."""


def old_python_service(workdir: Path) -> TemplateSpec:
    """python-service 1.0.0, rebuilt under `workdir` from the current template."""
    root = workdir / "python-service-1.0.0"
    shutil.copytree(_bundled("python-service").root, root)
    shutil.copytree(OLD_PYTHON_SERVICE, root, dirs_exist_ok=True)
    return load_template(root)


def _bundled(name: str) -> TemplateSpec:
    spec = find_bundled_template(name)
    if spec is None:  # pragma: no cover - every template the demo names ships with ANSARI
        raise DemoError(f"this build ships no '{name}' template")
    return spec


def _manifest(repo: Path) -> Manifest:
    manifest = read_manifest(repo)
    if manifest is None:  # pragma: no cover - the demo has just written it
        raise DemoError(f"no manifest in {repo}")
    return manifest


def _git(repo: Path, *args: str) -> None:
    identity = ["-c", "user.name=ANSARI demo", "-c", "user.email=demo@ansari.invalid"]
    subprocess.run(
        ["git", *identity, "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _scaffold(repo: Path, spec: TemplateSpec, **supplied: str) -> None:
    """What `ansari new` does, then the first commit its next steps suggest."""
    variables: dict[str, VariableValue] = {
        NAME_VARIABLE: repo.name,
        **spec.resolve_variables(supplied),
    }
    written = generate(spec, variables, repo)
    write_manifest(repo, build_manifest(spec.name, spec.version, variables, repo, written))
    _git(repo, "init", "-q")
    _commit(repo, f"Scaffold from {spec.name} {spec.version}")


# --------------------------------------------------------------------------
# One function per repo, each a way a fleet drifts
# --------------------------------------------------------------------------


def _service_with_scaling(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, _bundled("python-service"))
    scaling = _bundled("k8s-scaling")
    variables = {NAME_VARIABLE: repo.name, **scaling.resolve_variables({})}
    attach_template(repo, _manifest(repo), scaling, variables, bundled_version)
    _commit(repo, "Attach k8s-scaling")


def _never_upgraded(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, old)


def _never_upgraded_and_tuned(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, old)
    values = repo / "helm" / repo.name / "values.yaml"
    values.write_text(values.read_text().replace("memory: 256Mi", "memory: 512Mi"))
    _commit(repo, "Give checkout more memory")


def _dockerfile_edited(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, _bundled("python-service"))
    dockerfile = repo / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + 'LABEL team="search"\n')
    _commit(repo, "Label the image with its team")


def _module(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, _bundled("terraform-module"))


def _module_example_deleted(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, _bundled("terraform-module"), provider="google")
    (repo / "examples" / "basic" / "main.tf").unlink()
    _commit(repo, "Drop the example")


def _role(repo: Path, old: TemplateSpec) -> None:
    _scaffold(repo, _bundled("ansible-role"))


def _role_with_a_newer_template(repo: Path, old: TemplateSpec) -> None:
    """A colleague on a newer ANSARI attached a template this build doesn't ship."""
    _scaffold(repo, _bundled("ansible-role"))
    policy = repo / "backup" / "policy.yaml"
    policy.parent.mkdir()
    policy.write_text("retention_days: 30\n")
    entries = [record.to_dict() for record in _manifest(repo).templates]
    entries.append(
        {
            "template": "backup-policy",
            "version": "0.3.0",
            "rendered_at": "2026-09-01T09:00:00+00:00",
            "variables": {NAME_VARIABLE: repo.name},
            "files": {"backup/policy.yaml": "sha256:" + "0" * 64},
        }
    )
    manifest_path(repo).write_text(yaml.safe_dump({"schema": 2, "templates": entries}))
    _commit(repo, "Attach backup-policy")


def _manifest_claiming_one_file_twice(repo: Path, old: TemplateSpec) -> None:
    """Hand-edited so a second template claims a file the first already owns."""
    _scaffold(repo, _bundled("python-service"))
    (record,) = _manifest(repo).templates
    first = record.to_dict()
    second = {
        **first,
        "template": "k8s-scaling",
        "version": "0.1.0",
        "files": {"Dockerfile": record.files["Dockerfile"]},
    }
    manifest_path(repo).write_text(yaml.safe_dump({"schema": 2, "templates": [first, second]}))
    _commit(repo, "Track the Dockerfile under k8s-scaling too")


@dataclass(frozen=True)
class Recipe:
    path: str
    story: str
    seed: Callable[[Path, TemplateSpec], None]


RECIPES = (
    Recipe(
        "services/payments", "python-service + k8s-scaling, both current", _service_with_scaling
    ),
    Recipe("services/orders", "python-service 1.0.0, never upgraded", _never_upgraded),
    Recipe(
        "services/checkout",
        "python-service 1.0.0, memory tuned by hand",
        _never_upgraded_and_tuned,
    ),
    Recipe("services/search", "python-service, Dockerfile edited", _dockerfile_edited),
    Recipe("infra/network", "terraform-module (aws), current", _module),
    Recipe("infra/dns", "terraform-module (google), example deleted", _module_example_deleted),
    Recipe("roles/disk-health", "ansible-role, current", _role),
    Recipe(
        "roles/ntp",
        "ansible-role + a template from a newer ANSARI",
        _role_with_a_newer_template,
    ),
    Recipe(
        "legacy/reports",
        "manifest hand-edited so two templates claim one file",
        _manifest_claiming_one_file_twice,
    ),
)


def _prepare(root: Path) -> None:
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise DemoError(f"{root} is not a directory the demo can seed")
    if root.exists():
        if not (root / MARKER).is_file() and any(root.iterdir()):
            raise DemoError(
                f"{root} already exists and wasn't seeded by the demo; refusing to replace it"
            )
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / MARKER).write_text(
        "Seeded by `make demo`. Safe to delete; the demo replaces it on every run.\n"
    )


def seed_fleet(root: Path) -> tuple[Recipe, ...]:
    """Replace `root` with a freshly drifted fleet; return what was seeded."""
    if shutil.which("git") is None:
        raise DemoError("the demo needs git: sync merges edited files against repo history")
    _prepare(root)
    with tempfile.TemporaryDirectory() as workdir:
        old = old_python_service(Path(workdir))
        for recipe in RECIPES:
            recipe.seed(root / recipe.path, old)
    return RECIPES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ansari.demo",
        description="Seed a drifted fleet of ANSARI repos to run the fleet report against.",
    )
    parser.add_argument("root", type=Path, help="directory to seed; an earlier demo's is replaced")
    root: Path = parser.parse_args(argv).root

    try:
        recipes = seed_fleet(root)
    except DemoError as exc:
        print(f"demo: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"demo: {exc}\n{exc.stderr.decode(errors='replace')}", file=sys.stderr)
        return 1

    print(f"Seeded {len(recipes)} repos under {root}")
    width = max(len(recipe.path) for recipe in recipes)
    for recipe in recipes:
        print(f"  {recipe.path.ljust(width)}  {recipe.story}")
    return 0
