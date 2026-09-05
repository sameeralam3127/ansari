from pathlib import Path

from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import manifest_path, read_manifest

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
    assert manifest.template == "python-service"
    assert manifest.variables == {
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
    assert set(manifest.files) == generated
    assert all(digest.startswith("sha256:") for digest in manifest.files.values())


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
