"""The ansible-role template: layout, metadata, CI, and the real linters.

yamllint and ansible-lint run whenever they are installed: they are fast and
offline. `molecule test` pulls a container image and needs Docker, so it runs
only when ANSARI_MOLECULE_TEST=1. ANSARI_MOLECULE_CMD overrides how molecule is
invoked, for an environment where it isn't installed with the docker driver.
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import find_bundled_template, manifest_path, read_manifest

runner = CliRunner()

BASE = {
    "tasks/main.yml",
    "handlers/main.yml",
    "defaults/main.yml",
    "meta/main.yml",
    "README.md",
    ".github/workflows/ansari.yml",
    ".yamllint",
    ".ansible-lint",
    ".gitignore",
}
MOLECULE = {
    "molecule/default/molecule.yml",
    "molecule/default/converge.yml",
    "molecule/default/verify.yml",
}
ANSIBLE_LINT = shutil.which("ansible-lint")
YAMLLINT = shutil.which("yamllint")


def _role(tmp_path: Path, *variables: str, name: str = "disk-health") -> Path:
    args = ["new", name, "--type", "ansible-role", "--output-dir", str(tmp_path)]
    for variable in variables:
        args += ["--var", variable]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return tmp_path / name


def _generated(repo: Path) -> set[str]:
    return {
        str(p.relative_to(repo))
        for p in repo.rglob("*")
        if p.is_file() and p != manifest_path(repo) and ".ansible" not in p.parts
    }


def _run(cwd: Path, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


# --------------------------------------------------------------------------
# Layout and manifest
# --------------------------------------------------------------------------


def test_scaffolds_the_standard_role_layout_and_checks_clean(tmp_path: Path) -> None:
    repo = _role(tmp_path)
    assert _generated(repo) == BASE

    manifest = read_manifest(repo)
    assert manifest is not None
    assert set(manifest.templates[0].files) == BASE

    checked = runner.invoke(app, ["check", str(repo)])
    assert checked.exit_code == 0, checked.output


def test_molecule_is_opt_in_and_tracked_when_chosen(tmp_path: Path) -> None:
    repo = _role(tmp_path, "with_molecule=true")
    assert _generated(repo) == BASE | MOLECULE

    manifest = read_manifest(repo)
    assert manifest is not None
    assert set(manifest.templates[0].files) == BASE | MOLECULE


def test_a_non_boolean_molecule_choice_is_rejected(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "new",
            "r",
            "--type",
            "ansible-role",
            "--var",
            "with_molecule=maybe",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "true or false" in result.output


# --------------------------------------------------------------------------
# No brace escaping: M6's reason for render modes
# --------------------------------------------------------------------------


def test_no_template_source_escapes_its_braces() -> None:
    spec = find_bundled_template("ansible-role")
    assert spec is not None
    for source in spec.files:
        text = (spec.root / source).read_text()
        assert "{{ '{{' }}" not in text, f"{source} escapes Jinja braces"


def test_ansible_jinja_is_written_exactly_as_authored(tmp_path: Path) -> None:
    tasks = (_role(tmp_path) / "tasks/main.yml").read_text()
    assert "{{ ansible_facts['distribution'] }}" in tasks
    assert "when: disk_health_enabled | bool" in tasks


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------


def test_meta_defaults(tmp_path: Path) -> None:
    meta = yaml.safe_load((_role(tmp_path) / "meta/main.yml").read_text())
    info = meta["galaxy_info"]

    # Galaxy role names can't contain hyphens, even when the repository's can.
    assert info["role_name"] == "disk_health"
    assert "namespace" not in info
    assert info["license"] == "MIT"
    assert info["min_ansible_version"] == "2.16"
    assert info["platforms"] == [
        {"name": "Ubuntu", "versions": ["all"]},
        {"name": "EL", "versions": ["all"]},
    ]
    assert info["galaxy_tags"] == []
    assert meta["dependencies"] == []


def test_meta_survives_awkward_values(tmp_path: Path) -> None:
    """Free text is JSON-quoted, so colons and quotes can't break the YAML."""
    repo = _role(
        tmp_path,
        "author=O'Neil: Platform Team",
        'description=Checks disks: "SMART" data, & more',
        "namespace=acme",
        "platforms=Debian,Fedora",
        "galaxy_tags=linux,storage",
    )
    info = yaml.safe_load((repo / "meta/main.yml").read_text())["galaxy_info"]

    assert info["author"] == "O'Neil: Platform Team"
    assert info["description"] == 'Checks disks: "SMART" data, & more'
    assert info["namespace"] == "acme"
    assert [p["name"] for p in info["platforms"]] == ["Debian", "Fedora"]
    assert info["galaxy_tags"] == ["linux", "storage"]


def test_role_variables_carry_the_role_prefix(tmp_path: Path) -> None:
    defaults = yaml.safe_load((_role(tmp_path) / "defaults/main.yml").read_text())
    assert defaults == {"disk_health_enabled": True}


# --------------------------------------------------------------------------
# Generated CI and lint configuration
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("molecule", "jobs"), [(False, {"lint"}), (True, {"lint", "molecule"})])
def test_generated_ci_jobs(tmp_path: Path, molecule: bool, jobs: set[str]) -> None:
    text = (
        _role(tmp_path, f"with_molecule={str(molecule).lower()}") / ".github/workflows/ansari.yml"
    ).read_text()
    workflow = yaml.safe_load(text)

    # ansible-lint's production profile fails a YAML file with no document start.
    assert text.startswith("---\n")
    assert set(workflow["jobs"]) == jobs
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in text
    if molecule:
        runs = [step.get("run", "") for step in workflow["jobs"]["molecule"]["steps"]]
        assert "molecule test" in runs


def test_copied_files_are_byte_identical_to_their_sources(tmp_path: Path) -> None:
    spec = find_bundled_template("ansible-role")
    assert spec is not None
    repo = _role(tmp_path, "with_molecule=true")
    for source, file in spec.files.items():
        if file.render == "copy":
            assert (repo / file.dest).read_bytes() == (spec.root / source).read_bytes(), source


def test_lint_configs_exclude_the_ansari_manifest(tmp_path: Path) -> None:
    """The committed manifest has no `---`, and would fail the role's own lint CI."""
    repo = _role(tmp_path)
    assert ".ansari/" in yaml.safe_load((repo / ".ansible-lint").read_text())["exclude_paths"]
    assert ".ansari/" in yaml.safe_load((repo / ".yamllint").read_text())["ignore"]


def test_molecule_scenario_can_find_and_name_the_role(tmp_path: Path) -> None:
    """Two settings without which `molecule test` fails -- both found by running it.

    Without the roles path, converge can't find the role. Without relaxing the
    role-name check, molecule refuses to start when there's no Galaxy namespace.
    """
    scenario = yaml.safe_load(
        (_role(tmp_path, "with_molecule=true") / "molecule/default/molecule.yml").read_text()
    )
    assert (
        scenario["provisioner"]["env"]["ANSIBLE_ROLES_PATH"] == "${MOLECULE_PROJECT_DIRECTORY}/.."
    )
    assert scenario["role_name_check"] == 1


@pytest.mark.parametrize("molecule", [False, True])
def test_every_yaml_file_ends_cleanly(tmp_path: Path, molecule: bool) -> None:
    """Exactly one trailing newline -- the whitespace bug class, checked without yamllint."""
    repo = _role(tmp_path, f"with_molecule={str(molecule).lower()}")
    for relative in _generated(repo):
        if relative.endswith((".yml", ".yamllint", ".ansible-lint")):
            text = (repo / relative).read_text()
            assert text.endswith("\n") and not text.endswith("\n\n"), relative


# --------------------------------------------------------------------------
# The real tools
# --------------------------------------------------------------------------


@pytest.mark.skipif(YAMLLINT is None, reason="yamllint is not installed")
@pytest.mark.parametrize("molecule", [False, True])
def test_yamllint_strict_passes(tmp_path: Path, molecule: bool) -> None:
    repo = _role(tmp_path, f"with_molecule={str(molecule).lower()}")
    assert YAMLLINT is not None
    result = _run(repo, YAMLLINT, "--strict", ".")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(ANSIBLE_LINT is None, reason="ansible-lint is not installed")
@pytest.mark.parametrize("molecule", [False, True])
def test_ansible_lint_production_profile_passes(tmp_path: Path, molecule: bool) -> None:
    """M6's acceptance criterion, with settings read from the generated .ansible-lint."""
    repo = _role(tmp_path, f"with_molecule={str(molecule).lower()}")
    assert ANSIBLE_LINT is not None
    result = _run(repo, ANSIBLE_LINT)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Profile 'production' was required, and it passed" in output


@pytest.mark.skipif(
    os.environ.get("ANSARI_MOLECULE_TEST") != "1" or shutil.which("docker") is None,
    reason="set ANSARI_MOLECULE_TEST=1 (needs Docker) to run molecule",
)
def test_molecule_scenario_converges_idempotently(tmp_path: Path) -> None:
    repo = _role(tmp_path, "with_molecule=true")
    command = shlex.split(os.environ.get("ANSARI_MOLECULE_CMD", "molecule"))
    result = _run(repo, *command, "test")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-4000:]
    assert "All assertions passed" in output
