"""The terraform-module template: layout, provider pins, CI, and real Terraform.

`terraform fmt` runs whenever Terraform is installed: it is fast and offline.
`terraform init` + `validate` download the provider -- several hundred megabytes
for aws -- so they run only for providers listed in ANSARI_TERRAFORM_VALIDATE
(comma-separated). CI's template-smoke job sets it.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import find_bundled_template, manifest_path, read_manifest

runner = CliRunner()

PINS = {
    "aws": ("hashicorp/aws", "~> 6.0"),
    "google": ("hashicorp/google", "~> 8.0"),
    "azurerm": ("hashicorp/azurerm", "~> 5.0"),
}
EXPECTED = {
    "versions.tf",
    "main.tf",
    "variables.tf",
    "outputs.tf",
    "README.md",
    "examples/basic/main.tf",
    ".github/workflows/ansari.yml",
    ".gitignore",
}
TERRAFORM = shutil.which("terraform")
needs_terraform = pytest.mark.skipif(TERRAFORM is None, reason="terraform is not installed")
VALIDATE = {p.strip() for p in os.environ.get("ANSARI_TERRAFORM_VALIDATE", "").split(",") if p}


def _module(tmp_path: Path, provider: str = "aws", name: str = "network") -> Path:
    args = ["new", name, "--type", "terraform-module", "--output-dir", str(tmp_path)]
    args += ["--var", f"provider={provider}"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return tmp_path / name


def _terraform(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert TERRAFORM is not None
    env = {**os.environ, "TF_IN_AUTOMATION": "1"}
    return subprocess.run(
        [TERRAFORM, *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


# --------------------------------------------------------------------------
# Layout and manifest
# --------------------------------------------------------------------------


def test_scaffolds_the_expected_layout_and_checks_clean(tmp_path: Path) -> None:
    repo = _module(tmp_path)

    on_disk = {
        str(p.relative_to(repo))
        for p in repo.rglob("*")
        if p.is_file() and p != manifest_path(repo)
    }
    assert on_disk == EXPECTED

    manifest = read_manifest(repo)
    assert manifest is not None
    record = manifest.templates[0]
    assert record.template == "terraform-module"
    assert set(record.files) == EXPECTED
    assert record.variables == {"name": "network", "provider": "aws"}

    checked = runner.invoke(app, ["check", str(repo)])
    assert checked.exit_code == 0, checked.output


def test_an_unknown_provider_is_rejected(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "new",
            "network",
            "--type",
            "terraform-module",
            "--var",
            "provider=digitalocean",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "must be one of" in result.output
    assert not (tmp_path / "network").exists()


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------


@pytest.mark.parametrize("provider", sorted(PINS))
def test_versions_pin_exactly_one_provider_to_its_current_major(
    tmp_path: Path, provider: str
) -> None:
    versions = (_module(tmp_path, provider) / "versions.tf").read_text()
    source, constraint = PINS[provider]

    assert 'required_version = ">= 1.6.0"' in versions
    assert f'source  = "{source}"' in versions
    assert f'version = "{constraint}"' in versions
    assert versions.count("source ") == 1


@pytest.mark.parametrize(
    ("provider", "kind"), [("aws", "tags"), ("azurerm", "tags"), ("google", "labels")]
)
def test_google_uses_labels_and_the_others_use_tags(
    tmp_path: Path, provider: str, kind: str
) -> None:
    repo = _module(tmp_path, provider)
    for file in ("main.tf", "variables.tf", "outputs.tf"):
        assert (
            f"local.{kind}" in (repo / file).read_text() or f'"{kind}"' in (repo / file).read_text()
        )
    other = "tags" if kind == "labels" else "labels"
    assert f'variable "{other}"' not in (repo / "variables.tf").read_text()


def test_the_module_configures_no_provider(tmp_path: Path) -> None:
    """Providers belong to the caller; a module that configures one can't be reused."""
    repo = _module(tmp_path)
    for file in ("versions.tf", "main.tf", "variables.tf", "outputs.tf"):
        assert 'provider "' not in (repo / file).read_text()


@pytest.mark.parametrize("provider", sorted(PINS))
def test_the_example_configures_the_provider_and_uses_the_module(
    tmp_path: Path, provider: str
) -> None:
    example = (_module(tmp_path, provider, "my-network") / "examples/basic/main.tf").read_text()
    assert f'provider "{provider}"' in example
    assert 'source = "../.."' in example
    # HCL style: module labels use underscores even when the repo name has hyphens.
    assert 'module "my_network"' in example
    if provider == "azurerm":
        assert "features {}" in example


def test_gitignore_is_copied_verbatim(tmp_path: Path) -> None:
    spec = find_bundled_template("terraform-module")
    assert spec is not None
    repo = _module(tmp_path)
    assert (repo / ".gitignore").read_bytes() == (spec.root / "gitignore").read_bytes()
    assert ".terraform/" in (repo / ".gitignore").read_text()


# --------------------------------------------------------------------------
# Generated CI: credential-free, plan disabled
# --------------------------------------------------------------------------


def test_generated_ci_validates_without_credentials(tmp_path: Path) -> None:
    workflow_text = (_module(tmp_path) / ".github/workflows/ansari.yml").read_text()
    workflow = yaml.safe_load(workflow_text)

    # The plan job is commented out, so the only job YAML sees is validate.
    assert set(workflow["jobs"]) == {"validate"}
    assert workflow["permissions"] == {"contents": "read"}

    runs = "\n".join(step.get("run", "") for step in workflow["jobs"]["validate"]["steps"])
    assert "terraform fmt -check -recursive" in runs
    assert "terraform init -backend=false" in runs
    assert "terraform validate" in runs
    assert "secrets." not in workflow_text


def test_plan_ships_commented_out(tmp_path: Path) -> None:
    """The boundary: ANSARI's golden path needs no cloud credentials anywhere."""
    lines = (_module(tmp_path) / ".github/workflows/ansari.yml").read_text().splitlines()
    plan_lines = [line for line in lines if "terraform plan" in line]
    assert plan_lines, "the plan job should be present, commented, for users to enable"
    assert all(line.lstrip().startswith("#") for line in plan_lines)
    assert any(line.strip() == "# plan:" for line in lines)


# --------------------------------------------------------------------------
# Real Terraform
# --------------------------------------------------------------------------


@needs_terraform
@pytest.mark.parametrize("provider", sorted(PINS))
def test_terraform_fmt_accepts_the_output(tmp_path: Path, provider: str) -> None:
    result = _terraform(_module(tmp_path, provider), "fmt", "-check", "-recursive", "-diff")
    assert result.returncode == 0, result.stdout + result.stderr


@needs_terraform
@pytest.mark.parametrize("provider", sorted(PINS))
def test_terraform_validates_the_module_and_example(tmp_path: Path, provider: str) -> None:
    if provider not in VALIDATE:
        pytest.skip(f"set ANSARI_TERRAFORM_VALIDATE={provider} to download and validate")
    repo = _module(tmp_path, provider)

    for directory in (repo, repo / "examples/basic"):
        init = _terraform(directory, "init", "-backend=false", "-input=false", "-no-color")
        assert init.returncode == 0, init.stdout + init.stderr
        valid = _terraform(directory, "validate", "-no-color")
        assert valid.returncode == 0, valid.stdout + valid.stderr


@needs_terraform
def test_terraform_rejects_an_invalid_name(tmp_path: Path) -> None:
    if "aws" not in VALIDATE:
        pytest.skip("set ANSARI_TERRAFORM_VALIDATE=aws to download and validate")
    repo = _module(tmp_path)
    assert _terraform(repo, "init", "-backend=false", "-input=false").returncode == 0

    result = _terraform(repo, "plan", "-input=false", "-no-color", "-var", "name=Not_Valid")
    assert result.returncode != 0
    assert "Invalid value for variable" in result.stdout + result.stderr
