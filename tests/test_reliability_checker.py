from ansari.modules.checkers.base import Checker
from ansari.modules.reliability_checker import (
    HealthStatus,
    ReliabilityChecker,
    ResourceHealth,
)


def test_cluster_check_returns_reliability_signals() -> None:
    checker = ReliabilityChecker()

    result = checker.check_resource("eks-cluster-01")

    assert result.resource_type == "kubernetes-cluster"
    assert result.status == HealthStatus.HEALTHY
    assert result.signals["ready_nodes"] == 3
    assert result.recommendations


def test_database_check_surfaces_next_steps() -> None:
    checker = ReliabilityChecker()

    result = checker.check_resource("prod-rds-db")

    assert result.resource_type == "database"
    assert result.status == HealthStatus.DEGRADED
    assert "backup" in result.message.lower()
    assert any("backup" in step.lower() for step in result.recommendations)


def test_unknown_resource_explains_how_to_extend() -> None:
    checker = ReliabilityChecker()

    result = checker.check_resource("custom-service")

    assert result.resource_type == "unknown"
    assert result.status == HealthStatus.UNKNOWN
    assert any("checker module" in step.lower() for step in result.recommendations)


class _AlwaysUnhealthyChecker(Checker):
    """Minimal custom checker used to prove the registry is pluggable."""

    def matches(self, resource_name: str) -> bool:
        return resource_name == "widget"

    def check(self, resource_name: str) -> ResourceHealth:
        return ResourceHealth(
            resource_name=resource_name,
            resource_type="widget",
            status=HealthStatus.UNHEALTHY,
            message="Widget is on fire.",
        )


def test_custom_checker_can_be_injected_via_constructor() -> None:
    checker = ReliabilityChecker(checkers=(_AlwaysUnhealthyChecker(),))

    result = checker.check_resource("widget")

    assert result.resource_type == "widget"
    assert result.status == HealthStatus.UNHEALTHY


def test_injected_checkers_replace_rather_than_extend_defaults() -> None:
    checker = ReliabilityChecker(checkers=(_AlwaysUnhealthyChecker(),))

    result = checker.check_resource("eks-cluster-01")

    assert result.resource_type == "unknown"
