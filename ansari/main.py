"""CLI entry point for ANSARI."""

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ansari import __version__
from ansari.core.config import config
from ansari.modules.reliability_checker import ReliabilityChecker

app = typer.Typer(
    name="ansari",
    help=(
        "ANSARI helps DevOps, SRE, and platform teams check infrastructure "
        "reliability from one readable CLI."
    ),
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

EXAMPLE_RESOURCES = (
    ("Kubernetes cluster", "poetry run ansari check eks-cluster-01"),
    ("Kubernetes pod", "poetry run ansari check payment-pod"),
    ("Database", "poetry run ansari check prod-rds-db"),
    ("Terraform state", "poetry run ansari check terraform-prod-state"),
)


@app.command()
def check(
    resource: str = typer.Argument(
        ...,
        help="Resource name to check, such as eks-cluster-01 or prod-rds-db.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show extra context while the check runs.",
    ),
) -> None:
    """Check the reliability posture of an infrastructure resource."""
    config.debug = verbose
    resource = resource.strip()

    if not resource:
        console.print(
            "[red]Please provide a resource name.[/red]\n"
            "Example: [bold]poetry run ansari check eks-cluster-01[/bold]"
        )
        raise typer.Exit(code=1)

    if verbose:
        console.print("[dim]Verbose mode enabled. Showing check context.[/dim]")

    console.print(
        Panel.fit(
            f"[bold cyan]Checking[/bold cyan] {resource}\n"
            "[dim]Looking for resource type, useful signals, and next steps.[/dim]",
            border_style="cyan",
        )
    )

    checker = ReliabilityChecker()
    health = checker.check_resource(resource)
    checker.display_health(health)


@app.command()
def version() -> None:
    """Display the version of ANSARI."""
    rprint(
        Panel.fit(
            f"[bold green]ANSARI[/bold green] v{__version__}\n"
            "[dim]Advanced Network SRE & "
            "Automated Remediation Interface[/dim]",
            border_style="green",
        )
    )


@app.command()
def examples() -> None:
    """Show copy-pasteable example commands."""
    table = Table(title="ANSARI Examples", show_lines=False)
    table.add_column("Use Case", style="cyan", no_wrap=True)
    table.add_column("Command", style="green")

    for label, command in EXAMPLE_RESOURCES:
        table.add_row(label, command)

    console.print(table)


@app.callback()
def main() -> None:
    """
    ANSARI - the helper for reliability checks.

    A Python-native DevOps, SRE, and platform engineering CLI for
    reliability checks, operational context, and remediation guidance.
    """
    pass


if __name__ == "__main__":
    app()
