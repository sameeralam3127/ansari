from ansari.models import HealthStatus
from ansari.modules.checkers.terraform import TerraformChecker


def test_terraform_checker_matches_terraform_and_tfstate_names() -> None:
    checker = TerraformChecker()

    assert checker.matches("terraform-prod-state")
    assert checker.matches("app-tfstate")
    assert not checker.matches("payment-pod")


def test_terraform_checker_reports_unknown_drift_status() -> None:
    checker = TerraformChecker()

    health = checker.check("terraform-prod-state")

    assert health.resource_type == "terraform-state"
    assert health.status == HealthStatus.UNKNOWN
    assert health.signals["drift_status"] == "not_checked"
