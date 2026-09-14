"""Fleet drift: discovery, per-repo results, and the by-template summary."""

from dataclasses import replace
from pathlib import Path

import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import (
    SCHEMA_VERSION,
    Manifest,
    bundled_version,
    check_fleet,
    discover_repos,
    manifest_path,
    read_manifest,
    write_manifest,
)

runner = CliRunner()


def _new(root: Path, name: str, *args: str) -> Path:
    result = runner.invoke(app, ["new", name, *args, "--output-dir", str(root)])
    assert result.exit_code == 0, result.output
    return root / name


def _plant_manifest(directory: Path) -> None:
    manifest_path(directory).parent.mkdir(parents=True)
    manifest_path(directory).write_text("schema: 2\ntemplates: []\n")


def _set_version(repo: Path, version: str) -> None:
    manifest = read_manifest(repo)
    assert manifest is not None
    first = replace(manifest.templates[0], version=version)
    write_manifest(
        repo, Manifest(schema=SCHEMA_VERSION, templates=[first, *manifest.templates[1:]])
    )


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


def test_discovery_finds_repos_at_any_depth_including_the_root(tmp_path: Path) -> None:
    _plant_manifest(tmp_path)
    _plant_manifest(tmp_path / "services" / "payments")
    _plant_manifest(tmp_path / "infra" / "modules" / "network")

    assert discover_repos(tmp_path) == [
        tmp_path,
        tmp_path / "infra" / "modules" / "network",
        tmp_path / "services" / "payments",
    ]


def test_discovery_skips_vcs_dependency_and_tool_directories(tmp_path: Path) -> None:
    for hidden in (".git/x", "node_modules/pkg", ".terraform/modules/m", ".venv/lib"):
        _plant_manifest(tmp_path / hidden)
    _plant_manifest(tmp_path / "real")

    assert discover_repos(tmp_path) == [tmp_path / "real"]


def test_discovery_does_not_follow_symlinked_directories(tmp_path: Path) -> None:
    """A link loop must neither hang the scan nor count a repo twice."""
    _plant_manifest(tmp_path / "repo")
    (tmp_path / "repo" / "loop").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "alias").symlink_to(tmp_path / "repo", target_is_directory=True)

    assert discover_repos(tmp_path) == [tmp_path / "repo"]


def test_discovery_of_an_empty_tree_finds_nothing(tmp_path: Path) -> None:
    assert discover_repos(tmp_path) == []


# --------------------------------------------------------------------------
# A mixed fleet
# --------------------------------------------------------------------------


def _mixed_fleet(root: Path) -> None:
    _new(root, "svc-clean")

    scaled = _new(root, "svc-scaled")
    assert runner.invoke(app, ["attach", "--type", "k8s-scaling", str(scaled)]).exit_code == 0
    hpa = scaled / "helm/svc-scaled/templates/hpa.yaml"
    hpa.write_text(hpa.read_text() + "# tuned by hand\n")

    network = _new(root, "network", "--type", "terraform-module")
    _set_version(network, "0.0.1")

    _new(root, "disk-health", "--type", "ansible-role")

    future = _new(root, "from-future")
    manifest = read_manifest(future)
    assert manifest is not None
    entries = [r.to_dict() for r in manifest.templates]
    entries.append(
        {
            "template": "from-the-future",
            "version": "9.0.0",
            "rendered_at": "2026-01-01T00:00:00+00:00",
            "files": {"future.txt": "sha256:x"},
        }
    )
    manifest_path(future).write_text(yaml.safe_dump({"schema": 2, "templates": entries}))

    broken = root / "broken"
    manifest_path(broken).parent.mkdir(parents=True)
    manifest_path(broken).write_text("template: [unclosed\n")


def test_a_mixed_fleet_reports_each_repo(tmp_path: Path) -> None:
    _mixed_fleet(tmp_path)
    fleet = check_fleet(tmp_path, bundled_version)

    by_name = {result.path.name: result for result in fleet.repos}
    assert set(by_name) == {
        "svc-clean",
        "svc-scaled",
        "network",
        "disk-health",
        "from-future",
        "broken",
    }
    assert {name for name, result in by_name.items() if result.clean} == {
        "svc-clean",
        "disk-health",
    }
    assert not fleet.clean

    # An unreadable manifest is reported, never silently skipped.
    assert by_name["broken"].report is None
    assert by_name["broken"].error is not None


def test_the_summary_counts_attachments_per_template(tmp_path: Path) -> None:
    """M7's acceptance criterion: mixed types and multi-template repos, counted right."""
    _mixed_fleet(tmp_path)
    summaries = check_fleet(tmp_path, bundled_version).by_template()

    assert set(summaries) == {
        "python-service",
        "k8s-scaling",
        "terraform-module",
        "ansible-role",
        "from-the-future",
    }
    service = summaries["python-service"]
    assert (service.attached, service.behind, service.edited) == (3, 0, 0)

    scaling = summaries["k8s-scaling"]
    assert (scaling.attached, scaling.behind, scaling.edited) == (1, 0, 1)

    module = summaries["terraform-module"]
    assert (module.attached, module.behind, module.edited) == (1, 1, 0)

    unknown = summaries["from-the-future"]
    assert (unknown.attached, unknown.unresolved) == (1, 1)


def test_a_clean_fleet_is_clean(tmp_path: Path) -> None:
    _new(tmp_path, "a")
    _new(tmp_path, "b", "--type", "terraform-module")
    fleet = check_fleet(tmp_path, bundled_version)
    assert fleet.clean
    assert fleet.off_path == []


def test_an_empty_fleet_is_not_clean(tmp_path: Path) -> None:
    """Finding nothing is a misconfiguration to surface, not a pass."""
    fleet = check_fleet(tmp_path, bundled_version)
    assert fleet.repos == []
    assert not fleet.clean
