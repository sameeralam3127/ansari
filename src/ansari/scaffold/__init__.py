"""Template resolution, manifest tracking, and drift detection.

Pure functions over files and paths — no database, no network. The CLI and the
API are both thin callers over this package.
"""

from ansari.scaffold.drift import (
    RepoDriftReport,
    TemplateDriftReport,
    VersionResolver,
    check_drift,
    check_repo_drift,
    ensure_writable,
    unresolved_templates,
)
from ansari.scaffold.manifest import (
    LEGACY_SCHEMA_VERSION,
    MANIFEST_DIR,
    MANIFEST_NAME,
    SCHEMA_VERSION,
    Manifest,
    ManifestError,
    ManifestTooNewError,
    TemplateRecord,
    UnresolvedTemplateError,
    VariableValue,
    attach_record,
    build_manifest,
    build_record,
    file_digest,
    manifest_path,
    overlapping_paths,
    read_manifest,
    write_manifest,
)
from ansari.scaffold.template import (
    TemplateError,
    TemplateSpec,
    bundled_template,
    bundled_version,
    find_bundled_template,
    load_template,
)

__all__ = [
    "LEGACY_SCHEMA_VERSION",
    "MANIFEST_DIR",
    "MANIFEST_NAME",
    "SCHEMA_VERSION",
    "Manifest",
    "ManifestError",
    "ManifestTooNewError",
    "RepoDriftReport",
    "TemplateDriftReport",
    "TemplateError",
    "TemplateRecord",
    "TemplateSpec",
    "UnresolvedTemplateError",
    "VariableValue",
    "VersionResolver",
    "attach_record",
    "build_manifest",
    "build_record",
    "bundled_template",
    "bundled_version",
    "check_drift",
    "check_repo_drift",
    "ensure_writable",
    "file_digest",
    "find_bundled_template",
    "load_template",
    "manifest_path",
    "overlapping_paths",
    "read_manifest",
    "unresolved_templates",
    "write_manifest",
]
