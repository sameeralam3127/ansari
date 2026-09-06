from pathlib import Path

import pytest
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import SCHEMA_VERSION, manifest_path, read_manifest

runner = CliRunner()


def test_new_scaffolds_expected_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "payment-api", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output

    service_dir = tmp_path / "payment-api"
    assert (service_dir / "Dockerfile").exists()
    assert (service_dir / ".github" / "workflows" / "ansari.yml").exists()
    assert (service_dir / "README.md").exists()
    assert (service_dir / "helm" / "payment-api" / "Chart.yaml").exists()
    assert (service_dir / "helm" / "payment-api" / "values.yaml").exists()
    assert (service_dir / "helm" / "payment-api" / "templates" / "deployment.yaml").exists()
    assert (service_dir / "helm" / "payment-api" / "templates" / "service.yaml").exists()

    workflow = (service_dir / ".github" / "workflows" / "ansari.yml").read_text()
    assert "${{ github.sha }}" in workflow


def test_new_writes_a_manifest_covering_every_generated_file(tmp_path: Path) -> None:
    runner.invoke(app, ["new", "payment-api", "--output-dir", str(tmp_path)])
    service_dir = tmp_path / "payment-api"

    manifest = read_manifest(service_dir)
    assert manifest is not None
    assert manifest.schema == SCHEMA_VERSION

    record = manifest.templates[0]
    assert record.template == "python-service"
    assert record.variables == {
        "name": "payment-api",
        "language": "python",
        "database": "postgres",
    }

    # Every file the manifest claims must exist, and nothing generated may be
    # left untracked -- an untracked file is one `ansari sync` would clobber.
    generated = {
        str(p.relative_to(service_dir))
        for p in service_dir.rglob("*")
        if p.is_file() and manifest_path(service_dir) != p
    }
    assert set(record.files) == generated
    assert all(digest.startswith("sha256:") for digest in record.files.values())


def test_new_writes_a_single_template_manifest(tmp_path: Path) -> None:
    """`new` scaffolds one template; a second arrives via `attach` (M4)."""
    runner.invoke(app, ["new", "payment-api", "--output-dir", str(tmp_path)])

    manifest = read_manifest(tmp_path / "payment-api")
    assert manifest is not None
    assert [r.template for r in manifest.templates] == ["python-service"]


def test_new_rejects_unsupported_language(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "svc", "--language", "rust", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_new_rejects_unsupported_database(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "svc", "--database", "mysql", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 1


def test_new_rejects_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "svc").mkdir()
    result = runner.invoke(app, ["new", "svc", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1


# --------------------------------------------------------------------------
# `--type`, `--var`, and the deprecated aliases
# --------------------------------------------------------------------------


def test_new_accepts_an_explicit_type(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "svc", "--type", "python-service", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    manifest = read_manifest(tmp_path / "svc")
    assert manifest is not None
    assert manifest.templates[0].template == "python-service"


def test_new_rejects_an_unknown_type(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "svc", "--type", "rust-service", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 1
    # The error names what is available rather than only what is missing.
    assert "python-service" in result.output


def test_var_sets_a_declared_variable(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "svc", "--var", "database=none", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    manifest = read_manifest(tmp_path / "svc")
    assert manifest is not None
    assert manifest.templates[0].variables["database"] == "none"


def test_var_rejects_an_undeclared_variable(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "svc", "--var", "databse=none", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "databse" in result.output
    assert not (tmp_path / "svc").exists()


def test_var_rejects_a_value_outside_choices(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "svc", "--var", "database=mysql", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "must be one of" in result.output


def test_var_requires_key_equals_value(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "svc", "--var", "database", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "key=value" in result.output


def test_the_language_alias_still_works(tmp_path: Path) -> None:
    """Documented in the repo's dev skill, so it keeps working indefinitely."""
    result = runner.invoke(
        app, ["new", "svc", "--language", "python", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    manifest = read_manifest(tmp_path / "svc")
    assert manifest is not None
    assert manifest.templates[0].template == "python-service"
    assert "deprecated" in result.output


def test_the_database_alias_still_works(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "svc", "--database", "none", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    manifest = read_manifest(tmp_path / "svc")
    assert manifest is not None
    assert manifest.templates[0].variables["database"] == "none"
    assert "deprecated" in result.output


def test_the_documented_legacy_invocation_still_works(tmp_path: Path) -> None:
    """`ansari new my-service --language python --database postgres`, verbatim.

    This exact line is in .claude/skills/ansari-dev/SKILL.md, so it is a
    contract rather than an internal detail.
    """
    result = runner.invoke(
        app,
        [
            "new",
            "my-service",
            "--language",
            "python",
            "--database",
            "postgres",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = read_manifest(tmp_path / "my-service")
    assert manifest is not None
    assert manifest.templates[0].variables == {
        "name": "my-service",
        "language": "python",
        "database": "postgres",
    }


def test_mixing_type_and_the_old_flags_is_refused(tmp_path: Path) -> None:
    # A precedence rule here would be one nobody could remember.
    result = runner.invoke(
        app,
        [
            "new",
            "svc",
            "--type",
            "python-service",
            "--language",
            "python",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "not both" in result.output


def test_templates_command_lists_what_ships() -> None:
    result = runner.invoke(app, ["templates"])
    assert result.exit_code == 0, result.output
    assert "python-service" in result.output
    assert "--var database=<string>" in result.output


def test_cli_needs_no_edit_to_gain_a_template_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M2's acceptance criterion, asserted rather than asserted about.

    A template type that `cli/main.py` has never heard of -- with its own
    variables, its own choices, and its own destinations -- scaffolds through
    the ordinary `--type` / `--var` path.
    """
    bundled = tmp_path / "templates"
    root = bundled / "widget-module"
    (root / "sub").mkdir(parents=True)
    (root / "template.yaml").write_text(
        "name: widget-module\n"
        "version: 0.3.0\n"
        "description: A type the CLI does not know about.\n"
        "variables:\n"
        "  region:\n    type: string\n    choices: [eu-west-1, us-east-1]\n"
        "  replicas:\n    type: int\n    default: 2\n"
        "files:\n"
        "  sub/main.tf.j2: main.tf\n"
        "  sub/named.j2: widgets/{{ name }}.tf\n"
    )
    (root / "sub" / "main.tf.j2").write_text('region = "{{ region }}"\ncount = {{ replicas }}\n')
    (root / "sub" / "named.j2").write_text("# {{ name }}\n")
    monkeypatch.setattr("ansari.scaffold.template.BUNDLED_DIR", bundled)

    result = runner.invoke(
        app,
        [
            "new",
            "vpc",
            "--type",
            "widget-module",
            "--var",
            "region=eu-west-1",
            "--var",
            "replicas=5",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    repo = tmp_path / "vpc"
    assert (repo / "main.tf").read_text() == 'region = "eu-west-1"\ncount = 5\n'
    assert (repo / "widgets" / "vpc.tf").read_text() == "# vpc\n"

    manifest = read_manifest(repo)
    assert manifest is not None
    record = manifest.templates[0]
    assert record.template == "widget-module"
    assert record.version == "0.3.0"
    # The int stayed an int through the manifest, not stringified on the way in.
    assert record.variables == {"name": "vpc", "region": "eu-west-1", "replicas": 5}
    assert set(record.files) == {"main.tf", "widgets/vpc.tf"}


def test_an_unknown_type_reports_what_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "templates"
    (bundled / "widget-module").mkdir(parents=True)
    (bundled / "widget-module" / "template.yaml").write_text(
        "name: widget-module\nversion: 0.1.0\nfiles:\n  x.j2: x\n"
    )
    monkeypatch.setattr("ansari.scaffold.template.BUNDLED_DIR", bundled)

    result = runner.invoke(app, ["new", "svc", "--type", "nope", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "widget-module" in result.output
