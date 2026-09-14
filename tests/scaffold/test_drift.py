"""Drift classification, per template and composed across a repo.

Manifest parsing and the schema-1 compatibility promise live in
`test_manifest_schema.py`; this file is about comparison.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ansari.scaffold import (
    SCHEMA_VERSION,
    Manifest,
    RepoDriftReport,
    TemplateError,
    TemplateRecord,
    build_manifest,
    build_record,
    bundled_template,
    bundled_version,
    check_drift,
    check_repo_drift,
    file_digest,
    find_bundled_template,
)


def _repo(tmp_path: Path, contents: dict[str, str]) -> Path:
    for name, body in contents.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return tmp_path


def _record(repo: Path, template: str, paths: list[str], version: str = "1.0.0") -> TemplateRecord:
    return build_record(template, version, {}, repo, paths)


def _fixed_version(version: str | None) -> object:
    """A resolver that answers the same for every template."""
    return lambda _name: version


# --------------------------------------------------------------------------
# One template
# --------------------------------------------------------------------------


def test_unchanged_template_is_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "README.md": "# svc\n"})
    record = _record(repo, "python-service", ["Dockerfile", "README.md"])

    report = check_drift(repo, record, current_version="1.0.0")

    assert report.clean
    assert not report.behind
    assert not report.edited
    assert report.unchanged == ["Dockerfile", "README.md"]


def test_hand_edited_file_is_reported_as_modified(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    record = _record(repo, "python-service", ["Dockerfile"])
    (repo / "Dockerfile").write_text("FROM python\nRUN echo edited\n")

    report = check_drift(repo, record, current_version="1.0.0")

    assert report.modified == ["Dockerfile"]
    assert report.edited
    assert not report.clean


def test_deleted_file_is_reported_separately_from_a_modified_one(tmp_path: Path) -> None:
    # These drive different upgrade behaviour: a modified file gets merged, a
    # deleted one was removed deliberately and is left alone.
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "README.md": "# svc\n"})
    record = _record(repo, "python-service", ["Dockerfile", "README.md"])
    (repo / "README.md").unlink()

    report = check_drift(repo, record, current_version="1.0.0")

    assert report.deleted == ["README.md"]
    assert report.modified == []
    assert report.unchanged == ["Dockerfile"]


def test_a_template_can_be_behind_while_locally_untouched(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    record = _record(repo, "python-service", ["Dockerfile"])

    report = check_drift(repo, record, current_version="1.5.0")

    assert report.behind
    assert not report.edited
    assert not report.clean


@pytest.mark.parametrize(
    "template", ["python-service", "terraform-module", "ansible-role", "k8s-scaling"]
)
def test_drift_classification_is_independent_of_template_type(
    tmp_path: Path, template: str
) -> None:
    """The comparison core compares paths to hashes and nothing else.

    Parametrized deliberately: these cases used to hardcode "python-service" as
    an arbitrary label, which hid the fact that nothing here is service-specific
    and left the other template types uncovered.
    """
    repo = _repo(tmp_path, {"a.txt": "one\n", "b.txt": "two\n"})
    record = _record(repo, template, ["a.txt", "b.txt"])
    (repo / "a.txt").write_text("edited\n")

    report = check_drift(repo, record, current_version="1.0.0")

    assert report.template == template
    assert report.modified == ["a.txt"]
    assert report.unchanged == ["b.txt"]


# --------------------------------------------------------------------------
# Composite: several templates on one repo
# --------------------------------------------------------------------------


def test_composite_is_clean_when_every_template_is(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "hpa.yaml": "kind: H\n"})
    manifest = Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            _record(repo, "python-service", ["Dockerfile"]),
            _record(repo, "k8s-scaling", ["hpa.yaml"]),
        ],
    )

    report = check_repo_drift(repo, manifest, _fixed_version("1.0.0"))

    assert report.clean
    assert len(report.reports) == 2
    assert report.unchanged == ["Dockerfile", "hpa.yaml"]


def test_one_drifted_template_makes_the_whole_repo_drifted(tmp_path: Path) -> None:
    """The composite verdict is the point of the multi-template manifest.

    A repo is on the golden path only if every attached template is.
    """
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "hpa.yaml": "kind: H\n"})
    manifest = Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            _record(repo, "python-service", ["Dockerfile"]),
            _record(repo, "k8s-scaling", ["hpa.yaml"]),
        ],
    )
    (repo / "hpa.yaml").write_text("kind: HorizontalPodAutoscaler\n")

    report = check_repo_drift(repo, manifest, _fixed_version("1.0.0"))

    assert not report.clean
    assert report.edited
    assert report.modified == ["hpa.yaml"]
    # The clean template is still reported as clean -- the composite verdict
    # must not smear one template's drift across the others.
    assert report.reports[0].clean
    assert not report.reports[1].clean


def test_behind_on_one_template_only(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n", "hpa.yaml": "kind: H\n"})
    manifest = Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            _record(repo, "python-service", ["Dockerfile"], version="1.0.0"),
            _record(repo, "k8s-scaling", ["hpa.yaml"], version="0.1.0"),
        ],
    )

    versions = {"python-service": "1.0.0", "k8s-scaling": "0.2.0"}
    report = check_repo_drift(repo, manifest, versions.get)

    assert report.behind
    assert not report.edited
    assert [r.behind for r in report.reports] == [False, True]


# --------------------------------------------------------------------------
# Unresolved templates
# --------------------------------------------------------------------------


def test_an_unresolved_template_is_named_not_skipped(tmp_path: Path) -> None:
    """A template this build does not ship must not be silently ignored.

    Skipping it would report a repo clean on the strength of the half of it we
    happen to understand.
    """
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    manifest = Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            _record(repo, "python-service", ["Dockerfile"]),
            TemplateRecord(
                template="from-the-future",
                version="9.0.0",
                rendered_at=datetime(2026, 1, 1, tzinfo=UTC),
                variables={},
                files={"future.tf": "sha256:whatever"},
            ),
        ],
    )

    report = check_repo_drift(repo, manifest, {"python-service": "1.0.0"}.get)

    assert report.unresolved == ["from-the-future"]
    assert not report.clean
    # Not behind and not edited -- unverifiable is its own state, and conflating
    # it with either would mis-describe what is wrong.
    assert not report.behind
    assert not report.edited
    assert len(report.reports) == 1


def test_an_empty_report_is_clean() -> None:
    assert RepoDriftReport().clean


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def test_file_digest_is_content_addressed(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("same\n")
    b.write_text("same\n")
    assert file_digest(a) == file_digest(b)
    assert file_digest(a).startswith("sha256:")

    b.write_text("different\n")
    assert file_digest(a) != file_digest(b)


def test_bundled_python_template_declares_a_version_and_files() -> None:
    spec = bundled_template("python")
    assert spec.name == "python-service"
    assert spec.version
    assert "Dockerfile.j2" in spec.files


def test_bundled_template_rejects_an_unknown_language() -> None:
    with pytest.raises(TemplateError):
        bundled_template("rust")


def test_templates_resolve_by_their_own_name() -> None:
    """The resolution path a manifest uses.

    Every manifest ever written records `template:` directly, so this is what
    makes pre-migration repos readable without migrating them.
    """
    spec = find_bundled_template("python-service")
    assert spec is not None
    assert spec.name == "python-service"
    assert bundled_version("python-service") == spec.version


def test_an_unknown_template_name_resolves_to_none() -> None:
    # None rather than an exception: "this build ships no such template" is a
    # reportable state, not a failure.
    assert find_bundled_template("from-the-future") is None
    assert bundled_version("from-the-future") is None


@pytest.mark.parametrize("name", ["", "../../etc", "a/b", ".hidden", "x\\y"])
def test_template_resolution_refuses_to_escape_the_bundled_directory(name: str) -> None:
    # The name comes out of a manifest, which is a file a human can edit.
    assert find_bundled_template(name) is None


def test_template_destinations_are_rendered_with_the_service_name() -> None:
    spec = bundled_template("python")
    destinations = spec.destinations({"name": "payment-api"})
    assert destinations["helm/Chart.yaml.j2"] == "helm/payment-api/Chart.yaml"


def test_build_manifest_produces_a_single_template_manifest(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"Dockerfile": "FROM python\n"})
    manifest = build_manifest("python-service", "1.0.0", {"name": "svc"}, repo, ["Dockerfile"])

    assert manifest.schema == SCHEMA_VERSION
    assert len(manifest.templates) == 1
    assert manifest.templates[0].files["Dockerfile"].startswith("sha256:")
