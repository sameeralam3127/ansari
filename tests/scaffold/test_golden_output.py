"""Every bundled template's output is pinned, per version.

A template whose output changes without a version bump makes every repo
scaffolded from it report drift it never had. So each template records the hashes
its current version generates, in tests/fixtures/golden/<template>.yaml, and a
version with no entry fails: bumping a template means recording what the new
version produces, and the guard can't be switched off by a bump.
"""

from pathlib import Path

import pytest
import yaml

from ansari.scaffold import available_templates, file_digest, find_bundled_template, generate

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden"


@pytest.mark.parametrize("template", available_templates())
def test_output_matches_the_golden_for_the_current_version(tmp_path: Path, template: str) -> None:
    spec = find_bundled_template(template)
    assert spec is not None
    golden_file = GOLDEN_DIR / f"{template}.yaml"
    assert golden_file.is_file(), f"no golden output recorded for {template}"

    goldens = yaml.safe_load(golden_file.read_text())
    missing = f"{template} {spec.version} has no golden output in {golden_file.name}"
    assert spec.version in goldens, missing
    golden = goldens[spec.version]

    repo = tmp_path / str(golden["variables"]["name"])
    written = generate(spec, dict(golden["variables"]), repo)

    assert sorted(written) == sorted(golden["files"])
    for path, digest in golden["files"].items():
        changed = f"{template}: {path} changed without a version bump"
        assert file_digest(repo / path) == digest, changed


def test_every_template_is_covered() -> None:
    """A new template can't ship without joining the guard."""
    recorded = {path.stem for path in GOLDEN_DIR.glob("*.yaml")}
    assert set(available_templates()) <= recorded
