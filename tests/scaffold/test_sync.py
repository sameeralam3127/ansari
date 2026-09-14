"""Sync: three-way upgrades, and every refusal that keeps them safe.

Most tests build a small template in two versions and a real git repository, so
the merge ancestor really is found in history. The last test upgrades an actual
python-service 1.0.0 repository to the current version.
"""

import shutil
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ansari.scaffold import (
    SCHEMA_VERSION,
    Manifest,
    SyncError,
    SyncPlan,
    TemplateRecord,
    TemplateSpec,
    UnresolvedTemplateError,
    VariableError,
    apply_sync,
    build_manifest,
    bundled_version,
    carry_variables,
    check_repo_drift,
    ensure_syncable,
    file_digest,
    find_bundled_template,
    generate,
    load_template,
    plan_sync,
    read_manifest,
    write_manifest,
)
from ansari.scaffold.sync import (
    ADD,
    CONFLICT,
    KEPT,
    LEFT_DELETED,
    MERGE,
    REMOVE,
    UNCHANGED,
    UPDATE,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

V1 = {
    "config.txt": "a\nb\nc\nd\ne\n",
    "notes.txt": "notes\n",
    "old.txt": "legacy\n",
    "keep.txt": "keep\n",
}
V2 = {
    "config.txt": "a\nb\nc\nd\nE from v2\n",
    "notes.txt": "notes\n",
    "keep.txt": "keep v2\n",
    "new.txt": "new in v2\n",
}


def _template(
    root: Path, version: str, files: dict[str, str], *, name: str = "kit", extra: str = ""
) -> TemplateSpec:
    root.mkdir(parents=True, exist_ok=True)
    listing = "".join(f"  {file}.j2: {file}\n" for file in files)
    (root / "template.yaml").write_text(
        f"name: {name}\nversion: {version}\n{extra}files:\n{listing}"
    )
    for file, body in files.items():
        (root / f"{file}.j2").write_text(body)
    return load_template(root)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


def _init_git(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")


def _scaffolded(tmp_path: Path, *, commit: bool = True) -> Path:
    spec = _template(tmp_path / "kit-1.0.0", "1.0.0", V1)
    repo = tmp_path / "repo"
    written = generate(spec, {"name": "repo"}, repo)
    write_manifest(repo, build_manifest(spec.name, spec.version, {"name": "repo"}, repo, written))
    _init_git(repo)
    if commit:
        _commit(repo, "scaffold")
    return repo


def _finder(tmp_path: Path, files: dict[str, str] = V2, *, extra: str = "") -> object:
    spec = _template(tmp_path / "kit-2.0.0", "2.0.0", files, extra=extra)
    return {"kit": spec}.get


def _plan(repo: Path, finder: object) -> SyncPlan:
    manifest = read_manifest(repo)
    assert manifest is not None
    return plan_sync(repo, manifest, finder)  # type: ignore[arg-type]


def _kinds(plan: SyncPlan) -> dict[str, str]:
    (template_plan,) = plan.templates
    return {action.path: action.kind for action in template_plan.actions}


def _snapshot(repo: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(repo)): p.read_bytes()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


# --------------------------------------------------------------------------
# What happens to each file
# --------------------------------------------------------------------------


def test_untouched_files_are_replaced_and_the_version_moves(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    plan = _plan(repo, _finder(tmp_path))

    assert _kinds(plan) == {
        "config.txt": UPDATE,
        "keep.txt": UPDATE,
        "new.txt": ADD,
        "notes.txt": UNCHANGED,
        "old.txt": REMOVE,
    }
    assert plan.clean

    apply_sync(plan)

    assert (repo / "keep.txt").read_text() == "keep v2\n"
    assert (repo / "new.txt").read_text() == "new in v2\n"
    assert not (repo / "old.txt").exists()
    manifest = read_manifest(repo)
    assert manifest is not None
    record = manifest.templates[0]
    assert record.version == "2.0.0"
    assert set(record.files) == set(V2)
    assert check_repo_drift(repo, manifest, lambda _: "2.0.0").clean


def test_an_edited_file_is_merged_keeping_both_changes(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "config.txt").write_text("a\nb edited here\nc\nd\ne\n")
    _commit(repo, "local edit")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["config.txt"] == MERGE
    apply_sync(plan)

    assert (repo / "config.txt").read_text() == "a\nb edited here\nc\nd\nE from v2\n"
    manifest = read_manifest(repo)
    assert manifest is not None
    report = check_repo_drift(repo, manifest, lambda _: "2.0.0")
    # Upgraded, and the local edit is still reported as a local edit.
    assert not report.behind
    assert report.modified == ["config.txt"]


def test_overlapping_edits_get_conflict_markers(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "config.txt").write_text("a\nb\nc\nd\ne edited here\n")
    _commit(repo, "local edit")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["config.txt"] == CONFLICT
    assert plan.conflicts == ["config.txt"]
    assert not plan.clean

    apply_sync(plan)
    merged = (repo / "config.txt").read_text()
    assert "<<<<<<< local" in merged
    assert "e edited here" in merged
    assert "E from v2" in merged
    assert ">>>>>>> kit 2.0.0" in merged


def test_the_ancestor_is_found_behind_later_commits(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "config.txt").write_text("a\nb edited once\nc\nd\ne\n")
    _commit(repo, "first edit")
    (repo / "config.txt").write_text("a edited twice\nb edited once\nc\nd\ne\n")
    _commit(repo, "second edit")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["config.txt"] == MERGE


def test_a_deleted_file_stays_deleted(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "keep.txt").unlink()
    _commit(repo, "we don't want keep.txt")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["keep.txt"] == LEFT_DELETED
    apply_sync(plan)

    assert not (repo / "keep.txt").exists()
    manifest = read_manifest(repo)
    assert manifest is not None
    # Still tracked, so `check` keeps reporting the deletion honestly.
    assert "keep.txt" in manifest.templates[0].files
    assert check_repo_drift(repo, manifest, lambda _: "2.0.0").deleted == ["keep.txt"]


def test_a_dropped_file_is_removed_only_if_untouched(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "old.txt").write_text("legacy, but ours now\n")
    _commit(repo, "edit a file v2 drops")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["old.txt"] == KEPT
    apply_sync(plan)

    assert (repo / "old.txt").read_text() == "legacy, but ours now\n"
    manifest = read_manifest(repo)
    assert manifest is not None
    assert "old.txt" not in manifest.templates[0].files


def test_an_edit_that_already_matches_the_new_output_needs_no_merge(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "keep.txt").write_text("keep v2\n")
    _commit(repo, "got there first")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["keep.txt"] == UNCHANGED
    apply_sync(plan)
    manifest = read_manifest(repo)
    assert manifest is not None
    assert "keep.txt" not in check_repo_drift(repo, manifest, lambda _: "2.0.0").modified


def test_an_edit_to_a_file_the_template_did_not_change_is_left_alone(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "notes.txt").write_text("our notes\n")
    _commit(repo, "edit notes")

    plan = _plan(repo, _finder(tmp_path))
    assert _kinds(plan)["notes.txt"] == UNCHANGED
    apply_sync(plan)
    assert (repo / "notes.txt").read_text() == "our notes\n"


def test_modes_are_applied_to_updated_files(tmp_path: Path) -> None:
    extra_v1 = ""
    root = tmp_path / "kit-1.0.0"
    root.mkdir()
    (root / "template.yaml").write_text(
        f"name: kit\nversion: 1.0.0\n{extra_v1}files:\n"
        "  run.sh.j2:\n    dest: run.sh\n    mode: '0755'\n"
    )
    (root / "run.sh.j2").write_text("#!/bin/sh\necho v1\n")
    repo = tmp_path / "repo"
    spec = load_template(root)
    written = generate(spec, {"name": "repo"}, repo)
    write_manifest(repo, build_manifest("kit", "1.0.0", {"name": "repo"}, repo, written))
    _init_git(repo)
    _commit(repo, "scaffold")

    root2 = tmp_path / "kit-2.0.0"
    shutil.copytree(root, root2)
    (root2 / "template.yaml").write_text(
        (root / "template.yaml").read_text().replace("1.0.0", "2.0.0")
    )
    (root2 / "run.sh.j2").write_text("#!/bin/sh\necho v2\n")

    plan = _plan(repo, {"kit": load_template(root2)}.get)
    assert _kinds(plan) == {"run.sh": UPDATE}
    apply_sync(plan)
    assert stat.S_IMODE((repo / "run.sh").stat().st_mode) == 0o755


# --------------------------------------------------------------------------
# Refusals: nothing written for the template
# --------------------------------------------------------------------------


def test_an_edit_with_no_ancestor_in_history_refuses_the_template(tmp_path: Path) -> None:
    """Edited before the first commit, so what 1.0.0 generated was never recorded."""
    repo = _scaffolded(tmp_path, commit=False)
    (repo / "config.txt").write_text("a\nb edited before committing\nc\nd\ne\n")
    _commit(repo, "scaffold, already edited")

    plan = _plan(repo, _finder(tmp_path))
    (template_plan,) = plan.templates
    assert template_plan.refused is not None
    assert "git history" in template_plan.refused

    before = _snapshot(repo)
    apply_sync(plan)
    assert _snapshot(repo) == before


def test_an_untracked_file_in_the_way_of_a_new_one_refuses(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "new.txt").write_text("somebody's own file\n")
    _commit(repo, "add our own new.txt")

    plan = _plan(repo, _finder(tmp_path))
    assert "not tracked by ANSARI" in (plan.templates[0].refused or "")

    before = _snapshot(repo)
    apply_sync(plan)
    assert _snapshot(repo) == before


def test_a_destination_another_template_owns_refuses(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "new.txt").write_text("other\n")
    manifest = read_manifest(repo)
    assert manifest is not None
    other = TemplateRecord(
        template="other",
        version="1.0.0",
        rendered_at=datetime(2026, 1, 1, tzinfo=UTC),
        variables={"name": "repo"},
        files={"new.txt": file_digest(repo / "new.txt")},
    )
    write_manifest(repo, Manifest(schema=SCHEMA_VERSION, templates=[*manifest.templates, other]))
    _commit(repo, "attach other")

    kit = _template(tmp_path / "kit-2.0.0", "2.0.0", V2)
    other_spec = _template(tmp_path / "other", "1.0.0", {"new.txt": "other\n"}, name="other")
    plan = _plan(repo, {"kit": kit, "other": other_spec}.get)

    (template_plan,) = plan.templates
    assert template_plan.refused is not None
    assert "other owns" in template_plan.refused


def test_a_new_required_variable_refuses_the_template(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    finder = _finder(tmp_path, extra="variables:\n  region:\n    type: string\n")
    plan = _plan(repo, finder)
    assert "region" in (plan.templates[0].refused or "")


def test_an_edited_binary_file_refuses_the_template(tmp_path: Path) -> None:
    def binary_template(root: Path, version: str, body: bytes) -> TemplateSpec:
        root.mkdir(parents=True)
        (root / "template.yaml").write_text(
            f"name: kit\nversion: {version}\nfiles:\n"
            "  blob.bin:\n    dest: blob.bin\n    render: copy\n"
        )
        (root / "blob.bin").write_bytes(body)
        return load_template(root)

    v1 = binary_template(tmp_path / "v1", "1.0.0", b"\x00\x01v1")
    repo = tmp_path / "repo"
    written = generate(v1, {"name": "repo"}, repo)
    write_manifest(repo, build_manifest("kit", "1.0.0", {"name": "repo"}, repo, written))
    _init_git(repo)
    _commit(repo, "scaffold")
    (repo / "blob.bin").write_bytes(b"\x00\x01ours")
    _commit(repo, "edit blob")

    v2 = binary_template(tmp_path / "v2", "2.0.0", b"\x00\x01v2")
    plan = _plan(repo, {"kit": v2}.get)
    assert "isn't text" in (plan.templates[0].refused or "")


# --------------------------------------------------------------------------
# Variables, preconditions, and the whole-sync refusals
# --------------------------------------------------------------------------


def _record(variables: dict[str, object]) -> TemplateRecord:
    return TemplateRecord(
        template="kit",
        version="1.0.0",
        rendered_at=datetime(2026, 1, 1, tzinfo=UTC),
        variables=variables,  # type: ignore[arg-type]
        files={},
    )


def test_variables_are_carried_typed_and_new_defaults_fill_in(tmp_path: Path) -> None:
    spec = _template(
        tmp_path / "kit",
        "2.0.0",
        {"a.txt": "a\n"},
        extra="variables:\n  replicas:\n    type: int\n    default: 1\n  tier: gold\n",
    )
    # A schema-1 manifest recorded "3" as a string; `legacy` isn't declared any more.
    carried = carry_variables(spec, _record({"name": "repo", "replicas": "3", "legacy": "x"}))
    assert carried == {"name": "repo", "replicas": 3, "tier": "gold"}


def test_a_carried_value_the_new_version_forbids_is_rejected(tmp_path: Path) -> None:
    spec = _template(
        tmp_path / "kit",
        "2.0.0",
        {"a.txt": "a\n"},
        extra="variables:\n  database:\n    choices: [postgres]\n    default: postgres\n",
    )
    with pytest.raises(VariableError, match="must be one of"):
        carry_variables(spec, _record({"name": "repo", "database": "mysql"}))


def test_a_manifest_with_no_name_cannot_be_carried(tmp_path: Path) -> None:
    spec = _template(tmp_path / "kit", "2.0.0", {"a.txt": "a\n"})
    with pytest.raises(VariableError, match="name"):
        carry_variables(spec, _record({}))


def test_a_current_template_is_not_planned(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    same = _template(tmp_path / "kit-again", "1.0.0", V1)
    assert _plan(repo, {"kit": same}.get).up_to_date


def test_an_unresolved_template_refuses_the_whole_sync(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    with pytest.raises(UnresolvedTemplateError):
        _plan(repo, {}.get)


def test_sync_needs_a_git_working_tree(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    with pytest.raises(SyncError, match="git"):
        ensure_syncable(tmp_path / "plain")


def test_sync_needs_a_clean_tree_unless_allowed(tmp_path: Path) -> None:
    repo = _scaffolded(tmp_path)
    (repo / "notes.txt").write_text("uncommitted\n")
    with pytest.raises(SyncError, match="uncommitted"):
        ensure_syncable(repo)
    ensure_syncable(repo, allow_dirty=True)  # does not raise


# --------------------------------------------------------------------------
# The real upgrade: python-service 1.0.0 -> current
# --------------------------------------------------------------------------


def test_a_python_service_1_0_0_repo_upgrades_to_the_current_version(tmp_path: Path) -> None:
    """v0.8's acceptance test: the upgrade every repo on 1.0.0 is waiting for."""
    current = find_bundled_template("python-service")
    assert current is not None
    old_root = tmp_path / "python-service-1.0.0"
    shutil.copytree(current.root, old_root)
    shutil.copytree(FIXTURES / "python-service-1.0.0", old_root, dirs_exist_ok=True)
    old = load_template(old_root)
    assert old.version == "1.0.0"

    golden = yaml.safe_load((FIXTURES / "golden" / "python-service.yaml").read_text())["1.0.0"]
    variables = dict(golden["variables"])
    repo = tmp_path / str(variables["name"])
    written = generate(old, variables, repo)
    # The reconstructed 1.0.0 is byte for byte the real one.
    assert {path: file_digest(repo / path) for path in written} == golden["files"]
    write_manifest(repo, build_manifest(old.name, old.version, variables, repo, written))
    _init_git(repo)
    _commit(repo, "scaffold on python-service 1.0.0")

    values = repo / "helm/legacy-svc/values.yaml"
    values.write_text(values.read_text().replace("memory: 256Mi", "memory: 512Mi"))
    _commit(repo, "more memory")

    manifest = read_manifest(repo)
    assert manifest is not None
    plan = plan_sync(repo, manifest, find_bundled_template)
    kinds = _kinds(plan)
    assert kinds["helm/legacy-svc/templates/deployment.yaml"] == UPDATE
    assert kinds["helm/legacy-svc/values.yaml"] == MERGE
    assert plan.clean

    apply_sync(plan)

    deployment = (repo / "helm/legacy-svc/templates/deployment.yaml").read_text()
    assert '.Files.Get "autoscaling.yaml"' in deployment
    merged_values = values.read_text()
    assert "memory: 512Mi" in merged_values
    assert "Ignored once k8s-scaling is attached" in merged_values

    upgraded = read_manifest(repo)
    assert upgraded is not None
    report = check_repo_drift(repo, upgraded, bundled_version)
    assert not report.behind
    assert report.modified == ["helm/legacy-svc/values.yaml"]
