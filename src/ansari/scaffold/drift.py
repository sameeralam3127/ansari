"""Comparing a scaffolded repo against the templates it came from.

Read-only by design. Detection ships before modification: a tool that clobbers
hand-edited files gets uninstalled after the first upgrade, so being able to say
"these three files were edited locally, I won't touch them" is what makes an
automated upgrade acceptable at all.

A repo may carry several templates, so there are two levels here: one report per
attached template, and a composite over the repo. The composite is not merely a
sum — it also has to account for templates this build cannot resolve at all.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ansari.scaffold.manifest import (
    Manifest,
    TemplateRecord,
    UnresolvedTemplateError,
    file_digest,
)

VersionResolver = Callable[[str], str | None]
"""Template name -> the version this build ships, or None if it ships no such
template. Returning None rather than raising is what lets a repo carrying an
unknown template be reported honestly instead of crashing the command."""


@dataclass(frozen=True)
class TemplateDriftReport:
    """Drift for one attached template."""

    template: str
    recorded_version: str
    current_version: str
    modified: list[str] = field(default_factory=list)
    """Generated files whose contents no longer match the manifest."""
    deleted: list[str] = field(default_factory=list)
    """Generated files the repo no longer has."""
    unchanged: list[str] = field(default_factory=list)

    @property
    def behind(self) -> bool:
        return self.recorded_version != self.current_version

    @property
    def edited(self) -> bool:
        return bool(self.modified or self.deleted)

    @property
    def clean(self) -> bool:
        return not self.behind and not self.edited


@dataclass(frozen=True)
class RepoDriftReport:
    """Composite drift across every template attached to one repo."""

    reports: list[TemplateDriftReport] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    """Attached templates this build ships no descriptor for."""

    @property
    def behind(self) -> bool:
        return any(report.behind for report in self.reports)

    @property
    def edited(self) -> bool:
        return any(report.edited for report in self.reports)

    @property
    def clean(self) -> bool:
        # An unresolved template counts against clean. "I cannot verify this
        # repo" is a drift result, not a pass -- reporting it clean would be a
        # false all-clear on exactly the repos most likely to need attention.
        return not self.behind and not self.edited and not self.unresolved

    @property
    def modified(self) -> list[str]:
        return [path for report in self.reports for path in report.modified]

    @property
    def deleted(self) -> list[str]:
        return [path for report in self.reports for path in report.deleted]

    @property
    def unchanged(self) -> list[str]:
        return [path for report in self.reports for path in report.unchanged]


def check_drift(
    repo_dir: Path, record: TemplateRecord, current_version: str
) -> TemplateDriftReport:
    """Classify every file one template claims responsibility for.

    Three outcomes, and each drives different upgrade behaviour: an unchanged
    file can be replaced outright, a modified one needs a three-way merge, and a
    deleted one was removed deliberately and is left alone.
    """
    modified: list[str] = []
    deleted: list[str] = []
    unchanged: list[str] = []

    for path, recorded_digest in sorted(record.files.items()):
        target = repo_dir / path
        if not target.is_file():
            deleted.append(path)
        elif file_digest(target) != recorded_digest:
            modified.append(path)
        else:
            unchanged.append(path)

    return TemplateDriftReport(
        template=record.template,
        recorded_version=record.version,
        current_version=current_version,
        modified=modified,
        deleted=deleted,
        unchanged=unchanged,
    )


def check_repo_drift(
    repo_dir: Path, manifest: Manifest, resolve_version: VersionResolver
) -> RepoDriftReport:
    """Classify every template attached to a repo.

    Templates the resolver does not know are collected rather than skipped: a
    repo scaffolded by a newer ANSARI must not be reported as clean just because
    this build cannot see what it is carrying.
    """
    reports: list[TemplateDriftReport] = []
    unresolved: list[str] = []

    for record in manifest.templates:
        current_version = resolve_version(record.template)
        if current_version is None:
            unresolved.append(record.template)
            continue
        reports.append(check_drift(repo_dir, record, current_version))

    return RepoDriftReport(reports=reports, unresolved=unresolved)


def unresolved_templates(manifest: Manifest, resolve_version: VersionResolver) -> list[str]:
    """Attached templates this build ships no descriptor for."""
    return [r.template for r in manifest.templates if resolve_version(r.template) is None]


def ensure_writable(
    manifest: Manifest,
    resolve_version: VersionResolver,
    *,
    allow_unresolved: bool = False,
) -> None:
    """Refuse a write onto a manifest carrying an entry this build cannot read.

    `check` only has to *name* an unresolved template. A write has to refuse,
    because the path-overlap invariant becomes unenforceable: the files owned by
    an unresolved template are exactly the ones that cannot be read, so a new
    template could silently claim a file that is already owned. Writing anyway
    would produce a manifest asserting the repo is fully described while one
    entry in it is unverifiable.

    `allow_unresolved` exists for the genuine case of a colleague's unmerged
    branch template. It does not relax the overlap check against entries that
    *can* be read, and it never rewrites the unresolved entry.
    """
    if allow_unresolved:
        return
    unresolved = unresolved_templates(manifest, resolve_version)
    if unresolved:
        raise UnresolvedTemplateError(
            "refusing to write: this repo carries template(s) this ANSARI cannot "
            f"resolve ({', '.join(unresolved)}). It was scaffolded by a newer "
            "ANSARI; upgrade, or pass --allow-unresolved to attach anyway."
        )
