import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SCRIPT = REPO_ROOT / "examples" / "custom_checker.py"


def test_custom_checker_example_runs_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLE_SCRIPT), "payments-lambda-fn"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "aws-lambda" in result.stdout
    assert "payments-lambda-fn" in result.stdout


def test_custom_checker_example_falls_back_to_default_checkers() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLE_SCRIPT), "eks-cluster-01"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "kubernetes-cluster" in result.stdout
