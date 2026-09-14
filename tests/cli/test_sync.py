import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import read_manifest

runner = CliRunner()

V1 = {"config.txt": "a\nb\nc\nd\ne\n", "keep.txt": "keep\n"}
V2 = {"config.txt": "a\nb\nc\nd\nE from v2\n", "keep.txt": "keep v2\n"}


def _bundled(root: Path, version: str, files: dict[str, str]) -> Path:
    template_dir = root / "kit"
    template_dir.mkdir(parents=True)
    listing = "".join(f"  {name}.j2: {name}\n" for name in files)
    (template_dir / "template.yaml").write_text(f"name: kit\nversion: {version}\nfiles:\n{listing}")
    for name, body in files.items():
        (template_dir / f"{name}.j2").write_text(body)
    return root


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *names: str) -> list[Path]:
    """Scaffold repos from kit 1.0.0 and commit them, then make 2.0.0 the bundled version."""
    monkeypatch.setattr(
        "ansari.scaffold.template.BUNDLED_DIR", _bundled(tmp_path / "v1", "1.0.0", V1)
    )
    repos = []
    for name in names or ("repo",):
        result = runner.invoke(
            app, ["new", name, "--type", "kit", "--output-dir", str(tmp_path / "work")]
        )
        assert result.exit_code == 0, result.output
        repo = tmp_path / "work" / name
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "test")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "scaffold")
        repos.append(repo)
    monkeypatch.setattr(
        "ansari.scaffold.template.BUNDLED_DIR", _bundled(tmp_path / "v2", "2.0.0", V2)
    )
    return repos


def _conflict(repo: Path) -> None:
    (repo / "config.txt").write_text("a\nb\nc\nd\ne edited here\n")
    _git(repo, "commit", "-qam", "overlapping edit")


def _snapshot(repo: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(repo)): p.read_bytes()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


def test_sync_upgrades_a_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)

    result = runner.invoke(app, ["sync", str(repo)])

    assert result.exit_code == 0, result.output
    assert "kit  1.0.0 → 2.0.0" in result.output
    assert "updated      keep.txt" in result.output
    assert "Synced." in result.output
    assert (repo / "keep.txt").read_text() == "keep v2\n"

    checked = runner.invoke(app, ["check", str(repo)])
    assert checked.exit_code == 0, checked.output


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)
    before = _snapshot(repo)

    result = runner.invoke(app, ["sync", str(repo), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "updated      keep.txt" in result.output
    assert "Dry run: nothing written." in result.output
    assert _snapshot(repo) == before


def test_a_conflict_exits_non_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)
    _conflict(repo)

    result = runner.invoke(app, ["sync", str(repo)])

    assert result.exit_code == 1
    assert "CONFLICT     config.txt" in result.output
    assert "Resolve the conflict markers in 1 file" in result.output


def test_an_up_to_date_repo_has_nothing_to_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)
    runner.invoke(app, ["sync", str(repo)])
    _git(repo, "commit", "-qam", "synced")

    result = runner.invoke(app, ["sync", str(repo)])
    assert result.exit_code == 0, result.output
    assert "Nothing to sync" in result.output


def test_uncommitted_changes_are_refused_unless_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)
    (repo / "scratch.txt").write_text("work in progress\n")

    refused = runner.invoke(app, ["sync", str(repo)])
    assert refused.exit_code == 1
    assert "uncommitted changes" in refused.output

    allowed = runner.invoke(app, ["sync", str(repo), "--allow-dirty"])
    assert allowed.exit_code == 0, allowed.output


def test_a_repo_that_is_not_in_git_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "svc", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    result = runner.invoke(app, ["sync", str(tmp_path / "svc")])
    assert result.exit_code == 1
    assert "not a git working tree" in result.output


def test_a_directory_without_a_manifest_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sync", str(tmp_path)])
    assert result.exit_code == 1
    assert "No .ansari/manifest.yaml" in result.output


def test_contradictory_flags_are_refused(tmp_path: Path) -> None:
    assert runner.invoke(app, ["sync", str(tmp_path), "--pr", "--dry-run"]).exit_code == 1
    assert runner.invoke(app, ["sync", str(tmp_path), "--pr", "--allow-dirty"]).exit_code == 1


# --------------------------------------------------------------------------
# --pr
# --------------------------------------------------------------------------


def _fake_github(monkeypatch: pytest.MonkeyPatch, *, fail_on: str | None = None) -> list[list[str]]:
    """Run local git for real; record push and gh instead of reaching GitHub."""
    calls: list[list[str]] = []

    def fake(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        command = list(command)
        calls.append(command)
        if fail_on is not None and fail_on in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="remote rejected")
        if command[0] == "git" and command[1] != "push":
            return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
        return subprocess.CompletedProcess(
            command, 0, stdout="https://github.com/acme/repo/pull/7\n", stderr=""
        )

    monkeypatch.setattr("ansari.integrations.github.run_command", fake)
    return calls


def test_pr_commits_on_a_branch_and_opens_a_pull_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)
    calls = _fake_github(monkeypatch)

    result = runner.invoke(app, ["sync", str(repo), "--pr"])

    assert result.exit_code == 0, result.output
    assert "Opened https://github.com/acme/repo/pull/7" in result.output
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "ansari/sync-kit-2.0.0"
    assert _git(repo, "log", "-1", "--format=%s").strip() == "Sync kit to 2.0.0"
    assert _git(repo, "status", "--porcelain").strip() == ""

    assert ["git", "push", "-u", "origin", "ansari/sync-kit-2.0.0"] in calls
    gh = next(call for call in calls if call[0] == "gh")
    assert gh[gh.index("--title") + 1] == "Sync kit to 2.0.0"
    assert "updated `keep.txt`" in gh[gh.index("--body") + 1]


def test_pr_is_not_opened_when_there_are_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Committing conflict markers is worse than no pull request."""
    (repo,) = _repos(tmp_path, monkeypatch)
    _conflict(repo)
    calls = _fake_github(monkeypatch)
    before = _snapshot(repo)

    result = runner.invoke(app, ["sync", str(repo), "--pr"])

    assert result.exit_code == 1
    assert "Not opening a pull request" in result.output
    assert calls == []
    assert _snapshot(repo) == before


def test_a_failed_push_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo,) = _repos(tmp_path, monkeypatch)
    _fake_github(monkeypatch, fail_on="push")

    result = runner.invoke(app, ["sync", str(repo), "--pr"])

    assert result.exit_code == 1
    assert "couldn't open the pull request" in result.output
    assert "remote rejected" in result.output


# --------------------------------------------------------------------------
# --fleet
# --------------------------------------------------------------------------


def test_fleet_syncs_each_repo_and_reports_the_ones_needing_attention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean, conflicted = _repos(tmp_path, monkeypatch, "clean", "conflicted")
    _conflict(conflicted)

    result = runner.invoke(app, ["sync", "--fleet", str(tmp_path / "work")])

    assert result.exit_code == 1
    assert "== clean ==" in result.output
    assert "== conflicted ==" in result.output
    assert "1 of 2 repos need attention." in result.output

    upgraded = read_manifest(clean)
    assert upgraded is not None
    assert upgraded.templates[0].version == "2.0.0"


def test_fleet_pr_opens_one_pull_request_per_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repos(tmp_path, monkeypatch, "orders", "payments")
    calls = _fake_github(monkeypatch)

    result = runner.invoke(app, ["sync", "--fleet", str(tmp_path / "work"), "--pr"])

    assert result.exit_code == 0, result.output
    assert sum(1 for call in calls if call[0] == "gh") == 2
    assert "All 2 repos synced or already current." in result.output


def test_fleet_with_no_repos_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sync", "--fleet", str(tmp_path)])
    assert result.exit_code == 1
    assert "No ANSARI repos found" in result.output


def test_fleet_on_a_missing_directory_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sync", "--fleet", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "Not a directory" in result.output
