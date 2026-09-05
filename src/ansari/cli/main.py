from pathlib import Path
from typing import Annotated

import typer

from ansari.scaffold import (
    ManifestError,
    TemplateError,
    TemplateSpec,
    bundled_template,
    check_drift,
    read_manifest,
)
from ansari.scaffold.manifest import build_manifest, write_manifest
from ansari.scaffold.template import render

app = typer.Typer(
    name="ansari",
    help="Scaffold services on the golden path — and keep them on it.",
    no_args_is_help=True,
)

SUPPORTED_LANGUAGES = {"python"}
SUPPORTED_DATABASES = {"postgres", "none"}


@app.callback()
def _root() -> None:
    """ANSARI CLI. Run `ansari <command> --help` for details."""


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


@app.command()
def new(
    name: Annotated[str, typer.Argument(help="Service name, e.g. payment-api")],
    language: Annotated[str, typer.Option(help="Service language")] = "python",
    database: Annotated[str, typer.Option(help="Database dependency")] = "postgres",
    output_dir: Annotated[Path, typer.Option(help="Where to create the service")] = Path("."),
) -> None:
    """Generate a new service: Dockerfile, CI workflow, and Helm chart."""
    if language not in SUPPORTED_LANGUAGES:
        raise _fail(f"Unsupported language: {language}. Supported: {sorted(SUPPORTED_LANGUAGES)}")
    if database not in SUPPORTED_DATABASES:
        raise _fail(f"Unsupported database: {database}. Supported: {sorted(SUPPORTED_DATABASES)}")

    try:
        spec = bundled_template(language)
    except TemplateError as exc:
        raise _fail(str(exc)) from exc

    service_dir = output_dir / name
    if service_dir.exists():
        raise _fail(f"Directory already exists: {service_dir}")

    variables = {"name": name, "language": language, "database": database}
    written: list[str] = []
    for source, destination in spec.destinations(variables).items():
        target = service_dir / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(spec, source, variables))
        written.append(destination)

    # The manifest is what makes `ansari check` and `ansari sync` possible later:
    # it records the template version this repo came from and a hash per file, so
    # a future upgrade can tell a hand-edit from an untouched generated file.
    manifest = build_manifest(spec.name, spec.version, variables, service_dir, written)
    write_manifest(service_dir, manifest)

    typer.secho(f"Created {service_dir}", fg=typer.colors.GREEN)
    typer.echo(f"  {len(written)} files from template {spec.name} v{spec.version}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  cd {service_dir}")
    typer.echo("  git init && git add . && git commit -m 'Initial scaffold'")
    typer.echo("  ansari check     # verify this service is still on the golden path")


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Service directory to check")] = Path("."),
) -> None:
    """Report whether a service has drifted from the template it was scaffolded from.

    Read-only. Exits 1 when the service is behind or has local edits, so a repo
    can fail its own CI when it falls off the golden path.
    """
    try:
        manifest = read_manifest(path)
    except ManifestError as exc:
        raise _fail(f"Could not read manifest: {exc}") from exc

    if manifest is None:
        raise _fail(
            f"No .ansari/manifest.yaml in {path}.\n"
            "This service was not scaffolded by ANSARI, or the manifest was removed."
        )

    language = manifest.variables.get("language", "python")
    try:
        spec: TemplateSpec = bundled_template(language)
    except TemplateError as exc:
        raise _fail(str(exc)) from exc

    report = check_drift(path, manifest, spec.version)

    typer.echo(f"Template: {report.template}")
    if report.behind:
        typer.secho(
            f"Version:  {report.recorded_version} → {report.current_version} (behind)",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho(f"Version:  {report.current_version} (current)", fg=typer.colors.GREEN)

    for label, paths, colour in (
        ("modified locally", report.modified, typer.colors.YELLOW),
        ("deleted locally", report.deleted, typer.colors.YELLOW),
    ):
        if paths:
            typer.echo("")
            typer.secho(f"{len(paths)} file(s) {label}:", fg=colour)
            for item in paths:
                typer.echo(f"  {item}")

    typer.echo("")
    if report.clean:
        typer.secho(
            f"On the golden path — {len(report.unchanged)} generated files unchanged.",
            fg=typer.colors.GREEN,
        )
        return

    if report.edited:
        typer.echo("Locally edited files will be three-way merged, never overwritten.")
    if report.behind:
        typer.echo("Run `ansari sync` to upgrade to the current template. (Not yet implemented.)")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
