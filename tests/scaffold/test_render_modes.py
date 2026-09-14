"""Render modes: alternate delimiters, verbatim copy, file modes, conditional files.

The pipeline these change writes every file ANSARI generates, so the first test
here is a regression guard rather than a feature test: python-service's output
must stay byte-identical to what it was before render modes existed.
"""

import stat
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ansari.cli.main import app
from ansari.scaffold import (
    TemplateError,
    file_digest,
    find_bundled_template,
    generate,
    load_template,
    read_manifest,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "manifest_v1_python_service.yaml"
GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "python-service.yaml"
runner = CliRunner()


def _template(root: Path, descriptor: str, sources: dict[str, str | bytes]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "template.yaml").write_text(descriptor)
    for name, body in sources.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            target.write_bytes(body)
        else:
            target.write_text(body)
    return root


ROLE_LIKE = """\
name: role-like
version: 0.1.0
render:
  delimiters: alternate
variables:
  with_molecule:
    type: bool
    default: false
files:
  tasks/main.yml.j2: roles/[[ name ]]/tasks/main.yml
  files/preflight.sh:
    dest: roles/[[ name ]]/files/preflight.sh
    render: copy
    mode: "0755"
  molecule/molecule.yml.j2:
    dest: roles/[[ name ]]/molecule/default/molecule.yml
    when: with_molecule
"""

TASKS = """\
# role: [[ name ]]
[# an ANSARI-side comment, stripped at scaffold time #]
- name: Report the distribution
  ansible.builtin.debug:
    msg: "{{ ansible_facts['distribution'] }}"
{% if inventory_hostname is defined %}
{# an Ansible-side comment, kept #}
{% endif %}
"""

# Braces, alternate markers, and non-UTF-8 bytes: a copied file must survive all three.
PREFLIGHT = b"#!/bin/sh\necho '{{ not rendered }}' [[ name ]]\n\xff\x00\n"

SOURCES: dict[str, str | bytes] = {
    "tasks/main.yml.j2": TASKS,
    "files/preflight.sh": PREFLIGHT,
    "molecule/molecule.yml.j2": "role: [[ name ]]\n",
}


def _role_like(tmp_path: Path, **supplied: str) -> tuple[Path, list[str]]:
    spec = load_template(_template(tmp_path / "role-like", ROLE_LIKE, SOURCES))
    variables = {"name": "vitals", **spec.resolve_variables(supplied)}
    repo = tmp_path / "out"
    return repo, generate(spec, variables, repo)


# --------------------------------------------------------------------------
# Regression guard
# --------------------------------------------------------------------------


def test_python_service_output_matches_the_golden_for_its_version(tmp_path: Path) -> None:
    """Every generated file hashes exactly as recorded for the current version.

    Within a version, any byte of difference fails: template output changed
    without a version bump, which would make every existing repo report drift it
    never had. A version with no recorded entry fails too, so bumping the template
    means recording what the new version produces -- the guard can't be switched
    off by a bump.
    """
    spec = find_bundled_template("python-service")
    assert spec is not None
    goldens = yaml.safe_load(GOLDEN.read_text())
    missing = f"python-service {spec.version} has no golden output recorded in {GOLDEN.name}"
    assert spec.version in goldens, missing
    golden = goldens[spec.version]

    repo = tmp_path / str(golden["variables"]["name"])
    written = generate(spec, dict(golden["variables"]), repo)

    assert sorted(written) == sorted(golden["files"])
    for path, digest in golden["files"].items():
        assert file_digest(repo / path) == digest, f"{path} changed without a version bump"


def test_the_first_golden_is_the_real_pre_migration_output() -> None:
    """The oldest entry is anchored to captured bytes, not typed in by hand."""
    goldens = yaml.safe_load(GOLDEN.read_text())
    fixture = yaml.safe_load(FIXTURE.read_text())
    assert goldens[fixture["version"]]["files"] == fixture["files"]


# --------------------------------------------------------------------------
# Alternate delimiters
# --------------------------------------------------------------------------


def test_jinja_native_output_survives_rendering(tmp_path: Path) -> None:
    """M3's acceptance criterion: `{{ ansible_facts }}` is not eaten.

    ANSARI's `[[ ]]` and `[# #]` are processed; Ansible's `{{ }}`, `{% %}` and
    `{# #}` come out exactly as written, with no escaping in the source.
    """
    repo, _ = _role_like(tmp_path)
    rendered = (repo / "roles/vitals/tasks/main.yml").read_text()

    expected = TASKS.replace("[[ name ]]", "vitals").replace(
        "[# an ANSARI-side comment, stripped at scaffold time #]", ""
    )
    assert rendered == expected
    assert "{{ ansible_facts['distribution'] }}" in rendered
    assert "{# an Ansible-side comment, kept #}" in rendered


def test_alternate_delimiters_apply_to_destination_paths(tmp_path: Path) -> None:
    _, written = _role_like(tmp_path)
    assert "roles/vitals/tasks/main.yml" in written


# --------------------------------------------------------------------------
# Copy and mode
# --------------------------------------------------------------------------


def test_copy_mode_writes_bytes_untouched(tmp_path: Path) -> None:
    repo, _ = _role_like(tmp_path)
    assert (repo / "roles/vitals/files/preflight.sh").read_bytes() == PREFLIGHT


def test_mode_makes_a_generated_file_executable(tmp_path: Path) -> None:
    """M3's second acceptance criterion."""
    repo, _ = _role_like(tmp_path)
    mode = stat.S_IMODE((repo / "roles/vitals/files/preflight.sh").stat().st_mode)
    assert mode == 0o755


# --------------------------------------------------------------------------
# Conditional files
# --------------------------------------------------------------------------


def test_a_gated_file_is_omitted_by_default(tmp_path: Path) -> None:
    repo, written = _role_like(tmp_path)
    assert not (repo / "roles/vitals/molecule").exists()
    # Not generated means not tracked: the manifest must never claim a file
    # that was never written.
    assert all("molecule" not in path for path in written)


def test_a_gated_file_is_generated_when_asked_for(tmp_path: Path) -> None:
    repo, written = _role_like(tmp_path, with_molecule="true")
    assert (repo / "roles/vitals/molecule/default/molecule.yml").read_text() == "role: vitals\n"
    assert "roles/vitals/molecule/default/molecule.yml" in written


# --------------------------------------------------------------------------
# Descriptor validation
# --------------------------------------------------------------------------


def _descriptor_error(tmp_path: Path, descriptor: str) -> str:
    with pytest.raises(TemplateError) as exc:
        load_template(_template(tmp_path / "bad", descriptor, {}))
    return str(exc.value)


def test_an_unquoted_mode_is_rejected(tmp_path: Path) -> None:
    """YAML reads an unquoted 0755 as 493, so it cannot mean what it looks like."""
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nfiles:\n  a:\n    dest: a\n    mode: 0755\n"
    )
    assert "quoted octal" in message


def test_a_non_octal_mode_is_rejected(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nfiles:\n  a:\n    dest: a\n    mode: 'rwx'\n"
    )
    assert "quoted octal" in message


def test_an_unknown_render_mode_is_rejected(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nfiles:\n  a:\n    dest: a\n    render: template\n"
    )
    assert "unknown render mode" in message


def test_unknown_delimiters_are_rejected(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nrender:\n  delimiters: angle\nfiles:\n  a: a\n"
    )
    assert "unknown delimiters" in message


def test_an_unknown_render_key_is_rejected(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nrender:\n  delimeters: alternate\nfiles:\n  a: a\n"
    )
    assert "unknown key" in message


def test_a_non_mapping_render_block_is_rejected(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nrender: alternate\nfiles:\n  a: a\n"
    )
    assert "'render' is not a mapping" in message


def test_when_must_name_a_declared_variable(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nfiles:\n  a:\n    dest: a\n    when: with_tests\n"
    )
    assert "not a declared bool variable" in message


def test_when_must_name_a_bool_variable(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path,
        "name: t\nversion: 1.0.0\nvariables:\n  flavour: vanilla\n"
        "files:\n  a:\n    dest: a\n    when: flavour\n",
    )
    assert "not a declared bool variable" in message


def test_when_must_be_a_string(tmp_path: Path) -> None:
    message = _descriptor_error(
        tmp_path, "name: t\nversion: 1.0.0\nfiles:\n  a:\n    dest: a\n    when: true\n"
    )
    assert "non-string 'when'" in message


# --------------------------------------------------------------------------
# Refusals before anything is written
# --------------------------------------------------------------------------


def test_a_destination_outside_the_repo_is_refused(tmp_path: Path) -> None:
    """A `--var` value can reach a destination path, so containment is checked."""
    spec = load_template(
        _template(
            tmp_path / "t",
            "name: t\nversion: 1.0.0\nvariables:\n  dir: x\nfiles:\n  a.j2: '{{ dir }}/a'\n",
            {"a.j2": "a\n"},
        )
    )
    repo = tmp_path / "repo"
    with pytest.raises(TemplateError, match="outside the repo"):
        generate(spec, {"name": "r", "dir": "../../escaped"}, repo)
    assert not repo.exists()
    assert not (tmp_path / "escaped").exists()


def test_two_sources_writing_one_file_are_refused(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path / "t",
            "name: t\nversion: 1.0.0\nfiles:\n  a.j2: same.txt\n  b.j2: same.txt\n",
            {"a.j2": "a\n", "b.j2": "b\n"},
        )
    )
    with pytest.raises(TemplateError, match="both write"):
        generate(spec, {"name": "r"}, tmp_path / "repo")


def test_a_missing_source_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path / "t",
            "name: t\nversion: 1.0.0\nfiles:\n  present.j2: present.txt\n  missing.j2: m.txt\n",
            {"present.j2": "here\n"},
        )
    )
    repo = tmp_path / "repo"
    with pytest.raises(TemplateError, match="no source file 'missing.j2'"):
        generate(spec, {"name": "r"}, repo)
    # Refused during planning, so even the file that could have been written wasn't.
    assert not repo.exists()


# --------------------------------------------------------------------------
# End to end through the CLI
# --------------------------------------------------------------------------


def test_render_modes_scaffold_and_check_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copied, chmod-ed and conditional files are tracked and verify as clean."""
    bundled = tmp_path / "templates"
    _template(bundled / "role-like", ROLE_LIKE, SOURCES)
    monkeypatch.setattr("ansari.scaffold.template.BUNDLED_DIR", bundled)

    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "new",
            "vitals",
            "--type",
            "role-like",
            "--var",
            "with_molecule=true",
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output

    repo = out / "vitals"
    manifest = read_manifest(repo)
    assert manifest is not None
    assert set(manifest.templates[0].files) == {
        "roles/vitals/tasks/main.yml",
        "roles/vitals/files/preflight.sh",
        "roles/vitals/molecule/default/molecule.yml",
    }

    check = runner.invoke(app, ["check", str(repo)])
    assert check.exit_code == 0, check.output


def test_the_cli_reports_a_refused_destination_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "templates"
    _template(
        bundled / "leaky",
        "name: leaky\nversion: 1.0.0\nvariables:\n  dir: x\nfiles:\n  a.j2: '{{ dir }}/a'\n",
        {"a.j2": "a\n"},
    )
    monkeypatch.setattr("ansari.scaffold.template.BUNDLED_DIR", bundled)

    result = runner.invoke(
        app,
        ["new", "r", "--type", "leaky", "--var", "dir=../../x", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "outside the repo" in result.output
