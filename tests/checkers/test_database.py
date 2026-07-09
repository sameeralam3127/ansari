from ansari.models import HealthStatus
from ansari.modules.checkers.database import DatabaseChecker


def test_database_checker_matches_rds_and_db_names() -> None:
    checker = DatabaseChecker()

    assert checker.matches("prod-rds-db")
    assert checker.matches("orders-db")
    assert not checker.matches("eks-cluster-01")


def test_database_checker_flags_backup_review() -> None:
    checker = DatabaseChecker()

    health = checker.check("prod-rds-db")

    assert health.resource_type == "database"
    assert health.status == HealthStatus.DEGRADED
    assert health.signals["backup_status"] == "unknown"
