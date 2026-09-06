"""The template descriptor: declared variables, and the two `files` forms.

Templates declare what they accept so that adding a template type never means
editing the CLI. That property is the whole point of this layer, so it is
asserted directly in `test_cli_needs_no_edit_to_gain_a_template_type`.
"""

from pathlib import Path

import pytest

from ansari.scaffold import (
    FileSpec,
    TemplateError,
    VariableError,
    VariableSpec,
    available_templates,
    find_bundled_template,
    load_template,
)
from ansari.scaffold.template import NAME_VARIABLE


def _template(tmp_path: Path, descriptor: str, sources: dict[str, str] | None = None) -> Path:
    root = tmp_path / "a-template"
    root.mkdir(parents=True, exist_ok=True)
    (root / "template.yaml").write_text(descriptor)
    for name, body in (sources or {}).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return root


BASIC = """\
name: a-template
version: 1.0.0
description: A template used by the tests.
files:
  body.j2: out.txt
"""


# --------------------------------------------------------------------------
# The `files` mapping, in both forms
# --------------------------------------------------------------------------


def test_short_form_files_still_load(tmp_path: Path) -> None:
    """`source: dest` is what every existing descriptor uses. It must keep working."""
    spec = load_template(_template(tmp_path, BASIC))
    assert spec.files == {"body.j2": FileSpec(source="body.j2", dest="out.txt")}


def test_mapping_form_files_load(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path,
            "name: a-template\nversion: 1.0.0\nfiles:\n  body.j2:\n    dest: out.txt\n",
        )
    )
    assert spec.files["body.j2"].dest == "out.txt"


def test_both_files_forms_can_coexist(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path,
            "name: a-template\nversion: 1.0.0\nfiles:\n  a.j2: a.txt\n  b.j2:\n    dest: b.txt\n",
        )
    )
    assert {source: file.dest for source, file in spec.files.items()} == {
        "a.j2": "a.txt",
        "b.j2": "b.txt",
    }


def test_mapping_form_requires_a_dest(tmp_path: Path) -> None:
    root = _template(
        tmp_path, "name: a-template\nversion: 1.0.0\nfiles:\n  body.j2:\n    mode: '0755'\n"
    )
    with pytest.raises(TemplateError, match="dest"):
        load_template(root)


def test_destinations_render_with_variables(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path,
            "name: a-template\nversion: 1.0.0\nfiles:\n  body.j2: roles/{{ name }}/main.yml\n",
        )
    )
    assert spec.destinations({"name": "vitals"}) == {"body.j2": "roles/vitals/main.yml"}


# --------------------------------------------------------------------------
# Declared variables
# --------------------------------------------------------------------------


DECLARED = """\
name: a-template
version: 1.0.0
variables:
  database:
    type: string
    default: postgres
    choices: [postgres, none]
  replicas:
    type: int
    default: 2
  public:
    type: bool
    default: false
  providers:
    type: list
    default: [aws]
files:
  body.j2: out.txt
"""


def test_declared_variables_are_parsed(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    assert set(spec.variables) == {"database", "replicas", "public", "providers"}
    assert spec.variables["database"].choices == ["postgres", "none"]
    assert spec.variables["replicas"].type == "int"


def test_defaults_apply_when_nothing_is_supplied(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    assert spec.resolve_variables({}) == {
        "database": "postgres",
        "replicas": 2,
        "public": False,
        "providers": ["aws"],
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("3", 3), ("0", 0)],
)
def test_int_variables_are_coerced(tmp_path: Path, raw: str, expected: int) -> None:
    """Values arrive from the command line as text; the declaration types them."""
    spec = load_template(_template(tmp_path, DECLARED))
    assert spec.resolve_variables({"replicas": raw})["replicas"] == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("yes", True), ("1", True), ("false", False), ("no", False), ("0", False)],
)
def test_bool_variables_are_coerced(tmp_path: Path, raw: str, expected: bool) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    assert spec.resolve_variables({"public": raw})["public"] is expected


def test_list_variables_are_split_on_commas(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    assert spec.resolve_variables({"providers": "aws, random"})["providers"] == ["aws", "random"]


def test_a_non_integer_is_rejected(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    with pytest.raises(VariableError, match="integer"):
        spec.resolve_variables({"replicas": "many"})


def test_a_non_boolean_is_rejected(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    with pytest.raises(VariableError, match="true or false"):
        spec.resolve_variables({"public": "maybe"})


def test_a_value_outside_choices_is_rejected(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, DECLARED))
    with pytest.raises(VariableError, match="must be one of"):
        spec.resolve_variables({"database": "mysql"})


def test_an_unknown_variable_is_rejected(tmp_path: Path) -> None:
    """A typo must not silently scaffold the default.

    `--var databse=none` that quietly produced a postgres service would be
    discovered much later, in a repo nobody re-reads.
    """
    spec = load_template(_template(tmp_path, DECLARED))
    with pytest.raises(VariableError, match="databse"):
        spec.resolve_variables({"databse": "none"})


def test_a_variable_with_no_default_is_required(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path,
            "name: a-template\nversion: 1.0.0\nvariables:\n  region:\n    type: string\n"
            "files:\n  body.j2: out.txt\n",
        )
    )
    assert spec.variables["region"].required
    with pytest.raises(VariableError, match="requires --var region"):
        spec.resolve_variables({})
    assert spec.resolve_variables({"region": "eu-west-1"})["region"] == "eu-west-1"


def test_a_scalar_declaration_is_shorthand_for_a_default(tmp_path: Path) -> None:
    spec = load_template(
        _template(
            tmp_path,
            "name: a-template\nversion: 1.0.0\nvariables:\n  flavour: vanilla\n"
            "files:\n  body.j2: out.txt\n",
        )
    )
    assert spec.variables["flavour"] == VariableSpec(name="flavour", default="vanilla")


def test_the_name_variable_cannot_be_declared(tmp_path: Path) -> None:
    """A template that could rename its own output would break its destinations."""
    root = _template(
        tmp_path,
        f"name: a-template\nversion: 1.0.0\nvariables:\n  {NAME_VARIABLE}: x\n"
        "files:\n  body.j2: out.txt\n",
    )
    with pytest.raises(TemplateError, match=NAME_VARIABLE):
        load_template(root)


def test_the_name_variable_is_always_accepted(tmp_path: Path) -> None:
    spec = load_template(_template(tmp_path, BASIC))
    spec.resolve_variables({NAME_VARIABLE: "anything"})  # does not raise


def test_an_unknown_variable_type_is_rejected(tmp_path: Path) -> None:
    root = _template(
        tmp_path,
        "name: a-template\nversion: 1.0.0\nvariables:\n  x:\n    type: complex\n"
        "files:\n  body.j2: out.txt\n",
    )
    with pytest.raises(TemplateError, match="unknown type"):
        load_template(root)


def test_a_default_outside_its_own_choices_is_rejected(tmp_path: Path) -> None:
    """Caught at load time, not at the first scaffold that happens to hit it."""
    root = _template(
        tmp_path,
        "name: a-template\nversion: 1.0.0\nvariables:\n  x:\n    default: c\n    choices: [a, b]\n"
        "files:\n  body.j2: out.txt\n",
    )
    with pytest.raises(TemplateError, match="not among its 'choices'"):
        load_template(root)


def test_non_mapping_variables_are_rejected(tmp_path: Path) -> None:
    root = _template(
        tmp_path, "name: a-template\nversion: 1.0.0\nvariables: [a]\nfiles:\n  body.j2: out.txt\n"
    )
    with pytest.raises(TemplateError, match="variables"):
        load_template(root)


def test_non_list_choices_are_rejected(tmp_path: Path) -> None:
    root = _template(
        tmp_path,
        "name: a-template\nversion: 1.0.0\nvariables:\n  x:\n    choices: nope\n"
        "files:\n  body.j2: out.txt\n",
    )
    with pytest.raises(TemplateError, match="choices"):
        load_template(root)


# --------------------------------------------------------------------------
# The bundled descriptor, and the property this milestone exists for
# --------------------------------------------------------------------------


def test_python_service_declares_its_own_variables() -> None:
    """The options that used to be hardcoded in `cli/main.py`."""
    spec = find_bundled_template("python-service")
    assert spec is not None
    assert spec.variables["database"].choices == ["postgres", "none"]
    assert spec.variables["language"].default == "python"
    assert spec.resolve_variables({}) == {"language": "python", "database": "postgres"}


def test_available_templates_reads_the_bundled_directory() -> None:
    assert "python-service" in available_templates()
