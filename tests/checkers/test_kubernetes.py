from ansari.models import HealthStatus
from ansari.modules.checkers.kubernetes import ClusterChecker, PodChecker


def test_cluster_checker_matches_cluster_and_eks_names() -> None:
    checker = ClusterChecker()

    assert checker.matches("eks-cluster-01")
    assert checker.matches("prod-cluster")
    assert not checker.matches("payment-pod")


def test_cluster_checker_reports_healthy_signals() -> None:
    checker = ClusterChecker()

    health = checker.check("eks-cluster-01")

    assert health.resource_type == "kubernetes-cluster"
    assert health.status == HealthStatus.HEALTHY
    assert health.signals["ready_nodes"] == 3


def test_pod_checker_matches_pod_names_only() -> None:
    checker = PodChecker()

    assert checker.matches("payment-pod")
    assert not checker.matches("eks-cluster-01")


def test_pod_checker_reports_running_phase() -> None:
    checker = PodChecker()

    health = checker.check("payment-pod")

    assert health.resource_type == "kubernetes-pod"
    assert health.signals["phase"] == "Running"
