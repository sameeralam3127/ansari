"""Checkers for Kubernetes clusters and pods."""

from ansari.models import HealthStatus, ResourceHealth
from ansari.modules.checkers.base import Checker

_CLUSTER_PATTERNS = ("cluster", "eks")
_POD_PATTERNS = ("pod",)


class ClusterChecker(Checker):
    """Demo check for Kubernetes cluster control plane and node health."""

    def matches(self, resource_name: str) -> bool:
        return any(pattern in resource_name for pattern in _CLUSTER_PATTERNS)

    def check(self, resource_name: str) -> ResourceHealth:
        return ResourceHealth(
            resource_name=resource_name,
            resource_type="kubernetes-cluster",
            status=HealthStatus.HEALTHY,
            message="Cluster control plane and worker capacity look healthy.",
            signals={
                "ready_nodes": 3,
                "running_pods": 45,
                "kubernetes_version": "1.28",
            },
            recommendations=[
                "Enable cluster autoscaler and review node pressure alerts.",
                "Track API server latency and failed scheduling events.",
            ],
        )


class PodChecker(Checker):
    """Demo check for individual Kubernetes pod health."""

    def matches(self, resource_name: str) -> bool:
        return any(pattern in resource_name for pattern in _POD_PATTERNS)

    def check(self, resource_name: str) -> ResourceHealth:
        return ResourceHealth(
            resource_name=resource_name,
            resource_type="kubernetes-pod",
            status=HealthStatus.HEALTHY,
            message="Pod is running without recent restart noise.",
            signals={"phase": "Running", "restarts": 0, "age": "2d"},
            recommendations=[
                "Verify readiness and liveness probes are configured.",
                "Check resource requests and limits before production rollout.",
            ],
        )
