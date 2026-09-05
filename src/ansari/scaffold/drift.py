"""Comparing a scaffolded repo against the template it came from.

Read-only by design. Detection ships before modification: a tool that clobbers
hand-edited files gets uninstalled after the first upgrade, so being able to say
"these three files were edited locally, I won't touch them" is what makes an
automated upgrade acceptable at all.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ansari.scaffold.manifest import Manifest, file_digest


@dataclass(frozen=True)
class DriftReport:
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


def check_drift(service_dir: Path, manifest: Manifest, current_version: str) -> DriftReport:
    """Classify every file the manifest claims responsibility for.

    Three outcomes, and each drives different upgrade behaviour: an unchanged
    file can be replaced outright, a modified one needs a three-way merge, and a
    deleted one was removed deliberately and is left alone.
    """
    modified: list[str] = []
    deleted: list[str] = []
    unchanged: list[str] = []

    for path, recorded_digest in sorted(manifest.files.items()):
        target = service_dir / path
        if not target.is_file():
            deleted.append(path)
        elif file_digest(target) != recorded_digest:
            modified.append(path)
        else:
            unchanged.append(path)

    return DriftReport(
        template=manifest.template,
        recorded_version=manifest.version,
        current_version=current_version,
        modified=modified,
        deleted=deleted,
        unchanged=unchanged,
    )
