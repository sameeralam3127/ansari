"""GitHub, through the git and gh command-line tools.

This drives `git` and `gh` rather than calling GitHub's API directly: those tools
already carry the user's credentials, so ANSARI never holds a token. Every command
goes through a runner, so tests can see exactly what would run without pushing
anything anywhere.
"""

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


class PullRequestError(Exception):
    """A step of opening a pull request failed."""


def run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, check=False)


def _run_step(runner: Runner, command: list[str], repo_dir: Path) -> str:
    result = runner(command, repo_dir)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PullRequestError(f"`{' '.join(command[:3])}` failed: {detail}")
    return result.stdout


def open_pull_request(
    repo_dir: Path, branch: str, title: str, body: str, run: Runner | None = None
) -> str:
    """Commit the working tree on a new branch, push it, and open a pull request.

    Returns the pull request's URL. Stops at the first step that fails, and says
    which.
    """
    # Looked up at call time, so a test can replace run_command on the module.
    runner = run if run is not None else run_command
    for command in (
        ["git", "checkout", "-b", branch],
        ["git", "add", "-A", "--", "."],
        ["git", "commit", "-m", title],
        ["git", "push", "-u", "origin", branch],
    ):
        _run_step(runner, command, repo_dir)
    output = _run_step(
        runner,
        ["gh", "pr", "create", "--head", branch, "--title", title, "--body", body],
        repo_dir,
    )
    lines = output.strip().splitlines()
    return lines[-1] if lines else ""
