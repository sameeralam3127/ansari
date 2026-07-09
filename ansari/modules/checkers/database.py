"""Checker for database resources such as RDS instances."""

from ansari.models import HealthStatus, ResourceHealth
from ansari.modules.checkers.base import Checker

_PATTERNS = ("rds", "db")


class DatabaseChecker(Checker):
    """Demo check for managed database reliability signals."""

    def matches(self, resource_name: str) -> bool:
        return any(pattern in resource_name for pattern in _PATTERNS)

    def check(self, resource_name: str) -> ResourceHealth:
        return ResourceHealth(
            resource_name=resource_name,
            resource_type="database",
            status=HealthStatus.DEGRADED,
            message="Database needs deeper checks for backups and capacity.",
            signals={"backup_status": "unknown", "storage_trend": "review"},
            recommendations=[
                "Validate latest backup age and restore procedure.",
                "Review CPU, connections, storage, and replication lag alerts.",
            ],
        )
