"""The manifest schema, and the compatibility promise made to existing repos.

Every repo scaffolded before multi-template support carries a schema-1 manifest.
Those repos must keep working with no migration step, so the v1 reader is the
most load-bearing code in this package -- if it is wrong, every already-scaffolded
repo breaks, and no amount of correct template content compensates.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ansari.scaffold import (
    LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    Manifest,
    ManifestError,
    ManifestTooNewError,
    TemplateRecord,
    UnresolvedTemplateError,
    attach_record,
    build_manifest,
    build_record,
    ensure_writable,
    manifest_path,
    overlapping_paths,
    read_manifest,
    unresolved_templates,
    write_manifest,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
V1_FIXTURE = FIXTURES / "manifest_v1_python_service.yaml"


def _repo(tmp_path: Path, contents: dict[str, str]) -> Path:
    for name, body in contents.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return tmp_path


def _install_manifest(repo: Path, body: str) -> Path:
    path = manifest_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _record(template: str, files: dict[str, str], version: str = "1.0.0") -> TemplateRecord:
    return TemplateRecord(
        template=template,
        version=version,
        rendered_at=datetime(2026, 1, 1, tzinfo=UTC),
        variables={},
        files=files,
    )


# --------------------------------------------------------------------------
# Schema 1: the compatibility promise
# --------------------------------------------------------------------------


def test_real_pre_migration_manifest_still_parses(tmp_path: Path) -> None:
    """The golden fixture is a real manifest captured before the migration.

    Not a hand-written approximation of one -- the actual bytes `ansari new`
    produced at commit 3f42919.
    """
    repo = _install_manifest(tmp_path, V1_FIXTURE.read_text()).parent.parent
    manifest = read_manifest(repo)

    assert manifest is not None
    assert manifest.schema == LEGACY_SCHEMA_VERSION
    assert len(manifest.templates) == 1

    record = manifest.templates[0]
    assert record.template == "python-service"
    assert record.version == "1.0.0"
    assert record.variables == {
        "name": "legacy-svc",
        "language": "python",
        "database": "postgres",
    }
    assert len(record.files) == 7
    assert record.files["Dockerfile"].startswith("sha256:")
    assert record.rendered_at == datetime.fromisoformat("2026-09-05T19:35:28.215155+00:00")


def test_reading_a_v1_manifest_does_not_rewrite_it(tmp_path: Path) -> None:
    """`check` is read-only, so a v1 repo that is only ever checked stays v1.

    Silently upgrading the file on read would produce a diff in a repo the user
    only asked a question about.
    """
    original = V1_FIXTURE.read_text()
    repo = _install_manifest(tmp_path, original).parent.parent

    read_manifest(repo)
    read_manifest(repo)

    assert manifest_path(repo).read_text() == original


def test_v1_manifest_over_a_real_tree_reads_clean(tmp_path: Path) -> None:
    """A v1 manifest whose files are all present reports no drift.

    Built by writing a manifest with the current code and downgrading the
    document to the v1 shape -- which is exactly what an old repo looks like --
    so this stays honest as the templates change.
    """
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "README.md": "# svc\n"})
    manifest = build_manifest(
        "python-service", "1.0.0", {"name": "svc"}, repo, ["Dockerfile", "README.md"]
    )
    write_manifest(repo, manifest)

    record = manifest.templates[0]
    _install_manifest(
        repo,
        yaml.safe_dump(
            {
                "template": record.template,
                "version": record.version,
                "rendered_at": record.rendered_at.isoformat(),
                "variables": record.variables,
                "files": record.files,
            }
        ),
    )

    reloaded = read_manifest(repo)
    assert reloaded is not None
    assert reloaded.schema == LEGACY_SCHEMA_VERSION
    assert reloaded.templates[0].files == record.files


def test_v1_variables_are_still_coerced_to_strings(tmp_path: Path) -> None:
    """Widening the variable type must not change how an existing repo reads.

    Schema 1 was written when every value was stringified, so it is read back
    stringified. Only schema 2 preserves YAML scalars.
    """
    repo = _install_manifest(
        tmp_path,
        "template: svc\nversion: 1.0.0\nrendered_at: 2026-01-01T00:00:00\n"
        "variables:\n  replicas: 3\n  enabled: true\nfiles: {}\n",
    ).parent.parent

    manifest = read_manifest(repo)
    assert manifest is not None
    assert manifest.templates[0].variables == {"replicas": "3", "enabled": "True"}


# --------------------------------------------------------------------------
# Schema 2
# --------------------------------------------------------------------------


def test_v2_manifest_round_trips(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    original = build_manifest("python-service", "1.0.0", {"name": "svc"}, repo, ["Dockerfile"])

    write_manifest(repo, original)
    loaded = read_manifest(repo)

    assert loaded is not None
    assert loaded.schema == SCHEMA_VERSION
    assert loaded.templates == original.templates


def test_written_manifest_declares_its_schema(tmp_path: Path) -> None:
    """The field whose absence made v1 compatibility awkward. Never omit it."""
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    write_manifest(repo, build_manifest("python-service", "1.0.0", {}, repo, ["Dockerfile"]))

    raw = yaml.safe_load(manifest_path(repo).read_text())
    assert raw["schema"] == SCHEMA_VERSION
    assert isinstance(raw["templates"], list)


def test_v2_preserves_non_scalar_variables(tmp_path: Path) -> None:
    """Terraform wants provider lists; Ansible wants a platforms matrix."""
    repo = _repo(tmp_path, {"main.tf": "# module\n"})
    manifest = build_manifest(
        "terraform-module",
        "0.1.0",
        {"name": "vpc", "providers": ["aws", "random"], "replicas": 3, "public": True},
        repo,
        ["main.tf"],
    )
    write_manifest(repo, manifest)

    loaded = read_manifest(repo)
    assert loaded is not None
    assert loaded.templates[0].variables == {
        "name": "vpc",
        "providers": ["aws", "random"],
        "replicas": 3,
        "public": True,
    }


def test_a_repo_can_carry_two_templates(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path, {"Dockerfile": "FROM python\n", "helm/svc/templates/hpa.yaml": "kind: H\n"}
    )
    manifest = build_manifest("python-service", "1.0.0", {}, repo, ["Dockerfile"])
    manifest = attach_record(
        manifest,
        build_record("k8s-scaling", "0.1.0", {}, repo, ["helm/svc/templates/hpa.yaml"]),
    )
    write_manifest(repo, manifest)

    loaded = read_manifest(repo)
    assert loaded is not None
    assert [r.template for r in loaded.templates] == ["python-service", "k8s-scaling"]
    assert loaded.claimed_paths() == {
        "Dockerfile": "python-service",
        "helm/svc/templates/hpa.yaml": "k8s-scaling",
    }


def test_variables_of_an_unsupported_type_are_rejected(tmp_path: Path) -> None:
    repo = _install_manifest(
        tmp_path,
        "schema: 2\ntemplates:\n  - template: svc\n    version: 1.0.0\n"
        "    rendered_at: 2026-01-01T00:00:00\n    variables:\n      nested: {a: 1}\n"
        "    files: {}\n",
    ).parent.parent
    with pytest.raises(ManifestError):
        read_manifest(repo)


# --------------------------------------------------------------------------
# Schema dispatch
# --------------------------------------------------------------------------


def test_a_newer_schema_is_refused_not_misread(tmp_path: Path) -> None:
    """A manifest from a newer ANSARI is a distinct situation from a broken one.

    Reading it as a shape we do understand would silently drop whatever the
    newer schema added.
    """
    repo = _install_manifest(tmp_path, "schema: 99\ntemplates: []\n").parent.parent
    with pytest.raises(ManifestTooNewError) as exc:
        read_manifest(repo)
    assert "99" in str(exc.value)


def test_manifest_too_new_is_a_manifest_error() -> None:
    """Callers that only catch ManifestError must not leak a traceback."""
    assert issubclass(ManifestTooNewError, ManifestError)


@pytest.mark.parametrize("value", ["two", 0, True, -1])
def test_a_non_version_schema_value_is_rejected(tmp_path: Path, value: object) -> None:
    # `schema: true` is a malformed document, not schema 1 -- bool is an int
    # subclass, so this would otherwise slip through.
    repo = _install_manifest(
        tmp_path, yaml.safe_dump({"schema": value, "templates": []})
    ).parent.parent
    with pytest.raises(ManifestError):
        read_manifest(repo)


def test_v2_requires_a_non_empty_templates_list(tmp_path: Path) -> None:
    repo = _install_manifest(tmp_path, "schema: 2\ntemplates: []\n").parent.parent
    with pytest.raises(ManifestError):
        read_manifest(repo)


# --------------------------------------------------------------------------
# The path-overlap invariant
# --------------------------------------------------------------------------


def test_overlapping_paths_finds_files_with_two_owners() -> None:
    conflicts = overlapping_paths(
        [
            _record("python-service", {"README.md": "sha256:a", "Dockerfile": "sha256:b"}),
            _record("k8s-scaling", {"README.md": "sha256:c"}),
        ]
    )
    assert conflicts == {"README.md": ["python-service", "k8s-scaling"]}


def test_writing_a_manifest_with_overlapping_paths_is_refused(tmp_path: Path) -> None:
    manifest = Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            _record("python-service", {"README.md": "sha256:a"}),
            _record("k8s-scaling", {"README.md": "sha256:b"}),
        ],
    )
    with pytest.raises(ManifestError, match="more than one template"):
        write_manifest(tmp_path, manifest)


def test_a_hand_merged_manifest_with_overlapping_paths_is_refused(tmp_path: Path) -> None:
    """Enforced on read too, not only on write.

    The manifest is a file a human can edit, so the invariant cannot rely on
    every writer having been ANSARI.
    """
    repo = _install_manifest(
        tmp_path,
        "schema: 2\ntemplates:\n"
        "  - template: a\n    version: 1.0.0\n    rendered_at: 2026-01-01T00:00:00\n"
        "    files:\n      README.md: sha256:x\n"
        "  - template: b\n    version: 1.0.0\n    rendered_at: 2026-01-01T00:00:00\n"
        "    files:\n      README.md: sha256:y\n",
    ).parent.parent
    with pytest.raises(ManifestError, match="more than one template"):
        read_manifest(repo)


def test_attach_refuses_a_template_claiming_an_owned_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"README.md": "# svc\n"})
    manifest = build_manifest("python-service", "1.0.0", {}, repo, ["README.md"])

    with pytest.raises(ManifestError, match="already owned"):
        attach_record(manifest, build_record("k8s-scaling", "0.1.0", {}, repo, ["README.md"]))


def test_attach_upgrades_a_v1_manifest_to_the_current_schema(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "hpa.yaml": "kind: H\n"})
    _install_manifest(
        repo,
        "template: python-service\nversion: 1.0.0\nrendered_at: 2026-01-01T00:00:00\n"
        "variables:\n  name: svc\nfiles:\n  Dockerfile: sha256:x\n",
    )
    legacy = read_manifest(repo)
    assert legacy is not None
    assert legacy.schema == LEGACY_SCHEMA_VERSION

    upgraded = attach_record(legacy, build_record("k8s-scaling", "0.1.0", {}, repo, ["hpa.yaml"]))

    assert upgraded.schema == SCHEMA_VERSION
    # The original entry survives intact -- an upgrade must not lose provenance.
    assert upgraded.templates[0] == legacy.templates[0]
    assert upgraded.templates[1].template == "k8s-scaling"


# --------------------------------------------------------------------------
# Errors that predate this change and must keep behaving
# --------------------------------------------------------------------------


def test_read_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_read_manifest_raises_on_malformed_yaml(tmp_path: Path) -> None:
    _install_manifest(tmp_path, "template: [unclosed\n")
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_read_manifest_raises_when_required_fields_are_missing(tmp_path: Path) -> None:
    _install_manifest(tmp_path, yaml.safe_dump({"template": "svc"}))
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_manifest_rejects_a_non_mapping() -> None:
    with pytest.raises(ManifestError):
        Manifest.from_dict(["not", "a", "mapping"])


def test_template_entry_rejects_a_non_mapping(tmp_path: Path) -> None:
    _install_manifest(tmp_path, "schema: 2\ntemplates:\n  - not-a-mapping\n")
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_manifest_accepts_a_yaml_parsed_timestamp(tmp_path: Path) -> None:
    # PyYAML resolves unquoted ISO-8601 scalars to datetime before we see them.
    _install_manifest(
        tmp_path,
        "template: svc\nversion: 1.0.0\nrendered_at: 2026-01-01T00:00:00\nfiles: {}\n",
    )
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.templates[0].rendered_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_manifest_rejects_an_invalid_timestamp(tmp_path: Path) -> None:
    _install_manifest(
        tmp_path, "template: svc\nversion: 1.0.0\nrendered_at: 'not-a-date'\nfiles: {}\n"
    )
    with pytest.raises(ManifestError, match="rendered_at"):
        read_manifest(tmp_path)


def test_manifest_rejects_non_mapping_files(tmp_path: Path) -> None:
    _install_manifest(
        tmp_path,
        "template: svc\nversion: 1.0.0\nrendered_at: 2026-01-01T00:00:00\nfiles: [a, b]\n",
    )
    with pytest.raises(ManifestError, match="files"):
        read_manifest(tmp_path)


def test_manifest_rejects_non_mapping_variables(tmp_path: Path) -> None:
    _install_manifest(
        tmp_path,
        "template: svc\nversion: 1.0.0\nrendered_at: 2026-01-01T00:00:00\n"
        "variables: [a]\nfiles: {}\n",
    )
    with pytest.raises(ManifestError, match="variables"):
        read_manifest(tmp_path)


def test_record_for_finds_an_attached_template(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    manifest = build_manifest("python-service", "1.0.0", {}, repo, ["Dockerfile"])

    assert manifest.record_for("python-service") is not None
    assert manifest.record_for("terraform-module") is None


# --------------------------------------------------------------------------
# Writes refuse against an unresolved entry (see README.md, 'The manifest')
# --------------------------------------------------------------------------


def _two_template_manifest() -> Manifest:
    return Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            _record("python-service", {"Dockerfile": "sha256:a"}),
            _record("from-the-future", {"future.tf": "sha256:b"}),
        ],
    )


def test_writes_refuse_when_a_template_cannot_be_resolved() -> None:
    """`check` may name an unresolved entry; a write must refuse outright.

    The paths owned by an unresolved template are exactly the ones that cannot
    be read, so the path-overlap invariant is unenforceable against it -- a new
    template could silently claim a file that is already owned.
    """
    with pytest.raises(UnresolvedTemplateError, match="from-the-future"):
        ensure_writable(_two_template_manifest(), {"python-service": "1.0.0"}.get)


def test_writes_proceed_when_every_template_resolves() -> None:
    manifest = Manifest(
        schema=SCHEMA_VERSION, templates=[_record("python-service", {"Dockerfile": "sha256:a"})]
    )
    ensure_writable(manifest, {"python-service": "1.0.0"}.get)  # does not raise


def test_allow_unresolved_is_an_explicit_opt_in() -> None:
    ensure_writable(
        _two_template_manifest(), {"python-service": "1.0.0"}.get, allow_unresolved=True
    )


def test_unresolved_refusal_is_a_manifest_error() -> None:
    # Callers catching ManifestError must not leak a traceback.
    assert issubclass(UnresolvedTemplateError, ManifestError)


def test_unresolved_templates_lists_only_the_unknown_ones() -> None:
    assert unresolved_templates(_two_template_manifest(), {"python-service": "1.0.0"}.get) == [
        "from-the-future"
    ]
