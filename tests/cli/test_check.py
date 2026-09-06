from pathlib import Path

import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import manifest_path, read_manifest

runner = CliRunner()

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
V1_FIXTURE = FIXTURES / "manifest_v1_python_service.yaml"


def _scaffold(tmp_path: Path, name: str = "payment-api") -> Path:
    result = runner.invoke(app, ["new", name, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path / name


def _downgrade_to_v1(repo: Path) -> None:
    """Rewrite a repo's manifest into the pre-migration shape.

    This is exactly what a repo scaffolded by an older ANSARI looks like on
    disk, so a test built on it stays honest as the templates change -- unlike a
    hand-written approximation that would drift from reality.
    """
    manifest = read_manifest(repo)
    assert manifest is not None
    record = manifest.templates[0]
    manifest_path(repo).write_text(
        yaml.safe_dump(
            {
                "template": record.template,
                "version": record.version,
                "rendered_at": record.rendered_at.isoformat(),
                "variables": record.variables,
                "files": record.files,
            },
            sort_keys=False,
        )
    )


def test_check_passes_on_a_freshly_scaffolded_service(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 0, result.output
    assert "On the golden path" in result.output


def test_check_reports_a_hand_edited_file(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    dockerfile = repo / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + "\n# edited by a developer\n")

    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 1
    assert "modified locally" in result.output
    assert "Dockerfile" in result.output


def test_check_reports_a_deleted_file(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    (repo / "README.md").unlink()

    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 1
    assert "deleted locally" in result.output
    assert "README.md" in result.output


def test_check_fails_clearly_without_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "not-ours").mkdir()
    result = runner.invoke(app, ["check", str(tmp_path / "not-ours")])
    assert result.exit_code == 1
    assert "not scaffolded by ANSARI" in result.output


def test_check_distinguishes_a_broken_manifest_from_a_missing_one(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    manifest_path(repo).write_text("template: [unclosed\n")

    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 1
    assert "Could not read manifest" in result.output


# --------------------------------------------------------------------------
# Schema-1 repos keep working, and keep printing what they printed before
# --------------------------------------------------------------------------


def test_check_passes_on_a_v1_manifest(tmp_path: Path) -> None:
    """The compatibility promise, end to end through the CLI."""
    repo = _scaffold(tmp_path)
    _downgrade_to_v1(repo)

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 0, result.output
    assert "On the golden path" in result.output


def test_v1_and_v2_repos_print_identically(tmp_path: Path) -> None:
    """A single-template repo's output must not change with the schema.

    Existing CI greps this output, so the migration has to be invisible to it.
    """
    v2_repo = _scaffold(tmp_path / "v2", "svc")
    v1_repo = _scaffold(tmp_path / "v1", "svc")
    _downgrade_to_v1(v1_repo)

    v2_out = runner.invoke(app, ["check", str(v2_repo)]).output
    v1_out = runner.invoke(app, ["check", str(v1_repo)]).output

    assert v1_out == v2_out
    assert v1_out.startswith("Template: python-service")


def test_check_detects_drift_in_a_v1_repo(tmp_path: Path) -> None:
    """Reading a v1 manifest is not enough -- its hashes must still be compared."""
    repo = _scaffold(tmp_path)
    _downgrade_to_v1(repo)
    (repo / "Dockerfile").write_text("FROM scratch\n")

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 1
    assert "modified locally" in result.output
    assert "Dockerfile" in result.output


def test_check_reads_the_golden_v1_fixture(tmp_path: Path) -> None:
    """The real pre-migration manifest, through the CLI.

    Its files are absent here, so every one should report as deleted -- which
    proves the file list was read, not merely that the document parsed.
    """
    repo = tmp_path / "legacy-svc"
    (repo / ".ansari").mkdir(parents=True)
    manifest_path(repo).write_text(V1_FIXTURE.read_text())

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 1
    assert "7 file(s) deleted locally" in result.output
    assert "Template: python-service" in result.output


# --------------------------------------------------------------------------
# Multi-template and unresolved
# --------------------------------------------------------------------------


def _write_v2(repo: Path, entries: list[dict[str, object]]) -> None:
    manifest_path(repo).write_text(yaml.safe_dump({"schema": 2, "templates": entries}))


def test_check_reports_each_attached_template(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    manifest = read_manifest(repo)
    assert manifest is not None
    record = manifest.templates[0]

    (repo / "helm" / "payment-api" / "templates" / "hpa.yaml").write_text("kind: HPA\n")
    _write_v2(
        repo,
        [
            record.to_dict(),
            {
                "template": "k8s-scaling",
                "version": "0.1.0",
                "rendered_at": "2026-01-01T00:00:00+00:00",
                "variables": {},
                "files": {"helm/payment-api/templates/hpa.yaml": "sha256:stale"},
            },
        ],
    )

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 1
    assert "2 attached" in result.output
    assert "python-service" in result.output
    assert "k8s-scaling" in result.output


def test_an_unresolved_template_exits_non_zero(tmp_path: Path) -> None:
    """A repo scaffolded by a newer ANSARI must not be reported clean.

    Everything this build understands about the repo is fine, which is exactly
    why silently passing would be the dangerous outcome.
    """
    repo = _scaffold(tmp_path)
    manifest = read_manifest(repo)
    assert manifest is not None

    _write_v2(
        repo,
        [
            manifest.templates[0].to_dict(),
            {
                "template": "terraform-module",
                "version": "0.1.0",
                "rendered_at": "2026-01-01T00:00:00+00:00",
                "variables": {},
                "files": {"main.tf": "sha256:unknown"},
            },
        ],
    )

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 1
    assert "cannot verify" in result.output.lower()
    assert "terraform-module" in result.output


def test_a_manifest_from_a_newer_ansari_is_refused_clearly(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    manifest_path(repo).write_text("schema: 99\ntemplates: []\n")

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 1
    assert "99" in result.output
    assert "Upgrade ANSARI" in result.output
    # Not the generic parse-failure message: this file is fine, we are behind.
    assert "Could not read manifest" not in result.output


def test_overlapping_paths_in_a_manifest_are_refused(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    _write_v2(
        repo,
        [
            {
                "template": "a",
                "version": "1.0.0",
                "rendered_at": "2026-01-01T00:00:00+00:00",
                "files": {"README.md": "sha256:x"},
            },
            {
                "template": "b",
                "version": "1.0.0",
                "rendered_at": "2026-01-01T00:00:00+00:00",
                "files": {"README.md": "sha256:y"},
            },
        ],
    )

    result = runner.invoke(app, ["check", str(repo)])

    assert result.exit_code == 1
    assert "more than one template" in result.output
