from typer.testing import CliRunner

from ansari.main import app

runner = CliRunner()


def test_version_command_shows_project_name() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "ANSARI" in result.stdout


def test_check_command_reports_known_resource() -> None:
    result = runner.invoke(app, ["check", "eks-cluster-01"])

    assert result.exit_code == 0
    assert "Reliability Check: eks-cluster-01" in result.stdout
    assert "kubernetes-cluster" in result.stdout


def test_check_command_supports_verbose_mode() -> None:
    result = runner.invoke(app, ["check", "payment-pod", "--verbose"])

    assert result.exit_code == 0
    assert "Verbose mode enabled" in result.stdout


def test_examples_command_shows_copy_pasteable_commands() -> None:
    result = runner.invoke(app, ["examples"])

    assert result.exit_code == 0
    assert "ANSARI Examples" in result.stdout
    assert "poetry run ansari check eks-cluster-01" in result.stdout
