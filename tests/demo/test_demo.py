"""`make demo`'s fleet: every template type and every state, on real history."""

import runpy
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ansari.dashboard import STATES, build_dashboard
from ansari.demo import MARKER, RECIPES, DemoError, main, old_python_service, seed_fleet
from ansari.scaffold import (
    available_templates,
    bundled_version,
    check_fleet,
    file_digest,
    find_bundled_template,
    generate,
    plan_sync,
    read_manifest,
)
from ansari.scaffold.sync import MERGE, UPDATE

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="the demo commits with git")

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "python-service.yaml"


@pytest.fixture(scope="module")
def fleet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("demo") / "fleet"
    seed_fleet(root)
    return root


def test_every_template_type_and_every_state_appears(fleet: Path) -> None:
    page = build_dashboard(check_fleet(fleet, bundled_version), datetime.now(UTC))

    assert {row.state for row in page.repos} == set(STATES)
    assert set(available_templates()) <= {row.template for row in page.templates}
    assert page.total == len(RECIPES)


def test_each_repo_tells_the_story_it_is_listed_with(fleet: Path) -> None:
    page = build_dashboard(check_fleet(fleet, bundled_version), datetime.now(UTC))
    assert {row.label: row.state for row in page.repos} == {
        "services/payments": "current",
        "services/orders": "behind",
        "services/checkout": "behind",
        "services/search": "edited",
        "infra/network": "current",
        "infra/dns": "edited",
        "roles/disk-health": "current",
        "roles/ntp": "unverifiable",
        "legacy/reports": "unreadable",
    }


def test_the_old_python_service_is_the_real_1_0_0(tmp_path: Path) -> None:
    """The behind repos are what 1.0.0 generated, byte for byte, not a relabelled 1.1.0."""
    old = old_python_service(tmp_path)
    golden = yaml.safe_load(GOLDEN.read_text())["1.0.0"]
    repo = tmp_path / str(golden["variables"]["name"])

    written = generate(old, dict(golden["variables"]), repo)

    assert old.version == "1.0.0"
    assert {path: file_digest(repo / path) for path in written} == golden["files"]


def test_sync_can_upgrade_the_behind_repos_keeping_the_hand_edit(fleet: Path) -> None:
    orders = fleet / "services/orders"
    manifest = read_manifest(orders)
    assert manifest is not None
    plan = plan_sync(orders, manifest, find_bundled_template)
    kinds = {action.path: action.kind for t in plan.templates for action in t.actions}
    assert kinds["helm/orders/templates/deployment.yaml"] == UPDATE
    assert plan.clean

    checkout = fleet / "services/checkout"
    manifest = read_manifest(checkout)
    assert manifest is not None
    plan = plan_sync(checkout, manifest, find_bundled_template)
    kinds = {action.path: action.kind for t in plan.templates for action in t.actions}
    assert kinds["helm/checkout/values.yaml"] == MERGE
    assert plan.clean


def test_seeding_again_replaces_the_previous_demo(tmp_path: Path) -> None:
    root = tmp_path / "fleet"
    seed_fleet(root)
    (root / "stray.txt").write_text("left by hand\n")

    seed_fleet(root)

    assert (root / MARKER).is_file()
    assert not (root / "stray.txt").exists()


def test_refuses_a_directory_the_demo_did_not_create(tmp_path: Path) -> None:
    (tmp_path / "precious.txt").write_text("keep me\n")

    with pytest.raises(DemoError, match="wasn't seeded by the demo"):
        seed_fleet(tmp_path)

    assert (tmp_path / "precious.txt").read_text() == "keep me\n"


def test_refuses_a_file(tmp_path: Path) -> None:
    target = tmp_path / "fleet"
    target.write_text("")
    with pytest.raises(DemoError, match="not a directory"):
        seed_fleet(target)


def test_needs_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ansari.demo.shutil.which", lambda _: None)
    with pytest.raises(DemoError, match="needs git"):
        seed_fleet(tmp_path / "fleet")
    assert not (tmp_path / "fleet").exists()


def test_main_lists_what_it_seeded(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "fleet")]) == 0
    out = capsys.readouterr().out
    assert f"Seeded {len(RECIPES)} repos" in out
    assert "python-service 1.0.0, never upgraded" in out


def test_main_reports_a_failed_git_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(root: Path) -> None:
        raise subprocess.CalledProcessError(128, ["git", "commit"], stderr=b"fatal: no identity")

    monkeypatch.setattr("ansari.demo.seed_fleet", fail)

    assert main([str(tmp_path / "fleet")]) == 1
    assert "fatal: no identity" in capsys.readouterr().err


def test_module_entry_point_exits_non_zero_on_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "precious.txt").write_text("keep me\n")
    monkeypatch.setattr(sys, "argv", ["ansari.demo", str(tmp_path)])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("ansari.demo", run_name="__main__")

    assert exit_info.value.code == 1
    assert "refusing to replace it" in capsys.readouterr().err
