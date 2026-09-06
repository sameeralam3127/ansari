from pathlib import Path
from typing import Annotated

import typer

from ansari.scaffold import (
    ManifestError,
    ManifestTooNewError,
    RepoDriftReport,
    TemplateDriftReport,
    VariableError,
    VariableValue,
    available_templates,
    bundled_version,
    check_repo_drift,
    find_bundled_template,
    read_manifest,
)
from ansari.scaffold.manifest import build_manifest, write_manifest
from ansari.scaffold.template import NAME_VARIABLE, render

app = typer.Typer(
    name="ansari",
    help="Scaffold services on the golden path — and keep them on it.",
    no_args_is_help=True,
)

DEFAULT_TYPE = "python-service"


@app.callback()
def _root() -> None:
    """ANSARI CLI. Run `ansari <command> --help` for details."""


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


def _parse_vars(pairs: list[str] | None) -> dict[str, str]:
    """Turn repeated `--var key=value` into a mapping.

    Values stay strings here; the template's own declaration is what knows how
    to type them.
    """
    supplied: dict[str, str] = {}
    for pair in pairs or []:
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            raise _fail(f"--var expects key=value, got {pair!r}")
        supplied[key.strip()] = value
    return supplied


def _resolve_type(
    template_type: str | None, language: str | None, database: str | None
) -> tuple[str, dict[str, str]]:
    """Settle which template to use, honouring the pre-`--type` flags.

    `--language` and `--database` predate `--type` and are documented, so they
    keep working indefinitely rather than being retired on a schedule. They are
    translated into their general equivalents and warned about, never silently
    reinterpreted.
    """
    aliased: dict[str, str] = {}
    if language is not None:
        aliased["language"] = language
    if database is not None:
        aliased["database"] = database

    if template_type is not None and aliased:
        # A precedence rule here would be a rule nobody could remember.
        raise _fail("Pass either --type or the older --language/--database flags, not both.")

    if template_type is not None:
        return template_type, {}

    if language is not None:
        typer.secho(
            f"--language is deprecated; use --type {language}-service. Still supported.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return f"{language}-service", aliased
    if database is not None:
        typer.secho(
            "--database is deprecated; use --var database=<value>. Still supported.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    return DEFAULT_TYPE, aliased


@app.command()
def new(
    name: Annotated[str, typer.Argument(help="Artifact name, e.g. payment-api")],
    template_type: Annotated[
        str | None, typer.Option("--type", help="Template to scaffold from")
    ] = None,
    var: Annotated[
        list[str] | None, typer.Option("--var", help="Template variable, key=value (repeatable)")
    ] = None,
    output_dir: Annotated[Path, typer.Option(help="Where to create the repo")] = Path("."),
    language: Annotated[
        str | None, typer.Option(help="Deprecated: use --type <language>-service")
    ] = None,
    database: Annotated[
        str | None, typer.Option(help="Deprecated: use --var database=<value>")
    ] = None,
) -> None:
    """Generate a new repo from a template.

    Run `ansari templates` to see what this build ships.
    """
    chosen, aliased = _resolve_type(template_type, language, database)

    spec = find_bundled_template(chosen)
    if spec is None:
        raise _fail(f"No template '{chosen}'. Available: {available_templates()}")

    supplied = {**aliased, **_parse_vars(var)}
    try:
        variables: dict[str, VariableValue] = {
            NAME_VARIABLE: name,
            **spec.resolve_variables(supplied),
        }
    except VariableError as exc:
        raise _fail(str(exc)) from exc

    repo_dir = output_dir / name
    if repo_dir.exists():
        raise _fail(f"Directory already exists: {repo_dir}")

    written: list[str] = []
    for source, destination in spec.destinations(variables).items():
        target = repo_dir / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(spec, source, variables))
        written.append(destination)

    # The manifest is what makes `ansari check` and `ansari sync` possible later:
    # it records the template version this repo came from and a hash per file, so
    # a future upgrade can tell a hand-edit from an untouched generated file.
    manifest = build_manifest(spec.name, spec.version, variables, repo_dir, written)
    write_manifest(repo_dir, manifest)

    typer.secho(f"Created {repo_dir}", fg=typer.colors.GREEN)
    typer.echo(f"  {len(written)} files from template {spec.name} v{spec.version}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  cd {repo_dir}")
    typer.echo("  git init && git add . && git commit -m 'Initial scaffold'")
    typer.echo("  ansari check     # verify this repo is still on the golden path")


@app.command()
def templates() -> None:
    """List the templates this build ships."""
    names = available_templates()
    if not names:
        raise _fail("No bundled templates found.")

    for template_name in names:
        spec = find_bundled_template(template_name)
        if spec is None:  # pragma: no cover - listing reads the same directory
            continue
        typer.secho(f"{spec.name}  v{spec.version}", fg=typer.colors.GREEN)
        if spec.description:
            typer.echo(f"  {spec.description}")
        for key, variable in sorted(spec.variables.items()):
            default = "required" if variable.required else f"default: {variable.default}"
            choices = f", one of {variable.choices}" if variable.choices else ""
            typer.echo(f"    --var {key}=<{variable.type}>  ({default}{choices})")


def _echo_paths(label: str, paths: list[str]) -> None:
    if paths:
        typer.echo("")
        typer.secho(f"{len(paths)} file(s) {label}:", fg=typer.colors.YELLOW)
        for item in paths:
            typer.echo(f"  {item}")


def _report_single(report: TemplateDriftReport) -> None:
    """Render one template's drift.

    Kept byte-for-byte identical to the pre-multi-template output so that a repo
    with one template -- which is every repo scaffolded so far -- sees no change
    in what `ansari check` prints or what its CI greps for.
    """
    typer.echo(f"Template: {report.template}")
    if report.behind:
        typer.secho(
            f"Version:  {report.recorded_version} → {report.current_version} (behind)",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho(f"Version:  {report.current_version} (current)", fg=typer.colors.GREEN)

    _echo_paths("modified locally", report.modified)
    _echo_paths("deleted locally", report.deleted)


def _report_composite(repo: RepoDriftReport) -> None:
    """Render a repo carrying more than one template, one section per template."""
    attached = len(repo.reports) + len(repo.unresolved)
    typer.echo(f"Templates: {attached} attached")
    typer.echo("")

    for report in repo.reports:
        if report.behind:
            state = f"{report.recorded_version} → {report.current_version} (behind)"
            colour = typer.colors.YELLOW
        else:
            state = f"{report.current_version} (current)"
            colour = typer.colors.GREEN
        typer.secho(f"  {report.template}  {state}", fg=colour)
        for item in report.modified:
            typer.echo(f"      modified: {item}")
        for item in report.deleted:
            typer.echo(f"      deleted:  {item}")

    for name in repo.unresolved:
        typer.secho(f"  {name}  unknown to this ANSARI (cannot verify)", fg=typer.colors.RED)


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Repo directory to check")] = Path("."),
) -> None:
    """Report whether a repo has drifted from the templates it was scaffolded from.

    Read-only. Exits 1 when any attached template is behind, has local edits, or
    cannot be verified — so a repo can fail its own CI when it falls off the
    golden path.
    """
    try:
        manifest = read_manifest(path)
    except ManifestTooNewError as exc:
        # Not a malformed manifest: the file is fine, this build is older than
        # the one that wrote it. Saying so points at the actual fix.
        raise _fail(str(exc)) from exc
    except ManifestError as exc:
        raise _fail(f"Could not read manifest: {exc}") from exc

    if manifest is None:
        raise _fail(
            f"No .ansari/manifest.yaml in {path}.\n"
            "This service was not scaffolded by ANSARI, or the manifest was removed."
        )

    # Resolution is by recorded template name, not by the `language` variable.
    # Every manifest ever written records `template:` directly, so this reads
    # pre-multi-template manifests without migrating them.
    repo = check_repo_drift(path, manifest, bundled_version)

    if len(manifest.templates) == 1 and repo.reports:
        _report_single(repo.reports[0])
    else:
        _report_composite(repo)

    typer.echo("")
    if repo.clean:
        typer.secho(
            f"On the golden path — {len(repo.unchanged)} generated files unchanged.",
            fg=typer.colors.GREEN,
        )
        return

    if repo.edited:
        typer.echo("Locally edited files will be three-way merged, never overwritten.")
    if repo.behind:
        typer.echo("Run `ansari sync` to upgrade to the current template. (Not yet implemented.)")
    if repo.unresolved:
        typer.echo(
            "Cannot verify: "
            + ", ".join(repo.unresolved)
            + ". This repo was scaffolded by a newer ANSARI; upgrade to check it."
        )
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
