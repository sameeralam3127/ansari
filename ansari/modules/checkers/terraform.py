"""Checker for Terraform state resources."""

from ansari.models import HealthStatus, ResourceHealth
from ansari.modules.checkers.base import Checker

_PATTERNS = ("terraform", "tfstate")


class TerraformChecker(Checker):
    """Demo check for Terraform state drift and locking posture."""

    def matches(self, resource_name: str) -> bool:
        return any(pattern in resource_name for pattern in _PATTERNS)

    def check(self, resource_name: str) -> ResourceHealth:
        return ResourceHealth(
            resource_name=resource_name,
            resource_type="terraform-state",
            status=HealthStatus.UNKNOWN,
            message="Terraform state requires provider-aware inspection.",
            signals={"drift_status": "not_checked"},
            recommendations=[
                "Run a read-only drift check before applying changes.",
                "Confirm remote state locking and encryption are enabled.",
            ],
        )
