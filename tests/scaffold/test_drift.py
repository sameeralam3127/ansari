from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ansari.scaffold import (
    Manifest,
    ManifestError,
    TemplateError,
    bundled_template,
    check_drift,
    file_digest,
    read_manifest,
    write_manifest,
)
from ansari.scaffold.manifest import build_manifest


def _service(tmp_path: Path, contents: dict[str, str]) -> Path:
    for name, body in contents.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return tmp_path


def test_manifest_round_trips(tmp_path: Path) -> None:
    service = _service(tmp_path, {"Dockerfile": "FROM python\n"})
    original = build_manifest("python-service", "1.0.0", {"name": "svc"}, service, ["Dockerfile"])

    write_manifest(service, original)
    loaded = read_manifest(service)

    assert loaded is not None
    assert loaded.template == original.template
    assert loaded.version == original.version
    assert loaded.variables == original.variables
    assert loaded.files == original.files
    assert loaded.rendered_at == original.rendered_at


def test_read_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_read_manifest_raises_on_malformed_yaml(tmp_path: Path) -> None:
    # A missing manifest and an unreadable one are different situations: the
    # first means "not our repo", the second means "something is wrong".
    (tmp_path / ".ansari").mkdir()
    (tmp_path / ".ansari" / "manifest.yaml").write_text("template: [unclosed\n")
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_read_manifest_raises_when_required_fields_are_missing(tmp_path: Path) -> None:
    (tmp_path / ".ansari").mkdir()
    (tmp_path / ".ansari" / "manifest.yaml").write_text(yaml.safe_dump({"template": "svc"}))
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_manifest_accepts_a_yaml_parsed_timestamp(tmp_path: Path) -> None:
    # PyYAML resolves unquoted ISO-8601 scalars to datetime before we see them.
    (tmp_path / ".ansari").mkdir()
    (tmp_path / ".ansari" / "manifest.yaml").write_text(
        "template: svc\nversion: 1.0.0\nrendered_at: 2026-01-01T00:00:00\nfiles: {}\n"
    )
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.rendered_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_unchanged_service_is_clean(tmp_path: Path) -> None:
    service = _service(tmp_path, {"Dockerfile": "FROM python\n", "README.md": "# svc\n"})
    manifest = build_manifest("python-service", "1.0.0", {}, service, ["Dockerfile", "README.md"])

    report = check_drift(service, manifest, current_version="1.0.0")

    assert report.clean
    assert not report.behind
    assert not report.edited
    assert report.unchanged == ["Dockerfile", "README.md"]


def test_hand_edited_file_is_reported_as_modified(tmp_path: Path) -> None:
    service = _service(tmp_path, {"Dockerfile": "FROM python\n"})
    manifest = build_manifest("python-service", "1.0.0", {}, service, ["Dockerfile"])
    (service / "Dockerfile").write_text("FROM python\nRUN echo edited\n")

    report = check_drift(service, manifest, current_version="1.0.0")

    assert report.modified == ["Dockerfile"]
    assert report.edited
    assert not report.clean


def test_deleted_file_is_reported_separately_from_a_modified_one(tmp_path: Path) -> None:
    # These drive different upgrade behaviour: a modified file gets merged, a
    # deleted one was removed deliberately and is left alone.
    service = _service(tmp_path, {"Dockerfile": "FROM python\n", "README.md": "# svc\n"})
    manifest = build_manifest("python-service", "1.0.0", {}, service, ["Dockerfile", "README.md"])
    (service / "README.md").unlink()

    report = check_drift(service, manifest, current_version="1.0.0")

    assert report.deleted == ["README.md"]
    assert report.modified == []
    assert report.unchanged == ["Dockerfile"]


def test_a_service_can_be_behind_while_locally_untouched(tmp_path: Path) -> None:
    service = _service(tmp_path, {"Dockerfile": "FROM python\n"})
    manifest = build_manifest("python-service", "1.0.0", {}, service, ["Dockerfile"])

    report = check_drift(service, manifest, current_version="1.5.0")

    assert report.behind
    assert not report.edited
    assert not report.clean


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


def test_template_destinations_are_rendered_with_the_service_name() -> None:
    spec = bundled_template("python")
    destinations = spec.destinations({"name": "payment-api"})
    assert destinations["helm/Chart.yaml.j2"] == "helm/payment-api/Chart.yaml"


def test_manifest_dataclass_rejects_a_non_mapping() -> None:
    with pytest.raises(ManifestError):
        Manifest.from_dict(["not", "a", "mapping"])
