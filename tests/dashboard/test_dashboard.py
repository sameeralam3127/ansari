"""The fleet dashboard: health, adoption, and drift by template, from a real scan."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import yaml
from markupsafe import escape
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.dashboard import (
    BEHIND,
    CURRENT,
    EDITED,
    UNREADABLE,
    UNVERIFIABLE,
    Segment,
    build_dashboard,
    render_dashboard,
)
from ansari.scaffold import (
    SCHEMA_VERSION,
    Manifest,
    bundled_version,
    check_fleet,
    manifest_path,
    read_manifest,
    write_manifest,
)

runner = CliRunner()
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
SERVICE = bundled_version("python-service")


def _new(root: Path, name: str, *args: str) -> Path:
    result = runner.invoke(app, ["new", name, *args, "--output-dir", str(root)])
    assert result.exit_code == 0, result.output
    return root / name


def _set_version(repo: Path, version: str) -> None:
    manifest = read_manifest(repo)
    assert manifest is not None
    first = replace(manifest.templates[0], version=version)
    write_manifest(
        repo, Manifest(schema=SCHEMA_VERSION, templates=[first, *manifest.templates[1:]])
    )


def _fleet(root: Path) -> Path:
    """One repo in every state, and a template attached alongside another."""
    _new(root, "clean")

    both = _new(root, "both")
    _set_version(both, "0.9.0")
    (both / "Dockerfile").write_text("edited\n")

    scaled = _new(root, "scaled")
    assert runner.invoke(app, ["attach", "--type", "k8s-scaling", str(scaled)]).exit_code == 0
    hpa = scaled / "helm/scaled/templates/hpa.yaml"
    hpa.write_text(hpa.read_text() + "# tuned by hand\n")

    _new(root, "module", "--type", "terraform-module")

    future = _new(root, "future")
    manifest = read_manifest(future)
    assert manifest is not None
    entries = [record.to_dict() for record in manifest.templates]
    entries.append(
        {
            "template": "from-the-future",
            "version": "9.0.0",
            "rendered_at": "2026-01-01T00:00:00+00:00",
            "files": {"future.txt": "sha256:x"},
        }
    )
    manifest_path(future).write_text(yaml.safe_dump({"schema": 2, "templates": entries}))

    broken = root / "bro<k>en"
    manifest_path(broken).parent.mkdir(parents=True)
    manifest_path(broken).write_text("template: [unclosed\n")
    return root


# --------------------------------------------------------------------------
# What the page is built from
# --------------------------------------------------------------------------


def test_every_repo_is_counted_once_under_its_most_severe_state(tmp_path: Path) -> None:
    page = build_dashboard(check_fleet(_fleet(tmp_path), bundled_version), NOW)

    assert {row.label: row.state for row in page.repos} == {
        "clean": CURRENT,
        "both": BEHIND,  # behind and edited: behind is what sync can act on
        "scaled": EDITED,
        "module": CURRENT,
        "future": UNVERIFIABLE,
        "bro<k>en": UNREADABLE,
    }
    assert sum(segment.count for segment in page.health) == page.total == 6
    assert (page.on_path, page.readable) == (2, 5)


def test_adoption_counts_repos_and_drift_counts_attachments(tmp_path: Path) -> None:
    page = build_dashboard(check_fleet(_fleet(tmp_path), bundled_version), NOW)
    rows = {row.template: row for row in page.templates}

    assert set(rows) == {"python-service", "k8s-scaling", "terraform-module", "from-the-future"}

    service = rows["python-service"]
    assert (service.repos, service.attached) == (4, 4)
    assert service.adoption == 80.0  # 4 of the 5 readable repos
    assert service.drift == (Segment(CURRENT, 3), Segment(BEHIND, 1))
    assert service.versions == ((SERVICE, 3), ("0.9.0", 1))
    assert service.summary == "4 attached · 1 behind · 1 edited"

    assert rows["k8s-scaling"].drift == (Segment(EDITED, 1),)

    unknown = rows["from-the-future"]
    assert unknown.current_version is None
    assert unknown.versions == ()
    assert unknown.drift == (Segment(UNVERIFIABLE, 1),)
    assert unknown.summary == "1 attached · cannot verify"


def test_the_summary_matches_check_fleet(tmp_path: Path) -> None:
    """The page and the terminal come from one report, so they can't disagree."""
    root = _fleet(tmp_path)
    page = build_dashboard(check_fleet(root, bundled_version), NOW)
    printed = runner.invoke(app, ["check", "--fleet", str(root)]).output
    lines = {" ".join(line.split()) for line in printed.splitlines()}

    for row in page.templates:
        assert f"{row.template} {row.summary}" in lines


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------


def test_the_page_names_every_repo_and_escapes_what_it_read_from_disk(tmp_path: Path) -> None:
    page = build_dashboard(check_fleet(_fleet(tmp_path), bundled_version), NOW)
    html = render_dashboard(page)

    for row in page.repos:
        assert str(escape(row.label)) in html
    assert "bro<k>en" not in html
    assert "bro&lt;k&gt;en" in html
    assert "ansari sync --fleet --dry-run" in html
    assert "newer ANSARI" in html


def test_a_clean_fleet_suggests_nothing(tmp_path: Path) -> None:
    _new(tmp_path, "a")
    _new(tmp_path, "b", "--type", "ansible-role")
    html = render_dashboard(build_dashboard(check_fleet(tmp_path, bundled_version), NOW))

    assert "of 2 repos on the golden path" in html
    assert "ansari sync" not in html


# --------------------------------------------------------------------------
# `ansari dashboard`
# --------------------------------------------------------------------------


def test_dashboard_writes_the_page_and_exits_zero_despite_drift(tmp_path: Path) -> None:
    root = _fleet(tmp_path / "fleet")
    output = tmp_path / "reports" / "fleet.html"

    result = runner.invoke(app, ["dashboard", str(root), "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert f"Wrote {output}" in result.output
    assert "2 of 6 repos on the golden path" in result.output
    assert output.read_text().startswith("<!doctype html>")


def test_dashboard_refuses_an_empty_fleet_and_writes_nothing(tmp_path: Path) -> None:
    output = tmp_path / "fleet.html"
    result = runner.invoke(app, ["dashboard", str(tmp_path), "--output", str(output)])

    assert result.exit_code == 1
    assert "No ANSARI repos found" in result.output
    assert not output.exists()


def test_dashboard_refuses_a_path_that_is_not_a_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["dashboard", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "Not a directory" in result.output


def test_dashboard_reports_an_output_it_cannot_write(tmp_path: Path) -> None:
    root = _new(tmp_path, "a").parent
    result = runner.invoke(app, ["dashboard", str(root), "--output", str(tmp_path)])
    assert result.exit_code == 1
    assert "Could not write" in result.output
