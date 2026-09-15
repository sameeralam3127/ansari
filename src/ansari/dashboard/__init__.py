"""The fleet dashboard: `ansari check --fleet` as a page people can read.

Fleet health, which templates are adopted where, and drift by template type, as
one self-contained HTML file: no server, nothing fetched, openable from disk or
uploaded as a CI artifact. It is built from the same `FleetReport` that
`check --fleet` prints, so the page and the terminal can't disagree.

Like `scaffold/`, this never writes: the CLI decides where the page goes.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from jinja2 import Environment, FileSystemLoader

from ansari.scaffold import FleetReport, TemplateDriftReport

CURRENT = "current"
EDITED = "edited"
BEHIND = "behind"
UNVERIFIABLE = "unverifiable"
UNREADABLE = "unreadable"

STATES = (CURRENT, EDITED, BEHIND, UNVERIFIABLE, UNREADABLE)
"""Least to most severe. A repo, or an attachment, is counted once, under its most
severe state, so a breakdown always adds up to its total. Behind outranks edited
because `sync` has work to do there; an edit may well be deliberate."""

LABELS = {
    CURRENT: "On the golden path",
    EDITED: "Edited",
    BEHIND: "Behind",
    UNVERIFIABLE: "Cannot verify",
    UNREADABLE: "Unreadable manifest",
}

PAGE = "dashboard.html.j2"


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@dataclass(frozen=True)
class Segment:
    """One state's share of a breakdown."""

    state: str
    count: int


def _breakdown(states: Iterable[str]) -> tuple[Segment, ...]:
    counts = Counter(states)
    return tuple(Segment(state, counts[state]) for state in STATES if counts[state])


def _most_severe(states: Iterable[str]) -> str:
    return max(states, key=STATES.index, default=CURRENT)


@dataclass(frozen=True)
class Attachment:
    """One template attached to one repo."""

    template: str
    state: str
    recorded_version: str | None = None
    """None for a template this build can't resolve: its entry can't be checked."""
    current_version: str | None = None
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()

    @classmethod
    def from_report(cls, report: TemplateDriftReport) -> Self:
        state = BEHIND if report.behind else EDITED if report.edited else CURRENT
        return cls(
            template=report.template,
            state=state,
            recorded_version=report.recorded_version,
            current_version=report.current_version,
            modified=tuple(report.modified),
            deleted=tuple(report.deleted),
        )


@dataclass(frozen=True)
class RepoRow:
    label: str
    state: str
    attachments: tuple[Attachment, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class TemplateRow:
    template: str
    current_version: str | None
    """What this build ships, or None when it ships no such template."""
    repos: int
    """Repos attaching this template at least once."""
    adoption: float
    """`repos` as a percent of the fleet's readable repos."""
    attached: int
    behind: int
    edited: int
    unresolved: int
    drift: tuple[Segment, ...]
    """Attachments by most severe state."""
    versions: tuple[tuple[str, int], ...]
    """Recorded version -> attachments, the shipped version first."""

    @property
    def summary(self) -> str:
        """The by-template line `check --fleet` prints, without the name."""
        if self.unresolved == self.attached:
            detail = "cannot verify"
        else:
            detail = f"{self.behind} behind · {self.edited} edited"
            if self.unresolved:
                detail += f" · {self.unresolved} cannot verify"
        return f"{self.attached} attached · {detail}"


@dataclass(frozen=True)
class Dashboard:
    root: str
    generated_at: datetime
    repos: tuple[RepoRow, ...]
    templates: tuple[TemplateRow, ...]

    @property
    def total(self) -> int:
        return len(self.repos)

    @property
    def readable(self) -> int:
        return sum(1 for row in self.repos if row.error is None)

    @property
    def health(self) -> tuple[Segment, ...]:
        return _breakdown(row.state for row in self.repos)

    def count(self, state: str) -> int:
        return sum(1 for row in self.repos if row.state == state)

    @property
    def on_path(self) -> int:
        return self.count(CURRENT)


def build_dashboard(fleet: FleetReport, generated_at: datetime) -> Dashboard:
    repos: list[RepoRow] = []
    attached: dict[str, list[tuple[Path, Attachment]]] = {}

    for result in fleet.repos:
        label = str(result.path.relative_to(fleet.root))
        if result.report is None:
            repos.append(RepoRow(label=label, state=UNREADABLE, error=result.error))
            continue
        attachments = [Attachment.from_report(report) for report in result.report.reports]
        attachments += [
            Attachment(template=name, state=UNVERIFIABLE) for name in result.report.unresolved
        ]
        for attachment in attachments:
            attached.setdefault(attachment.template, []).append((result.path, attachment))
        repos.append(
            RepoRow(
                label=label,
                state=_most_severe(attachment.state for attachment in attachments),
                attachments=tuple(attachments),
            )
        )

    readable = sum(1 for row in repos if row.error is None)
    templates: list[TemplateRow] = []
    # The counts come from by_template() itself, so they match `check --fleet`.
    for name, summary in fleet.by_template().items():
        entries = attached[name]
        current = next((a.current_version for _, a in entries if a.current_version), None)
        versions = Counter(a.recorded_version for _, a in entries if a.recorded_version)
        in_repos = len({path for path, _ in entries})
        templates.append(
            TemplateRow(
                template=name,
                current_version=current,
                repos=in_repos,
                # A template only appears once a readable repo attaches it.
                adoption=100 * in_repos / readable,
                attached=summary.attached,
                behind=summary.behind,
                edited=summary.edited,
                unresolved=summary.unresolved,
                drift=_breakdown(attachment.state for _, attachment in entries),
                versions=tuple(
                    sorted(versions.items(), key=lambda item: (item[0] != current, -item[1]))
                ),
            )
        )

    return Dashboard(
        root=str(fleet.root),
        generated_at=generated_at,
        repos=tuple(repos),
        templates=tuple(templates),
    )


def render_dashboard(dashboard: Dashboard) -> str:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parent),
        # Repo paths and manifest errors come from disk; none of it is markup.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals.update(labels=LABELS, plural=plural)
    return env.get_template(PAGE).render(d=dashboard, BEHIND=BEHIND, UNVERIFIABLE=UNVERIFIABLE)
