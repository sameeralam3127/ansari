from pathlib import Path

from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import manifest_path

runner = CliRunner()


def _scaffold(tmp_path: Path, name: str = "payment-api") -> Path:
    result = runner.invoke(app, ["new", name, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path / name


def test_check_passes_on_a_freshly_scaffolded_service(tmp_path: Path) -> None:
    service_dir = _scaffold(tmp_path)
    result = runner.invoke(app, ["check", str(service_dir)])
    assert result.exit_code == 0, result.output
    assert "On the golden path" in result.output


def test_check_reports_a_hand_edited_file(tmp_path: Path) -> None:
    service_dir = _scaffold(tmp_path)
    dockerfile = service_dir / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + "\n# edited by a developer\n")

    result = runner.invoke(app, ["check", str(service_dir)])
    assert result.exit_code == 1
    assert "modified locally" in result.output
    assert "Dockerfile" in result.output


def test_check_reports_a_deleted_file(tmp_path: Path) -> None:
    service_dir = _scaffold(tmp_path)
    (service_dir / "README.md").unlink()

    result = runner.invoke(app, ["check", str(service_dir)])
    assert result.exit_code == 1
    assert "deleted locally" in result.output
    assert "README.md" in result.output


def test_check_fails_clearly_without_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "not-ours").mkdir()
    result = runner.invoke(app, ["check", str(tmp_path / "not-ours")])
    assert result.exit_code == 1
    assert "not scaffolded by ANSARI" in result.output


def test_check_distinguishes_a_broken_manifest_from_a_missing_one(tmp_path: Path) -> None:
    service_dir = _scaffold(tmp_path)
    manifest_path(service_dir).write_text("template: [unclosed\n")

    result = runner.invoke(app, ["check", str(service_dir)])
    assert result.exit_code == 1
    assert "Could not read manifest" in result.output
