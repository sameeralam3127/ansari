"""
ANSARI - The Voice
Main CLI interface for the ANSARI tool.
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint

from ansari.modules.resource_checker import ResourceChecker
from ansari.core.config import config

# Create the Typer app
app = typer.Typer(
    name="ansari",
    help="Advanced Native Scripting for Automated Resource Integration",
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
    """
    Check the health of a specific resource.
    
    Examples:
        ansari check eks-cluster-01
        ansari check my-pod -v
    """
    if verbose:
        config.debug = True
        console.print("[dim]Debug mode enabled[/dim]")
    
    console.print(
        Panel.fit(
            f"[bold cyan]Checking resource:[/bold cyan] {resource}",
            border_style="cyan",
        )
    )
    
    checker = ResourceChecker()
    health = checker.check_resource(resource)
    checker.display_health(health)


@app.command()
def version() -> None:
    """Display the version of ANSARI."""
    from ansari import __version__
    
    rprint(
        Panel.fit(
            f"[bold green]ANSARI[/bold green] v{__version__}\n"
            "[dim]Advanced Native Scripting for "
            "Automated Resource Integration[/dim]",
            border_style="green",
        )
    )


@app.callback()
def main() -> None:
    """
    ANSARI - The Helper
    
    A Python-native DevOps utility for resource orchestration
    and health auditing.
    """
    pass


if __name__ == "__main__":
    app()

# Made with Bob
