"""Drift across a fleet: every ANSARI-tracked repo under a directory.

This is the question single-repo `check` can't answer -- who is behind, and on
what -- asked of a directory of checkouts. Like everything in this package it
reads files and nothing else: no API, no network, no cloning.

A repo whose manifest can't be read is reported as an error rather than
skipped. A fleet report that silently drops the repos it couldn't understand is
a false all-clear on exactly the repos most likely to need attention.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ansari.scaffold.drift import RepoDriftReport, VersionResolver, check_repo_drift
from ansari.scaffold.manifest import MANIFEST_DIR, MANIFEST_NAME, ManifestError, read_manifest

SKIPPED_DIRS = frozenset(
    {
        MANIFEST_DIR,
        ".git",
        ".hg",
        ".svn",
        ".terraform",
        ".ansible",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)
"""Version control, dependency, and tool caches: never where a repo lives, and
often large enough to make a scan slow."""


@dataclass(frozen=True)
class RepoResult:
    """One repo in the fleet: its drift, or why it couldn't be checked."""

    path: Path
    report: RepoDriftReport | None = None
    error: str | None = None

    @property
    def clean(self) -> bool:
        return self.error is None and self.report is not None and self.report.clean


@dataclass(frozen=True)
class TemplateSummary:
    """How one template type is doing across every repo it's attached to.

    Counts attachments, not repos: a repo that attaches a template twice counts
    twice, because each attachment can fall behind on its own.
    """

    template: str
    attached: int = 0
    behind: int = 0
    edited: int = 0
    unresolved: int = 0


@dataclass(frozen=True)
class FleetReport:
    root: Path
    repos: list[RepoResult] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        # Finding nothing isn't clean. A fleet check pointed at the wrong
        # directory would otherwise pass, and keep passing.
        return bool(self.repos) and all(result.clean for result in self.repos)

    @property
    def off_path(self) -> list[RepoResult]:
        return [result for result in self.repos if not result.clean]

    def by_template(self) -> dict[str, TemplateSummary]:
        counts: dict[str, dict[str, int]] = {}

        def bump(template: str, key: str) -> None:
            entry = counts.setdefault(
                template, {"attached": 0, "behind": 0, "edited": 0, "unresolved": 0}
            )
            entry[key] += 1

        for result in self.repos:
            if result.report is None:
                continue
            for report in result.report.reports:
                bump(report.template, "attached")
                if report.behind:
                    bump(report.template, "behind")
                if report.edited:
                    bump(report.template, "edited")
            for name in result.report.unresolved:
                bump(name, "attached")
                bump(name, "unresolved")

        return {name: TemplateSummary(template=name, **counts[name]) for name in sorted(counts)}


def discover_repos(root: Path) -> list[Path]:
    """Every directory under `root`, `root` included, that carries a manifest.

    Descends into repos as well as around them, since a monorepo can hold several
    ANSARI-tracked directories. Never follows a symlinked directory, so a link
    loop can't hang the scan or count a repo twice.
    """
    found: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        if (directory / MANIFEST_DIR / MANIFEST_NAME).is_file():
            found.append(directory)
        try:
            children = list(directory.iterdir())
        except OSError:
            continue  # unreadable directory: nothing we can check inside it
        for child in children:
            if child.name in SKIPPED_DIRS or child.is_symlink() or not child.is_dir():
                continue
            pending.append(child)
    return sorted(found)


def check_fleet(root: Path, resolve_version: VersionResolver) -> FleetReport:
    """Check every repo under `root`. Read-only, like single-repo `check`."""
    results: list[RepoResult] = []
    for repo in discover_repos(root):
        try:
            manifest = read_manifest(repo)
        except ManifestError as exc:
            results.append(RepoResult(path=repo, error=str(exc)))
            continue
        if manifest is None:  # removed between discovery and reading
            continue
        report = check_repo_drift(repo, manifest, resolve_version)
        results.append(RepoResult(path=repo, report=report))
    return FleetReport(root=root, repos=results)
