"""Reliability checking primitives for infrastructure resources."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table


class HealthStatus(str, Enum):
    """Supported health states for a checked resource."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ResourceHealth(BaseModel):
    """Normalized result returned by a reliability check."""

    resource_name: str
    resource_type: str
    status: HealthStatus
    message: str
    signals: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class ReliabilityChecker:
    """Run resource checks and present SRE-friendly reliability insights."""

    def __init__(self) -> None:
        self.console = Console()
        self._resource_patterns: tuple[tuple[str, ResourceHealth], ...] = (
            (
                "cluster",
                ResourceHealth(
                    resource_name="",
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
                ),
            ),
            (
                "eks",
                ResourceHealth(
                    resource_name="",
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
                ),
            ),
            (
                "pod",
                ResourceHealth(
                    resource_name="",
                    resource_type="kubernetes-pod",
                    status=HealthStatus.HEALTHY,
                    message="Pod is running without recent restart noise.",
                    signals={"phase": "Running", "restarts": 0, "age": "2d"},
                    recommendations=[
                        "Verify readiness and liveness probes are configured.",
                        "Check resource requests and limits before production rollout.",
                    ],
                ),
            ),
            (
                "rds",
                ResourceHealth(
                    resource_name="",
                    resource_type="database",
                    status=HealthStatus.DEGRADED,
                    message="Database needs deeper checks for backups and capacity.",
                    signals={"backup_status": "unknown", "storage_trend": "review"},
                    recommendations=[
                        "Validate latest backup age and restore procedure.",
                        "Review CPU, connections, storage, and replication lag alerts.",
                    ],
                ),
            ),
            (
                "db",
                ResourceHealth(
                    resource_name="",
                    resource_type="database",
                    status=HealthStatus.DEGRADED,
                    message="Database needs deeper checks for backups and capacity.",
                    signals={"backup_status": "unknown", "storage_trend": "review"},
                    recommendations=[
                        "Validate latest backup age and restore procedure.",
                        "Review CPU, connections, storage, and replication lag alerts.",
                    ],
                ),
            ),
            (
                "terraform",
                ResourceHealth(
                    resource_name="",
                    resource_type="terraform-state",
                    status=HealthStatus.UNKNOWN,
                    message="Terraform state requires provider-aware inspection.",
                    signals={"drift_status": "not_checked"},
                    recommendations=[
                        "Run a read-only drift check before applying changes.",
                        "Confirm remote state locking and encryption are enabled.",
                    ],
                ),
            ),
            (
                "tfstate",
                ResourceHealth(
                    resource_name="",
                    resource_type="terraform-state",
                    status=HealthStatus.UNKNOWN,
                    message="Terraform state requires provider-aware inspection.",
                    signals={"drift_status": "not_checked"},
                    recommendations=[
                        "Run a read-only drift check before applying changes.",
                        "Confirm remote state locking and encryption are enabled.",
                    ],
                ),
            ),
        )

    def check_resource(self, resource_name: str) -> ResourceHealth:
        """
        Check a resource by name.

        The current implementation provides deterministic demo checks. Cloud,
        Kubernetes, and IaC integrations can plug into this interface without
        changing the CLI contract.
        """
        normalized_name = resource_name.strip().lower()

        for pattern, template in self._resource_patterns:
            if pattern in normalized_name:
                return template.model_copy(update={"resource_name": resource_name})

        return ResourceHealth(
            resource_name=resource_name,
            resource_type="unknown",
            status=HealthStatus.UNKNOWN,
            message="Resource type not recognized yet.",
            recommendations=[
                "Use a recognizable resource name such as eks-cluster, pod, "
                "rds, or terraform-state.",
                "Add a dedicated checker module for this platform resource.",
            ],
        )

    def display_health(self, health: ResourceHealth) -> None:
        """Display health check results in a readable terminal table."""
        table = Table(title=f"Reliability Check: {health.resource_name}")

        table.add_column("Area", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        status_colors = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.DEGRADED: "yellow",
            HealthStatus.UNHEALTHY: "red",
            HealthStatus.UNKNOWN: "dim",
        }

        status_color = status_colors.get(health.status, "white")

        table.add_row("Resource Type", health.resource_type)
        table.add_row("Status", f"[{status_color}]{health.status.value}[/]")
        table.add_row("Summary", health.message)

        if health.signals:
            table.add_section()
            for key, value in health.signals.items():
                table.add_row(f"Signal: {key}", str(value))

        if health.recommendations:
            table.add_section()
            for index, recommendation in enumerate(health.recommendations, start=1):
                table.add_row(f"Next Step {index}", recommendation)

        self.console.print(table)
