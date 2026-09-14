"""Attaching a second template to a repo, and the chart that results.

`attach` is the first write path that touches a repo holding files ANSARI did not
just create, so many of these tests are refusals, and each proves that a refused
attach leaves the repo and its manifest byte-for-byte as they were.

The Helm tests at the end render the real chart. They exist because hashing
files can prove a template was written faithfully, but not that what it wrote
deploys correctly -- and "would this go to production?" is the first tripwire.
"""

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import (
    SCHEMA_VERSION,
    AttachConflictError,
    Manifest,
    TemplateError,
    TemplateRecord,
    TemplateSpec,
    UnresolvedTemplateError,
    attach_template,
    bundled_version,
    check_repo_drift,
    default_name,
    find_bundled_template,
    generate,
    load_template,
    manifest_path,
    read_manifest,
)

runner = CliRunner()
CHART = "helm/payment-api"
SCALING = f"{CHART}/autoscaling.yaml"
HPA = f"{CHART}/templates/hpa.yaml"
PDB = f"{CHART}/templates/pdb.yaml"


def _service(tmp_path: Path, name: str = "payment-api") -> Path:
    result = runner.invoke(app, ["new", name, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path / name


def _scaling() -> TemplateSpec:
    spec = find_bundled_template("k8s-scaling")
    assert spec is not None
    return spec


def _attach(repo: Path, *, allow_unresolved: bool = False, **supplied: str) -> Any:
    manifest = read_manifest(repo)
    assert manifest is not None
    spec = _scaling()
    variables = {"name": default_name(manifest, repo), **spec.resolve_variables(supplied)}
    return attach_template(
        repo, manifest, spec, variables, bundled_version, allow_unresolved=allow_unresolved
    )


def _snapshot(repo: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }


def _add_unknown_template(repo: Path, files: dict[str, str]) -> None:
    """Append an entry for a template this build does not ship, as a newer ANSARI would."""
    manifest = read_manifest(repo)
    assert manifest is not None
    entries = [r.to_dict() for r in manifest.templates]
    entries.append(
        {
            "template": "from-the-future",
            "version": "9.0.0",
            "rendered_at": "2026-01-01T00:00:00+00:00",
            "variables": {},
            "files": files,
        }
    )
    manifest_path(repo).write_text(yaml.safe_dump({"schema": 2, "templates": entries}))


def _downgrade_to_v1(repo: Path) -> None:
    manifest = read_manifest(repo)
    assert manifest is not None
    record = manifest.templates[0]
    manifest_path(repo).write_text(
        yaml.safe_dump(
            {
                "template": record.template,
                "version": record.version,
                "rendered_at": record.rendered_at.isoformat(),
                "variables": record.variables,
                "files": record.files,
            },
            sort_keys=False,
        )
    )


# --------------------------------------------------------------------------
# A successful attach
# --------------------------------------------------------------------------


def test_attach_records_a_second_template(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    _, written = _attach(repo)

    assert set(written) == {SCALING, HPA, PDB}
    reloaded = read_manifest(repo)
    assert reloaded is not None
    assert reloaded.schema == SCHEMA_VERSION
    assert [r.template for r in reloaded.templates] == ["python-service", "k8s-scaling"]
    assert check_repo_drift(repo, reloaded, bundled_version).clean


def test_attached_variables_are_typed_and_rendered(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    _attach(repo, max_replicas="12")

    manifest = read_manifest(repo)
    assert manifest is not None
    assert manifest.templates[1].variables == {
        "name": "payment-api",
        "min_replicas": 2,
        "max_replicas": 12,
        "target_cpu_utilization": 70,
    }
    assert "maxReplicas: 12\n" in (repo / SCALING).read_text()


def test_attaching_onto_a_v1_repo_upgrades_it_and_keeps_the_original_entry(
    tmp_path: Path,
) -> None:
    """A repo scaffolded before schema 2 gains a template without losing provenance."""
    repo = _service(tmp_path)
    _downgrade_to_v1(repo)
    legacy = read_manifest(repo)
    assert legacy is not None
    assert legacy.schema == 1

    _attach(repo)

    reloaded = read_manifest(repo)
    assert reloaded is not None
    assert reloaded.schema == SCHEMA_VERSION
    assert reloaded.templates[0] == legacy.templates[0]


def test_default_name_is_the_name_the_repo_was_scaffolded_with(tmp_path: Path) -> None:
    repo = _service(tmp_path, "payment-api")
    renamed = repo.rename(tmp_path / "checked-out-elsewhere")
    manifest = read_manifest(renamed)
    assert manifest is not None
    # The recorded name, not the directory: it is what the chart path was built from.
    assert default_name(manifest, renamed) == "payment-api"


def test_default_name_falls_back_to_the_directory(tmp_path: Path) -> None:
    manifest = Manifest(
        schema=SCHEMA_VERSION,
        templates=[
            TemplateRecord(
                template="python-service",
                version="1.1.0",
                rendered_at=datetime(2026, 1, 1, tzinfo=UTC),
                variables={},
                files={},
            )
        ],
    )
    assert default_name(manifest, tmp_path / "orders") == "orders"


# --------------------------------------------------------------------------
# Refusals: each leaves the repo exactly as it was
# --------------------------------------------------------------------------


def test_attach_refuses_an_unresolved_entry_and_writes_nothing(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    _add_unknown_template(repo, {"future.tf": "sha256:x"})
    before = _snapshot(repo)

    with pytest.raises(UnresolvedTemplateError, match="from-the-future"):
        _attach(repo)
    assert _snapshot(repo) == before


def test_allow_unresolved_attaches_and_keeps_the_unknown_entry(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    _add_unknown_template(repo, {"future.tf": "sha256:x"})
    unknown = read_manifest(repo).templates[1]  # type: ignore[union-attr]

    _attach(repo, allow_unresolved=True)

    reloaded = read_manifest(repo)
    assert reloaded is not None
    assert [r.template for r in reloaded.templates] == [
        "python-service",
        "from-the-future",
        "k8s-scaling",
    ]
    # Passed through untouched, never "cleaned up".
    assert reloaded.templates[1] == unknown


def test_an_unresolved_templates_files_are_still_protected(tmp_path: Path) -> None:
    """Its descriptor is unknown, but the paths it owns are recorded and honoured."""
    repo = _service(tmp_path)
    _add_unknown_template(repo, {HPA: "sha256:x"})
    before = _snapshot(repo)

    with pytest.raises(AttachConflictError, match="owned by from-the-future"):
        _attach(repo, allow_unresolved=True)
    assert _snapshot(repo) == before


def test_attach_never_overwrites_an_untracked_file(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    (repo / HPA).write_text("# a hand-written autoscaler somebody already had\n")
    before = _snapshot(repo)

    with pytest.raises(AttachConflictError, match="not tracked by ANSARI"):
        _attach(repo)
    assert _snapshot(repo) == before


def test_attaching_the_same_template_twice_is_refused(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    _attach(repo)
    before = _snapshot(repo)

    with pytest.raises(AttachConflictError, match="owned by k8s-scaling"):
        _attach(repo)
    assert _snapshot(repo) == before


def test_no_template_may_write_into_the_manifest_directory(tmp_path: Path) -> None:
    root = tmp_path / "sneaky"
    root.mkdir()
    (root / "template.yaml").write_text(
        "name: sneaky\nversion: 1.0.0\nfiles:\n  m.j2: .ansari/manifest.yaml\n"
    )
    (root / "m.j2").write_text("schema: 2\n")
    spec = load_template(root)

    with pytest.raises(TemplateError, match="reserves"):
        generate(spec, {"name": "r"}, tmp_path / "repo")
    assert not (tmp_path / "repo").exists()


# --------------------------------------------------------------------------
# The contract between the two templates
# --------------------------------------------------------------------------


def test_python_service_checks_for_the_file_k8s_scaling_writes() -> None:
    """The one coupling between the templates, pinned so neither side can drift.

    python-service's Deployment omits `replicas` while a chart file exists; that
    file must be exactly the one k8s-scaling writes, relative to the chart root.
    """
    service = find_bundled_template("python-service")
    assert service is not None
    deployment = (service.root / "helm/templates/deployment.yaml.j2").read_text()

    dest = _scaling().files["autoscaling.yaml.j2"].dest
    chart_relative = dest.split("/", 2)[2]  # helm/<name>/<this>

    assert chart_relative == "autoscaling.yaml"
    assert f'.Files.Get "{chart_relative}"' in deployment


def test_k8s_scaling_is_attach_only() -> None:
    assert _scaling().standalone is False


def test_standalone_must_be_a_boolean(tmp_path: Path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    (root / "template.yaml").write_text(
        "name: t\nversion: 1.0.0\nstandalone: 'no'\nfiles:\n  a: a\n"
    )
    with pytest.raises(TemplateError, match="standalone"):
        load_template(root)


# --------------------------------------------------------------------------
# The rendered chart
# --------------------------------------------------------------------------

HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is not installed")


def _helm(*args: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    return subprocess.run([HELM, *args], capture_output=True, text=True, check=False)


def _rendered(repo: Path) -> dict[str, dict[str, Any]]:
    result = _helm("template", "release", str(repo / CHART))
    assert result.returncode == 0, result.stderr
    return {doc["kind"]: doc for doc in yaml.safe_load_all(result.stdout) if doc}


@needs_helm
def test_without_scaling_the_deployment_keeps_its_replicas(tmp_path: Path) -> None:
    docs = _rendered(_service(tmp_path))
    assert docs["Deployment"]["spec"]["replicas"] == 2
    assert "HorizontalPodAutoscaler" not in docs


@needs_helm
def test_with_scaling_the_autoscaler_owns_replicas(tmp_path: Path) -> None:
    """The production defect this milestone exists to avoid.

    Were `replicas` still set, every `helm upgrade` would reset the count the
    autoscaler had chosen.
    """
    repo = _service(tmp_path)
    _attach(repo, min_replicas="3", max_replicas="9", target_cpu_utilization="60")
    docs = _rendered(repo)

    assert "replicas" not in docs["Deployment"]["spec"]
    hpa = docs["HorizontalPodAutoscaler"]["spec"]
    assert hpa["scaleTargetRef"] == {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "name": "payment-api",
    }
    assert (hpa["minReplicas"], hpa["maxReplicas"]) == (3, 9)
    assert hpa["metrics"][0]["resource"]["target"]["averageUtilization"] == 60

    pdb = docs["PodDisruptionBudget"]["spec"]
    assert pdb["maxUnavailable"] == 1
    # The budget must select the same pods the Deployment runs.
    assert pdb["selector"]["matchLabels"] == docs["Deployment"]["spec"]["selector"]["matchLabels"]


@needs_helm
def test_the_chart_lints_with_scaling_attached(tmp_path: Path) -> None:
    repo = _service(tmp_path)
    _attach(repo)
    result = _helm("lint", str(repo / CHART))
    assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
@pytest.mark.parametrize(
    ("supplied", "message"),
    [
        ({"min_replicas": "5", "max_replicas": "3"}, "must not exceed maxReplicas"),
        ({"min_replicas": "0"}, "at least 1"),
    ],
)
def test_the_chart_refuses_to_render_impossible_bounds(
    tmp_path: Path, supplied: dict[str, str], message: str
) -> None:
    repo = _service(tmp_path)
    _attach(repo, **supplied)
    result = _helm("template", "release", str(repo / CHART))
    assert result.returncode != 0
    assert message in result.stderr
