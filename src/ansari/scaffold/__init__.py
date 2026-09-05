"""Template resolution, manifest tracking, and drift detection.

Pure functions over files and paths — no database, no network. The CLI and the
API are both thin callers over this package.
"""

from ansari.scaffold.drift import DriftReport, check_drift
from ansari.scaffold.manifest import (
    MANIFEST_DIR,
    MANIFEST_NAME,
    Manifest,
    ManifestError,
    file_digest,
    manifest_path,
    read_manifest,
    write_manifest,
)
from ansari.scaffold.template import TemplateError, TemplateSpec, bundled_template, load_template

__all__ = [
    "MANIFEST_DIR",
    "MANIFEST_NAME",
    "DriftReport",
    "Manifest",
    "ManifestError",
    "TemplateError",
    "TemplateSpec",
    "bundled_template",
    "check_drift",
    "file_digest",
    "load_template",
    "manifest_path",
    "read_manifest",
    "write_manifest",
]
