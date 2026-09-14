import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ansari.integrations.github import PullRequestError, open_pull_request, run_command


def _recorder(
    fail_on: str | None = None,
) -> tuple[list[list[str]], object]:
    calls: list[list[str]] = []

    def run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if fail_on is not None and command[1] == fail_on:
            return subprocess.CompletedProcess(list(command), 1, stdout="", stderr="boom")
        return subprocess.CompletedProcess(
            list(command), 0, stdout="https://github.com/acme/repo/pull/3\n", stderr=""
        )

    return calls, run


def test_opens_a_pull_request_in_order(tmp_path: Path) -> None:
    calls, run = _recorder()
    url = open_pull_request(tmp_path, "ansari/sync-x-2.0.0", "Sync x", "body", run=run)  # type: ignore[arg-type]

    assert url == "https://github.com/acme/repo/pull/3"
    assert [call[:2] for call in calls] == [
        ["git", "checkout"],
        ["git", "add"],
        ["git", "commit"],
        ["git", "push"],
        ["gh", "pr"],
    ]


def test_stops_at_the_first_failing_step_and_names_it(tmp_path: Path) -> None:
    calls, run = _recorder(fail_on="commit")
    with pytest.raises(PullRequestError, match="git commit -m.*boom"):
        open_pull_request(tmp_path, "b", "t", "body", run=run)  # type: ignore[arg-type]
    assert [call[1] for call in calls] == ["checkout", "add", "commit"]


def test_run_command_runs_locally(tmp_path: Path) -> None:
    result = run_command(["git", "--version"], tmp_path)
    assert result.returncode == 0
    assert "git version" in result.stdout
