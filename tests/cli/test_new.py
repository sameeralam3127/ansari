from pathlib import Path

from typer.testing import CliRunner

from ansari.cli.main import app

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


def test_new_rejects_unsupported_language(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "svc", "--language", "rust", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_new_rejects_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "svc").mkdir()
    result = runner.invoke(app, ["new", "svc", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1
