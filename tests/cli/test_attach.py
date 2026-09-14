from pathlib import Path

import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import manifest_path, read_manifest

runner = CliRunner()
HPA = "helm/payment-api/templates/hpa.yaml"


def _service(tmp_path: Path, name: str = "payment-api") -> Path:
    result = runner.invoke(app, ["new", name, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path / name


def _snapshot(repo: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }


def test_attach_then_check_reports_both_templates(tmp_path: Path) -> None:
    """M4's acceptance criterion: one repo, two templates, both reported."""
    repo = _service(tmp_path)

    attached = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    assert attached.exit_code == 0, attached.output
    assert "Attached k8s-scaling v0.1.0" in attached.output
    assert HPA in attached.output
    assert "now tracks 2 templates" in attached.output

    checked = runner.invoke(app, ["check", str(repo)])
    assert checked.exit_code == 0, checked.output
    assert "Templates: 2 attached" in checked.output
    assert "python-service" in checked.output
    assert "k8s-scaling" in checked.output
    assert "On the golden path" in checked.output


def test_check_names_the_attached_file_that_was_edited(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    (repo / HPA).write_text((repo / HPA).read_text() + "# tuned by hand\n")

    result = runner.invoke(app, ["check", str(repo)])
    assert result.exit_code == 1
    assert f"modified: {HPA}" in result.output


def test_attach_passes_variables_through(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    result = runner.invoke(
        app, ["attach", "--type", "k8s-scaling", str(repo), "--var", "max_replicas=20"]
    )
    assert result.exit_code == 0, result.output
    assert "maxReplicas: 20" in (repo / "helm/payment-api/autoscaling.yaml").read_text()


def test_attach_name_overrides_the_recorded_name(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    result = runner.invoke(
        app, ["attach", "--type", "k8s-scaling", str(repo), "--name", "payments-v2"]
    )
    assert result.exit_code == 0, result.output
    assert (repo / "helm/payments-v2/templates/hpa.yaml").is_file()


def test_attach_reports_upgrading_a_v1_manifest(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    record = read_manifest(repo).templates[0]  # type: ignore[union-attr]
    manifest_path(repo).write_text(
        yaml.safe_dump(
            {
                "template": record.template,
                "version": record.version,
                "rendered_at": record.rendered_at.isoformat(),
                "variables": record.variables,
                "files": record.files,
            }
        )
    )

    result = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    assert result.exit_code == 0, result.output
    assert "Upgraded .ansari/manifest.yaml to schema 2" in result.output


def test_attach_without_a_manifest_points_at_new(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    result = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(tmp_path / "plain")])
    assert result.exit_code == 1
    assert "ansari new" in result.output


def test_attach_reports_a_malformed_manifest(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    manifest_path(repo).write_text("template: [unclosed\n")
    result = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    assert result.exit_code == 1
    assert "Could not read manifest" in result.output


def test_attach_reports_a_manifest_from_a_newer_ansari(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    manifest_path(repo).write_text("schema: 99\ntemplates: []\n")
    result = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    assert result.exit_code == 1
    assert "Upgrade ANSARI" in result.output


def test_attach_rejects_an_unknown_type(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    result = runner.invoke(app, ["attach", "--type", "nope", str(repo)])
    assert result.exit_code == 1
    assert "k8s-scaling" in result.output


def test_attach_rejects_a_bad_variable_and_writes_nothing(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    before = _snapshot(repo)
    result = runner.invoke(
        app, ["attach", "--type", "k8s-scaling", str(repo), "--var", "max_replicas=lots"]
    )
    assert result.exit_code == 1
    assert "integer" in result.output
    assert _snapshot(repo) == before


def test_attach_refuses_an_unresolved_entry_and_names_the_override(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    manifest = read_manifest(repo)
    assert manifest is not None
    entries = [r.to_dict() for r in manifest.templates]
    entries.append(
        {
            "template": "from-the-future",
            "version": "9.0.0",
            "rendered_at": "2026-01-01T00:00:00+00:00",
            "files": {"future.tf": "sha256:x"},
        }
    )
    manifest_path(repo).write_text(yaml.safe_dump({"schema": 2, "templates": entries}))

    refused = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    assert refused.exit_code == 1
    assert "--allow-unresolved" in refused.output

    forced = runner.invoke(
        app, ["attach", "--type", "k8s-scaling", str(repo), "--allow-unresolved"]
    )
    assert forced.exit_code == 0, forced.output


def test_attach_reports_a_conflict_with_an_untracked_file(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    (repo / HPA).write_text("# mine\n")
    result = runner.invoke(app, ["attach", "--type", "k8s-scaling", str(repo)])
    assert result.exit_code == 1
    assert "not tracked by ANSARI" in result.output
    assert (repo / HPA).read_text() == "# mine\n"


def test_new_refuses_an_attach_only_template(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["new", "orders", "--type", "k8s-scaling", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "ansari attach --type k8s-scaling" in result.output
    assert not (tmp_path / "orders").exists()


def test_templates_marks_attach_only_templates() -> None:
    result = runner.invoke(app, ["templates"])
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.output.splitlines() if ln.startswith("k8s-scaling"))
    assert "(attach only)" in line
    service = next(ln for ln in result.output.splitlines() if ln.startswith("python-service"))
    assert "(attach only)" not in service
