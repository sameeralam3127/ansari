"""Reliability check orchestration for infrastructure resources."""

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ansari.models import HealthStatus, ResourceHealth
from ansari.modules.checkers import DEFAULT_CHECKERS
from ansari.modules.checkers.base import Checker

__all__ = ["HealthStatus", "ResourceHealth", "ReliabilityChecker"]


class ReliabilityChecker:
    """Run resource checks and present SRE-friendly reliability insights."""

    def __init__(
        self, checkers: tuple[Checker, ...] = DEFAULT_CHECKERS
    ) -> None:
        self.console = Console()
        self.checkers = checkers

    def check_resource(self, resource_name: str) -> ResourceHealth:
        """
        Check a resource by name against each registered checker in order.

        The bundled checkers return deterministic demo results keyed off the
        resource name. Real Kubernetes, cloud, and IaC integrations can plug
        in by implementing `Checker` and passing it to `checkers=` -- see
        `examples/custom_checker.py`.
        """
        normalized_name = resource_name.strip().lower()

        for checker in self.checkers:
            if checker.matches(normalized_name):
                return checker.check(resource_name)

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
        status_colors = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.DEGRADED: "yellow",
            HealthStatus.UNHEALTHY: "red",
            HealthStatus.UNKNOWN: "dim",
        }
        status_color = status_colors.get(health.status, "white")

        overview = Table.grid(padding=(0, 2))
        overview.add_column(style="cyan", no_wrap=True)
        overview.add_column()
        overview.add_row("Resource", health.resource_name)
        overview.add_row("Type", health.resource_type)
        status_text = f"[bold {status_color}]{health.status.value}[/]"
        overview.add_row("Status", status_text)
        overview.add_row("Summary", health.message)

        self.console.print(
            Panel(
                overview,
                title=f"Reliability Check: {health.resource_name}",
                border_style=status_color,
                expand=False,
            )
        )

        if health.signals:
            signals_table = Table(
                title="Signals",
                box=box.SIMPLE,
                show_header=True,
                header_style="bold cyan",
            )
            signals_table.add_column("Signal", no_wrap=True)
            signals_table.add_column("Observed Value")

            for key, value in health.signals.items():
                signals_table.add_row(key.replace("_", " "), str(value))

            self.console.print(signals_table)

        if health.recommendations:
            next_steps = Table(
                title="Next Steps",
                box=box.SIMPLE,
                show_header=False,
            )
            next_steps.add_column("Step", style="cyan", no_wrap=True)
            next_steps.add_column("Recommendation")

            for index, recommendation in enumerate(
                health.recommendations, start=1
            ):
                next_steps.add_row(str(index), recommendation)

            self.console.print(next_steps)
