from pathlib import Path

import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import manifest_path

runner = CliRunner()


def _new(root: Path, name: str, *args: str) -> Path:
    result = runner.invoke(app, ["new", name, *args, "--output-dir", str(root)])
    assert result.exit_code == 0, result.output
    return root / name


def test_a_clean_fleet_exits_zero(tmp_path: Path) -> None:
    _new(tmp_path, "payments")
    _new(tmp_path, "network", "--type", "terraform-module")

    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Fleet: 2 repos" in result.output
    assert "All 2 repos on the golden path." in result.output


def test_a_drifted_fleet_exits_non_zero_and_names_the_problem(tmp_path: Path) -> None:
    _new(tmp_path, "payments")
    scaled = _new(tmp_path, "orders")
    runner.invoke(app, ["attach", "--type", "k8s-scaling", str(scaled)])
    (scaled / "Dockerfile").write_text("FROM scratch\n")

    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])

    assert result.exit_code == 1
    assert "orders" in result.output
    assert "python-service 1.1.0 (current), 1 file edited" in result.output
    assert "k8s-scaling 0.1.0 (current)" in result.output
    assert "By template:" in result.output
    assert "python-service" in result.output and "2 attached · 0 behind · 1 edited" in result.output
    assert "1 of 2 repos off the golden path." in result.output


def test_an_unreadable_manifest_is_reported_not_skipped(tmp_path: Path) -> None:
    _new(tmp_path, "payments")
    broken = tmp_path / "broken"
    manifest_path(broken).parent.mkdir(parents=True)
    manifest_path(broken).write_text("template: [unclosed\n")

    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])

    assert result.exit_code == 1
    assert "broken" in result.output
    assert "could not read manifest" in result.output


def test_an_unresolved_template_is_reported(tmp_path: Path) -> None:
    repo = _new(tmp_path, "payments")
    document = yaml.safe_load(manifest_path(repo).read_text())
    document["templates"].append(
        {
            "template": "from-the-future",
            "version": "9.0.0",
            "rendered_at": "2026-01-01T00:00:00+00:00",
            "files": {"future.txt": "sha256:x"},
        }
    )
    manifest_path(repo).write_text(yaml.safe_dump(document))

    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])

    assert result.exit_code == 1
    assert "from-the-future unknown to this ANSARI (cannot verify)" in result.output
    assert "1 attached · cannot verify" in result.output


def test_finding_no_repos_fails(tmp_path: Path) -> None:
    """Pointed at the wrong directory, a fleet check must not report success."""
    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])
    assert result.exit_code == 1
    assert "No ANSARI repos found" in result.output


def test_a_missing_directory_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", "--fleet", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "Not a directory" in result.output


def test_a_single_repo_fleet_uses_singular_wording(tmp_path: Path) -> None:
    _new(tmp_path, "payments")
    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Fleet: 1 repo under" in result.output
    assert "All 1 repo on the golden path." in result.output


def test_check_without_fleet_is_unchanged(tmp_path: Path) -> None:
    """--fleet is additive: plain `check` on a non-repo still says so."""
    _new(tmp_path, "payments")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 1
    assert "not scaffolded by ANSARI" in result.output


def test_a_fleet_with_nothing_readable_fails_without_crashing(tmp_path: Path) -> None:
    """With no readable manifest there are no templates to summarise.

    This crashed: the summary took max() over an empty set of template names.
    """
    for name in ("broken-a", "broken-b"):
        manifest_path(tmp_path / name).parent.mkdir(parents=True)
        manifest_path(tmp_path / name).write_text("template: [unclosed\n")

    result = runner.invoke(app, ["check", "--fleet", str(tmp_path)])

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert result.output.count("could not read manifest") == 2
    assert "By template:" not in result.output
    assert "2 of 2 repos off the golden path." in result.output
