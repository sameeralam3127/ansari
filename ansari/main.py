"""CLI entry point for ANSARI."""

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from ansari import __version__
from ansari.modules.reliability_checker import ReliabilityChecker
from ansari.core.config import config

app = typer.Typer(
    name="ansari",
    help="Advanced Network SRE & Automated Remediation Interface",
)

console = Console()


@app.command()
def check(
    resource: str = typer.Argument(
        ...,
        help="Name of the resource to check (e.g., eks-cluster-01)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Check the reliability posture of an infrastructure resource."""
    config.debug = verbose

    if verbose:
        console.print("[dim]Debug mode enabled[/dim]")

    console.print(
        Panel.fit(
            f"[bold cyan]Checking resource:[/bold cyan] {resource}",
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


@app.callback()
def main() -> None:
    """
    ANSARI - The Helper.

    A Python-native DevOps, SRE, and platform engineering CLI for
    reliability checks, operational context, and remediation guidance.
    """
    pass


if __name__ == "__main__":
    app()
