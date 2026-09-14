# Phase details

Each milestone's goal, scope, acceptance criteria, and outcome. For ordering and
dependencies see [roadmap.md](roadmap.md); for how the result fits together see
[architecture.md](architecture.md).

| Milestone | Version | Status | Tests (scaffold + cli) | Coverage |
|---|---|---|---|---|
| — | v0.1 | ✅ | 24 | 92% |
| [M1 · Multi-template manifest](#m1--multi-template-manifest) | v0.2 | ✅ merged in #26 | 80 | 95% |
| [M2 · Pluggable templates](#m2--pluggable-templates) | v0.3 | ✅ merged in #26 | 123 | 96% |
| [M3 · Render modes](#m3--render-modes) | v0.3.1 | ✅ built · awaiting merge | 144 | 97% |
| [M4 · `k8s-scaling` + `attach`](#m4--k8s-scaling--attach) | v0.4 | 📋 next | | |
| [M5 · `terraform-module`](#m5--terraform-module) | v0.5 | 📋 | | |
| [M6 · `ansible-role`](#m6--ansible-role) | v0.6 | 📋 | | |
| [M7 · Fleet drift](#m7--fleet-drift) | v0.7 | 📋 | | |
| [Sync](#v08--sync) | v0.8 | 📋 | | |
| [Dashboard + demo](#v10--dashboard--demo) | v1.0 | 📋 | | |
| [Housekeeping](#housekeeping) | — | 📋 | | |

The API suite adds 17 tests on top of these counts. They run against Postgres
in CI.

---

## M1 · Multi-template manifest

**Status:** ✅ merged in #26 · **Version:** v0.2

**Goal.** Let one repo record more than one template (for example a service plus
its scaling config) without breaking any repo scaffolded before the change.

**Problem it solved.** `Manifest.template` and `.version` were plain strings, so
there was no way to record "is this repo, as a whole, on the golden path?"

**Scope**

- `schema: 2` plus a `templates:` list, one entry per attached template
- schema dispatch: absent → v1, `2` → v2, anything newer → `ManifestTooNewError`
- a v1 manifest is read as a one-entry list and never rewritten on read
- template resolution by recorded name instead of `variables.language`
- path-overlap invariant, enforced on both write and read
- `RepoDriftReport` with per-template reports plus `unresolved`
- `ensure_writable()`: writes refuse against unresolved entries, with an explicit
  `allow_unresolved` opt-in
- non-scalar variables in v2 (`int`, `bool`, `list[str]`)

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| A v1 manifest reads unchanged | golden fixture captured before the migration; `test_real_pre_migration_manifest_still_parses` |
| Reading never rewrites | `test_reading_a_v1_manifest_does_not_rewrite_it` |
| v1 and v2 print identical `check` output | `test_v1_and_v2_repos_print_identically` |
| Path overlap refused | five tests covering detection, write, read, attach, and the CLI |
| Unresolved → non-zero exit | `test_an_unresolved_template_exits_non_zero` |
| Writes refuse against unresolved | `test_writes_refuse_when_a_template_cannot_be_resolved` |

**Decisions**

- `templates` is a list rather than a map, because a repo may attach the same
  template twice in different directories.
- `schema` is an integer rather than semver, because it versions the document's
  shape.
- No compatibility shim for `Manifest.template`. mypy flags every stale caller
  instead, and it caught one immediately.

---

## M2 · Pluggable templates

**Status:** ✅ merged in #26 · **Version:** v0.3

**Goal.** Adding a template type requires no Python change.

**Problem it solved.** `SUPPORTED_LANGUAGES` / `SUPPORTED_DATABASES` were
constants in the CLI, and the variable dict was hardcoded.

**Scope**

- `variables:` block in `template.yaml`: `type`, `default`, `choices`,
  `description`
- `files:` accepts a mapping form (`dest:` plus options) as well as `source: dest`
- `ansari new --type <t> --var key=value` (repeatable)
- `ansari templates` lists bundled templates, read from the directory
- `--language` / `--database` kept as permanent aliases, with a warning on stderr
- unknown variables rejected; `name` reserved for ANSARI

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| A new type needs zero edits to `cli/main.py` | `test_cli_needs_no_edit_to_gain_a_template_type` scaffolds an unknown type end to end |
| The documented legacy command still works | `test_the_documented_legacy_invocation_still_works` |
| Mixing `--type` with the old flags is refused | `test_mixing_type_and_the_old_flags_is_refused` |
| Typos don't scaffold defaults | `test_var_rejects_an_undeclared_variable` |

**Public CLI:** no breaking change. Every documented invocation keeps its exit
code.

---

## M3 · Render modes

**Status:** ✅ built on `feat/render-modes` · awaiting merge · **Version:** v0.3.1

**Goal.** Support output formats that are themselves Jinja, binary or executable
files, and optional files, without special-casing any template.

**Scope**

- `render: {delimiters: alternate}` → `[[ ]]` `[% %]` `[# #]`
- per-file `render: copy` (bytes written unchanged)
- per-file `mode: "0755"` (must be a quoted octal string)
- per-file `when: <bool variable>`; files not generated are not tracked
- `generate()` in `scaffold/` replaces the CLI's render loop and checks every
  destination before writing anything

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| `{{ ansible_facts }}` survives rendering | `test_jinja_native_output_survives_rendering` (exact output match) |
| An executable file is generated | `test_mode_makes_a_generated_file_executable` |
| python-service output unchanged | `test_python_service_output_is_unchanged_by_the_new_pipeline`: all 7 files match the golden hashes |
| Refusals leave nothing on disk | destination outside repo, duplicate destination, and missing source tests |
| Copied, mode-set, and conditional files check clean | `test_render_modes_scaffold_and_check_clean` |

**Deviation from plan, recorded.** The approved delimiter pair was
`[[ ]]` / `[% %]`. The comment markers had to move too (`[# #]`), because a
`{# … #}` left alone in an Ansible task file would be silently deleted.

**Known limit introduced.** Drift compares content, not permission bits.

---

## M4 · `k8s-scaling` + `attach`

**Status:** 📋 next · **Version:** v0.4 · **Blocked on:** M1 ✅, M2 ✅

**Goal.** The first real repo with two templates: a python-service repo with
scaling config attached, and `check` reporting both.

**Scope**

- `k8s-scaling` template: HPA and PodDisruptionBudget for an existing chart,
  **versioned independently** from python-service
- `ansari attach --type <t> [--var …] [PATH]`:
  - loads the manifest; refuses via `ensure_writable()` when any entry is
    unresolved (`--allow-unresolved` to override)
  - renders with `generate()` into the existing repo
  - refuses destinations already owned by another template, and existing
    untracked files it would overwrite
  - appends a record with `attach_record()`, which writes schema 2
- composite `check` output exercised on real content

**Why this shape.** A config option on python-service couldn't be versioned
independently, and HPA/PDB API deprecations move on a different cadence from
Dockerfiles. A standalone template type makes no sense, because an HPA with no
Deployment isn't a thing you scaffold on its own.

**Acceptance criteria**

- a python-service repo carries two templates, and `check` reports both
- attaching onto a v1 repo upgrades its manifest and keeps the original entry
- `attach` refuses against an unresolved entry by default
- `attach` never overwrites a file it doesn't own

**Then:** review checkpoint 1.

---

## M5 · `terraform-module`

**Status:** 📋 · **Version:** v0.5 · **Blocked on:** M2 ✅ · checkpoint 1

**Goal.** A minimal module skeleton that passes validation in its own generated CI.

**Generated files**

```
main.tf  variables.tf  outputs.tf  versions.tf  README.md
examples/basic/main.tf
.github/workflows/ansari.yml
.gitignore
```

`versions.tf` pins `required_version` and `required_providers`. Provider pins are
what go stale fastest, and catching that is the point of drift tracking.

**Generated CI:** `terraform fmt -check -recursive` → `terraform init
-backend=false` → `terraform validate`. A `plan` job against `examples/basic/` is
included **commented out and labelled**: a module can't plan without a backend
and credentials, and ANSARI never needs credentials.

**Acceptance criteria**

- `ansari new vpc --type terraform-module` scaffolds, and `check` is clean
- `terraform validate` passes on the generated module
- provider list supplied via a `list` variable round-trips through the manifest

**Then:** review checkpoint 2.

---

## M6 · `ansible-role`

**Status:** 📋 · **Version:** v0.6 · **Blocked on:** M3 · checkpoint 2

**Goal.** A standard role layout, written without escaped braces.

**Generated files**

```
tasks/main.yml  handlers/main.yml  defaults/main.yml  meta/main.yml  README.md
molecule/default/{molecule.yml, converge.yml, verify.yml}   # only if with_molecule
```

- `render: {delimiters: alternate}`, so Ansible's `{{ }}` stays as written
- `meta/main.yml` mirrors the `galaxy_info` convention in the linux-vitals roles:
  `role_name`, `author`, `description`, `license`, `min_ansible_version`,
  `platforms`, `galaxy_tags`, `dependencies`
- molecule is **opt-in**, because the reference roles don't carry per-role molecule

**Generated CI:** `ansible-lint`, `yamllint`, and molecule only when scaffolded.

**Acceptance criteria**

- scaffolds and passes `ansible-lint`
- no `{{ '{{' }}`-style escaping anywhere in the template sources
- `with_molecule=false` generates and tracks no molecule files

---

## M7 · Fleet drift

**Status:** 📋 · **Version:** v0.7 · **Blocked on:** M4

**Goal.** Answer "who is behind, and on what?" across many repos.

**Scope**

- `ansari check --fleet --root DIR` finds `.ansari/manifest.yaml` files under DIR
- per-repo composite results plus a per-template-type summary
  ("12 of 40 behind on python-service; 3 of 8 behind on terraform-module")
- `TEMPLATE_BINDING` table, **one row per attached template**, with a migration;
  the repo's manifest remains authoritative

**Acceptance criteria**

- a fleet mixing template types and multi-template repos reports correctly
- the exit code is non-zero if any repo isn't clean
- `alembic check` stays clean

---

## v0.8 · Sync

**Status:** 📋

- re-render the recorded version (from recorded variables) and the current one
- three-way merge against the local file; untouched files replaced, edited files
  merged with conflicts surfaced, deleted files left alone
- `ansari sync --pr`: one pull request per stale repo via `src/ansari/integrations/`
- refuses against unresolved entries, with no override

---

## v1.0 · Dashboard + demo

**Status:** 📋

- fleet health, adoption, and drift by template type
- `make demo`: seeds a fleet, drifts it, shows the report

---

## Housekeeping

Low priority, and deliberately kept out of feature diffs so those stay reviewable.

| Item | State |
|---|---|
| `service_dir` → `repo_dir` in `manifest.py` / `drift.py` | ✅ done in M1 |
| `bundled_template(language)` → resolve by name only | 📋 still used by tests |
| CLI app help ("Scaffold services on the golden path") and the "This service was not scaffolded" message | 📋 |
| Move templates from `cli/templates/` to `src/ansari/templates/` | 📋 |
| Rename the `projects` table to `services` | 📋 with the next migration |
