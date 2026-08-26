from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader

app = typer.Typer(
    name="ansari",
    help="Scaffold and manage services on the ANSARI delivery platform.",
    no_args_is_help=True,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
SUPPORTED_LANGUAGES = {"python"}
SUPPORTED_DATABASES = {"postgres", "none"}


@app.callback()
def _root() -> None:
    """ANSARI CLI. Run `ansari <command> --help` for details."""


def _render_template(env: Environment, template_name: str, dest: Path, **context: object) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(env.get_template(template_name).render(**context))


@app.command()
def new(
    name: Annotated[str, typer.Argument(help="Service name, e.g. payment-api")],
    language: Annotated[str, typer.Option(help="Service language")] = "python",
    database: Annotated[str, typer.Option(help="Database dependency")] = "postgres",
    output_dir: Annotated[Path, typer.Option(help="Where to create the service")] = Path("."),
) -> None:
    """Generate a new service: Dockerfile, CI workflow, and Helm chart."""
    if language not in SUPPORTED_LANGUAGES:
        typer.secho(f"Unsupported language: {language}. Supported: {SUPPORTED_LANGUAGES}", fg="red")
        raise typer.Exit(1)
    if database not in SUPPORTED_DATABASES:
        typer.secho(f"Unsupported database: {database}. Supported: {SUPPORTED_DATABASES}", fg="red")
        raise typer.Exit(1)

    template_dir = TEMPLATES_DIR / f"{language}-service"
    if not template_dir.exists():
        typer.secho(f"No template found for language '{language}'", fg="red")
        raise typer.Exit(1)

    service_dir = output_dir / name
    if service_dir.exists():
        typer.secho(f"Directory already exists: {service_dir}", fg="red")
        raise typer.Exit(1)

    # autoescape is intentionally off: templates render Dockerfile/YAML/Markdown
    # text from local CLI arguments, not HTML from untrusted web input.
    env = Environment(
        loader=FileSystemLoader(template_dir), keep_trailing_newline=True, autoescape=False
    )  # nosec B701
    context = {"name": name, "language": language, "database": database}

    _render_template(env, "Dockerfile.j2", service_dir / "Dockerfile", **context)
    _render_template(
        env,
        "github-workflow.yml.j2",
        service_dir / ".github" / "workflows" / "ansari.yml",
        **context,
    )
    _render_template(env, "README.md.j2", service_dir / "README.md", **context)
    _render_template(
        env, "helm/Chart.yaml.j2", service_dir / "helm" / name / "Chart.yaml", **context
    )
    _render_template(
        env, "helm/values.yaml.j2", service_dir / "helm" / name / "values.yaml", **context
    )
    _render_template(
        env,
        "helm/templates/deployment.yaml.j2",
        service_dir / "helm" / name / "templates" / "deployment.yaml",
        **context,
    )
    _render_template(
        env,
        "helm/templates/service.yaml.j2",
        service_dir / "helm" / name / "templates" / "service.yaml",
        **context,
    )

    typer.secho(f"Created {service_dir}", fg="green")
    typer.echo("Next steps:")
    typer.echo(f"  cd {service_dir}")
    typer.echo("  git init && git add . && git commit -m 'Initial scaffold'")
    typer.echo("  ansari register --repo-url <your-repo-url>  # once registered with the API")


if __name__ == "__main__":
    app()
