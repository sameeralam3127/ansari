"""Attaching a template to a repo that already carries one.

A repo often has more than one provenance -- a service that also owns its scaling
config -- so templates can be added after `ansari new`. Attaching is the first
write path that touches a repo holding files ANSARI did not just create, which is
why every check here runs before anything is written: a refused attach leaves the
repo, and its manifest, exactly as they were.
"""

from collections.abc import Mapping
from pathlib import Path

from ansari.scaffold.drift import VersionResolver, ensure_writable
from ansari.scaffold.manifest import (
    Manifest,
    ManifestError,
    VariableValue,
    attach_record,
    build_record,
    write_manifest,
)
from ansari.scaffold.template import NAME_VARIABLE, TemplateSpec, generate


class AttachConflictError(ManifestError):
    """Attaching would write over a file the new template does not own."""


def default_name(manifest: Manifest, repo_dir: Path) -> str:
    """The artifact name to attach under when the caller gives none.

    The first recorded `name` is what the repo's existing destination paths were
    rendered with -- `helm/payment-api/...` -- so reusing it is what lands an
    attached template's files beside the ones they extend. The directory name is
    only a fallback, for a manifest that never recorded one.
    """
    for record in manifest.templates:
        recorded = record.variables.get(NAME_VARIABLE)
        if isinstance(recorded, str) and recorded:
            return recorded
    return repo_dir.resolve().name


def attach_template(
    repo_dir: Path,
    manifest: Manifest,
    spec: TemplateSpec,
    variables: Mapping[str, VariableValue],
    resolve_version: VersionResolver,
    *,
    allow_unresolved: bool = False,
) -> tuple[Manifest, list[str]]:
    """Render `spec` into an existing repo and record it.

    Returns the updated manifest and the paths written. Refuses, before writing
    anything:

    - when the manifest carries a template this build cannot resolve, unless
      `allow_unresolved`, because that entry's file ownership cannot be verified;
    - when a destination is already owned by an attached template -- including an
      unresolved one, whose paths are still recorded even though its descriptor
      is unknown;
    - when a destination exists but no template owns it. It is somebody's file,
      and ANSARI never overwrites a file it did not generate.
    """
    ensure_writable(manifest, resolve_version, allow_unresolved=allow_unresolved)

    owners = manifest.claimed_paths()
    conflicts: dict[str, str] = {}
    for dest in spec.destinations(variables).values():
        target = repo_dir / dest
        if dest in owners:
            conflicts[dest] = f"owned by {owners[dest]}"
        elif target.exists() or target.is_symlink():
            conflicts[dest] = "exists and is not tracked by ANSARI"
    if conflicts:
        listing = "\n".join(f"  {path}: {why}" for path, why in sorted(conflicts.items()))
        raise AttachConflictError(
            f"refusing to attach {spec.name}: it would write over existing files\n{listing}"
        )

    written = generate(spec, variables, repo_dir)
    updated = attach_record(
        manifest, build_record(spec.name, spec.version, variables, repo_dir, written)
    )
    write_manifest(repo_dir, updated)
    return updated, written
