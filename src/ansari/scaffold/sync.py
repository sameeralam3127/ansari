"""Upgrading a repo to the current versions of its templates.

`ansari check` reports that a repo has fallen behind; `ansari sync` brings it up to
date without discarding what people changed. Each generated file is handled by
what its recorded hash says about it:

- **untouched** -- replaced outright with the new version's output;
- **edited** -- three-way merged. The common ancestor is what the old version
  generated. This build only ships each template's current version, so that
  content is found in the repo's own git history: the committed blob whose hash
  equals the one the manifest recorded. Independent edits merge cleanly;
  overlapping ones get conflict markers for a person to resolve;
- **deleted** -- left deleted. Somebody removed it on purpose.

A template is refused, with nothing written for it, when its plan can't be carried
out safely: an edited file with no ancestor in history, a new file where an
untracked one already sits, a destination another template owns, or a newly
required variable nobody has set. Planning does all the work, merges included, so
a dry run reports exactly what a real run would do.
"""

import hashlib
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ansari.scaffold.drift import ensure_writable
from ansari.scaffold.manifest import (
    SCHEMA_VERSION,
    Manifest,
    TemplateRecord,
    VariableValue,
    write_manifest,
)
from ansari.scaffold.template import (
    NAME_VARIABLE,
    TemplateError,
    TemplateSpec,
    VariableError,
    generate,
)

TemplateFinder = Callable[[str], TemplateSpec | None]
GitRunner = Callable[[Path, Sequence[str]], subprocess.CompletedProcess[bytes]]

UPDATE = "update"
"""Untouched since generated; replaced with the new output."""
ADD = "add"
"""New in this version."""
MERGE = "merge"
"""Edited here; merged with the new output cleanly."""
CONFLICT = "conflict"
"""Edited here in a way that overlaps the new output; written with markers."""
REMOVE = "remove"
"""No longer generated, and untouched; deleted."""
KEPT = "kept"
"""No longer generated, but edited here; kept, and dropped from the manifest."""
LEFT_DELETED = "left-deleted"
"""Deleted here on purpose; stays deleted."""
UNCHANGED = "unchanged"
"""Nothing to write: the template didn't change it, or the edit already matches."""

_WRITES = frozenset({UPDATE, ADD, MERGE, CONFLICT})


class SyncError(Exception):
    """Sync can't start on this repo at all."""


@dataclass(frozen=True)
class FileAction:
    path: str
    kind: str
    content: bytes | None = None
    mode: int | None = None


@dataclass(frozen=True)
class TemplatePlan:
    """What syncing one attached template would do."""

    index: int
    """Position of the record in the manifest's `templates:` list."""
    record: TemplateRecord
    to_version: str
    variables: dict[str, VariableValue] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    """The new record's files: every path the new version generates, with its hash."""
    actions: list[FileAction] = field(default_factory=list)
    refused: str | None = None

    @property
    def template(self) -> str:
        return self.record.template

    @property
    def conflicts(self) -> list[str]:
        return [action.path for action in self.actions if action.kind == CONFLICT]


@dataclass(frozen=True)
class SyncPlan:
    repo: Path
    manifest: Manifest
    templates: list[TemplatePlan] = field(default_factory=list)
    """Only the templates that are behind."""

    @property
    def up_to_date(self) -> bool:
        return not self.templates

    @property
    def refused(self) -> list[TemplatePlan]:
        return [plan for plan in self.templates if plan.refused is not None]

    @property
    def conflicts(self) -> list[str]:
        return [path for plan in self.templates if plan.refused is None for path in plan.conflicts]

    @property
    def clean(self) -> bool:
        return not self.refused and not self.conflicts


def run_git(cwd: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    """Run a local git command. Sync never reaches the network through this."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def ensure_syncable(repo_dir: Path, git: GitRunner = run_git, *, allow_dirty: bool = False) -> None:
    """Refuse a repo sync can't upgrade safely.

    It must be a git working tree, because edited files merge against what the old
    version generated, which lives in git history. And its tree must be clean, so
    the sync is a reviewable diff of its own rather than tangled with unfinished
    work -- unless the caller says otherwise.
    """
    inside = git(repo_dir, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        raise SyncError(
            f"{repo_dir} is not a git working tree. Sync merges edited files against "
            "what the old template version generated, which it finds in git history."
        )
    if allow_dirty:
        return
    status = git(repo_dir, ["status", "--porcelain", "--", "."])
    if status.stdout.strip():
        raise SyncError(
            f"{repo_dir} has uncommitted changes. Commit or stash them first, so the "
            "sync is a diff of its own -- or pass --allow-dirty."
        )


def carry_variables(spec: TemplateSpec, record: TemplateRecord) -> dict[str, VariableValue]:
    """The variables to render the new version with.

    The ones the repo was scaffolded with, typed and validated against the new
    version's declarations. A variable the new version dropped is dropped; a new
    one with a default takes its default. A new *required* variable can't be
    guessed, so it raises.
    """
    name = record.variables.get(NAME_VARIABLE)
    if not isinstance(name, str) or not name:
        raise VariableError(f"{record.template}: the manifest records no '{NAME_VARIABLE}'")

    carried: dict[str, VariableValue] = {NAME_VARIABLE: name}
    for key, declared in spec.variables.items():
        if key in record.variables:
            value = record.variables[key]
            # Schema-1 manifests recorded every value as a string.
            if isinstance(value, str) and declared.type != "string":
                value = declared.parse(value)
        elif declared.default is not None:
            value = declared.default
        else:
            raise VariableError(
                f"{spec.name} {spec.version} requires a new variable '{key}' this repo has "
                "never set, and sync can't choose a value for it"
            )
        declared.validate(value)
        carried[key] = value
    return carried


def plan_sync(
    repo_dir: Path, manifest: Manifest, find_template: TemplateFinder, git: GitRunner = run_git
) -> SyncPlan:
    """Work out, without writing anything, what upgrading this repo would do.

    Raises when the manifest carries a template this build can't resolve: a sync
    that can't see every template's files can't know which files it may touch.
    """

    def resolve(name: str) -> str | None:
        spec = find_template(name)
        return spec.version if spec is not None else None

    ensure_writable(manifest, resolve)

    plans: list[TemplatePlan] = []
    for index, record in enumerate(manifest.templates):
        spec = find_template(record.template)
        if spec is None or spec.version == record.version:
            continue
        others = {
            path: other.template
            for position, other in enumerate(manifest.templates)
            if position != index
            for path in other.files
        }
        plans.append(_plan_template(repo_dir, index, record, spec, others, git))
    return SyncPlan(repo=repo_dir, manifest=manifest, templates=plans)


def apply_sync(plan: SyncPlan) -> Manifest:
    """Carry out a plan: write the files, then record the new versions.

    Refused templates are left untouched and keep their old records. When every
    template was refused, nothing is written at all.
    """
    applicable = {
        template.index: template for template in plan.templates if template.refused is None
    }
    if not applicable:
        return plan.manifest

    records: list[TemplateRecord] = []
    for index, record in enumerate(plan.manifest.templates):
        template_plan = applicable.get(index)
        if template_plan is None:
            records.append(record)
            continue
        _apply_actions(plan.repo, template_plan.actions)
        records.append(
            TemplateRecord(
                template=record.template,
                version=template_plan.to_version,
                rendered_at=datetime.now(UTC),
                variables=template_plan.variables,
                files=template_plan.files,
            )
        )

    updated = Manifest(schema=SCHEMA_VERSION, templates=records)
    write_manifest(plan.repo, updated)
    return updated


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _plan_template(
    repo_dir: Path,
    index: int,
    record: TemplateRecord,
    spec: TemplateSpec,
    others: dict[str, str],
    git: GitRunner,
) -> TemplatePlan:
    def refuse(reason: str) -> TemplatePlan:
        return TemplatePlan(index=index, record=record, to_version=spec.version, refused=reason)

    try:
        variables = carry_variables(spec, record)
    except VariableError as exc:
        return refuse(str(exc))

    with tempfile.TemporaryDirectory() as scratch:
        rendered = Path(scratch) / "out"
        try:
            written = generate(spec, variables, rendered)
        except TemplateError as exc:
            return refuse(str(exc))
        new = {dest: (rendered / dest).read_bytes() for dest in written}

    sources = {dest: source for source, dest in spec.destinations(variables).items()}
    actions: list[FileAction] = []

    for dest in sorted(new):
        content = new[dest]
        if dest in others:
            return refuse(f"{spec.version} would write {dest}, which {others[dest]} owns")

        target = repo_dir / dest
        recorded = record.files.get(dest)
        mode = spec.files[sources[dest]].mode

        if recorded is None:
            if target.exists() or target.is_symlink():
                return refuse(
                    f"{spec.version} adds {dest}, but a file not tracked by ANSARI is already there"
                )
            actions.append(FileAction(dest, ADD, content, mode))
            continue

        if not target.is_file():
            actions.append(FileAction(dest, LEFT_DELETED))
            continue

        local = target.read_bytes()
        if _digest(local) == recorded:
            if _digest(content) == recorded:
                actions.append(FileAction(dest, UNCHANGED))
            else:
                actions.append(FileAction(dest, UPDATE, content, mode))
            continue

        # Edited here. Nothing to merge if the template didn't change this file,
        # or if the edit already is what the new version generates.
        if _digest(content) == recorded or local == content:
            actions.append(FileAction(dest, UNCHANGED))
            continue

        original = _generated_original(repo_dir, dest, recorded, git)
        if original is None:
            return refuse(
                f"{dest} was edited, and what {record.version} generated isn't in git history "
                "to merge against. Merge it by hand, or commit the untouched file first next time."
            )
        merged = _merge(
            repo_dir,
            local,
            original,
            content,
            (f"{record.template} {record.version}", f"{spec.name} {spec.version}"),
            git,
        )
        if merged is None:
            return refuse(f"{dest} was edited but can't be merged: it isn't text")
        merged_content, conflict_count = merged
        actions.append(FileAction(dest, CONFLICT if conflict_count else MERGE, merged_content))

    for path in sorted(set(record.files) - set(new)):
        target = repo_dir / path
        if not target.is_file():
            continue
        untouched = _digest(target.read_bytes()) == record.files[path]
        actions.append(FileAction(path, REMOVE if untouched else KEPT))

    return TemplatePlan(
        index=index,
        record=record,
        to_version=spec.version,
        variables=variables,
        files={dest: _digest(content) for dest, content in new.items()},
        actions=actions,
    )


def _generated_original(repo_dir: Path, path: str, digest: str, git: GitRunner) -> bytes | None:
    """The committed blob of `path` whose hash is the one the manifest recorded."""
    log = git(repo_dir, ["log", "--format=%H", "--", path])
    if log.returncode != 0:
        return None
    for commit in log.stdout.decode().split():
        blob = git(repo_dir, ["show", f"{commit}:./{path}"])
        if blob.returncode == 0 and _digest(blob.stdout) == digest:
            return blob.stdout
    return None


def _merge(
    repo_dir: Path,
    local: bytes,
    original: bytes,
    new: bytes,
    labels: tuple[str, str],
    git: GitRunner,
) -> tuple[bytes, int] | None:
    """Three-way merge with `git merge-file`; returns the result and its conflict count."""
    if any(b"\0" in content for content in (local, original, new)):
        return None
    with tempfile.TemporaryDirectory() as scratch:
        paths = []
        for name, content in (("local", local), ("original", original), ("new", new)):
            file = Path(scratch) / name
            file.write_bytes(content)
            paths.append(str(file))
        result = git(
            repo_dir,
            ["merge-file", "-p", "-L", "local", "-L", labels[0], "-L", labels[1], *paths],
        )
    # merge-file exits with the number of conflicts, or a negative number on error.
    if not 0 <= result.returncode <= 127:
        return None
    return result.stdout, result.returncode


def _apply_actions(repo_dir: Path, actions: list[FileAction]) -> None:
    for action in actions:
        target = repo_dir / action.path
        if action.kind == REMOVE:
            target.unlink(missing_ok=True)
        elif action.kind in _WRITES and action.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(action.content)
            if action.mode is not None:
                target.chmod(action.mode)
