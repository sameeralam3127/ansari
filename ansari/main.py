"""CLI entry point for ANSARI."""

import pyfiglet
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ansari import __version__
from ansari.core.config import config
from ansari.modules.reliability_checker import ReliabilityChecker

app = typer.Typer(
    name="ansari",
    help=(
        "ANSARI helps DevOps, SRE, and platform teams check infrastructure "
        "reliability from one readable CLI."
    ),
    add_completion=False,
)

console = Console()

EXAMPLE_RESOURCES = (
    ("Kubernetes cluster", "ansari check eks-cluster-01"),
    ("Kubernetes pod", "ansari check payment-pod"),
    ("Database", "ansari check prod-rds-db"),
    ("Terraform state", "ansari check terraform-prod-state"),
)


def print_banner() -> None:
    """Print the big ANSARI wordmark."""
    banner = pyfiglet.figlet_format("ANSARI", font="big")
    console.print(Text(banner.rstrip("\n"), style="bold cyan"))
    console.print(
        "[dim]Advanced Network SRE & Automated Remediation Interface[/dim]\n"
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
            "Example: [bold]ansari check eks-cluster-01[/bold]"
        )
        raise typer.Exit(code=1)

    if verbose:
        console.print("[dim]Verbose mode enabled. Showing check context.[/dim]")

    console.print(
        Panel.fit(
            f"[bold cyan]Checking[/bold cyan] {resource}\n"
            "[dim]Looking for resource type, useful signals, "
            "and next steps.[/dim]",
            border_style="cyan",
        )
    )

    checker = ReliabilityChecker()
    health = checker.check_resource(resource)
    checker.display_health(health)


@app.command()
def version() -> None:
    """Display the version of ANSARI."""
    print_banner()
    console.print(f"[bold green]Version[/bold green] {__version__}")


@app.command()
def examples() -> None:
    """Show copy-pasteable example commands."""
    table = Table(title="ANSARI Examples", show_lines=False)
    table.add_column("Use Case", style="cyan", no_wrap=True)
    table.add_column("Command", style="green")

    for label, command in EXAMPLE_RESOURCES:
        table.add_row(label, command)

    console.print(table)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    ANSARI - the helper for reliability checks.

    A Python-native DevOps, SRE, and platform engineering CLI for
    reliability checks, operational context, and remediation guidance.
    """
    if ctx.invoked_subcommand is None:
        print_banner()
        console.print(ctx.get_help())
        raise typer.Exit()


if __name__ == "__main__":
    app()
