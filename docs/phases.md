# Phase details

Each milestone's goal, scope, acceptance criteria, and outcome. For ordering and
dependencies see [roadmap.md](roadmap.md); for how the result fits together see
[architecture.md](architecture.md).

| Milestone | Version | Status | Tests (scaffold + cli) | Coverage |
|---|---|---|---|---|
| — | v0.1 | ✅ | 24 | 92% |
| [M1 · Multi-template manifest](#m1--multi-template-manifest) | v0.2 | ✅ merged in #26 | 80 | 95% |
| [M2 · Pluggable templates](#m2--pluggable-templates) | v0.3 | ✅ merged in #26 | 123 | 96% |
| [M3 · Render modes](#m3--render-modes) | v0.3.1 | ✅ merged in #28 | 144 | 97% |
| [M4 · `k8s-scaling` + `attach`](#m4--k8s-scaling--attach) | v0.4 | ✅ merged in #29 | 178 | 98% |
| [M5 · `terraform-module`](#m5--terraform-module) | v0.5 | ✅ merged in #30 | 199 | 98% |
| [M6 · `ansible-role`](#m6--ansible-role) | v0.6 | ✅ merged in #31 | 219 | 98% |
| [M7 · Fleet drift](#m7--fleet-drift) | v0.7 | ✅ merged in #32 | 236 | 97% |
| [Sync](#v08--sync) | v0.8 | ✅ merged in #33 | 273 | 97% |
| [Dashboard + demo](#v10--dashboard--demo) | v1.0 | ✅ built · awaiting merge | 298 | 97% |
| [Housekeeping](#housekeeping) | — | 📋 | | |

From v1.0 the counts include the `dashboard` and `demo` suites. The API suite
adds 29 tests on top of these counts. They run against Postgres in CI.

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

**Status:** ✅ merged in #28 · **Version:** v0.3.1

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

**Status:** ✅ merged in #29 · **Version:** v0.4

**Goal.** The first real repo with two templates: a python-service repo with
scaling config attached, and `check` reporting both.

**Scope**

- `k8s-scaling` 0.1.0, attach-only (`standalone: false`): `autoscaling.yaml`
  (the numbers), a `HorizontalPodAutoscaler`, and a `PodDisruptionBudget`,
  written with alternate delimiters so Helm's `{{ }}` passes through
- `ansari attach --type <t> [PATH] [--var …] [--name …] [--allow-unresolved]`,
  backed by `scaffold.attach_template()`
- python-service **1.0.0 → 1.1.0**, so the Deployment stops setting `replicas`
  once scaling is attached (see below)
- `ansari new` refuses attach-only templates; `ansari templates` labels them
- `generate()` refuses to write into `.ansari/`

**The finding that reshaped this milestone.** python-service's Deployment set
`replicas: {{ .Values.replicaCount }}` unconditionally. With an autoscaler
attached, every `helm upgrade` would have reset the replica count the autoscaler
had chosen. `helm create` guards that field for exactly this reason. Shipping the
HPA on its own would have crossed the first tripwire: output that shouldn't go
to production.

k8s-scaling can't edit a file python-service owns, so the fix is a contract
between the two templates, pinned by a test:

- k8s-scaling writes `helm/<name>/autoscaling.yaml`
- python-service 1.1.0's Deployment omits `replicas` while that file is in the
  chart (`.Files.Get "autoscaling.yaml"`)

Attaching alone produces a correct chart, with no hand-edit and no drift
reported against python-service's files. Charts without scaling render exactly
as before.

**Consequence, accepted.** Every repo scaffolded on python-service 1.0.0 now
reports *behind*. That's drift detection doing its job, but with no `sync` yet,
upgrading a repo is manual. Between the two versions only `deployment.yaml` and
`values.yaml` changed; the other five files are byte-identical.

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| A python-service repo carries two templates, and `check` reports both | `test_attach_then_check_reports_both_templates` |
| Attaching onto a v1 repo upgrades it and keeps the original entry | `test_attaching_onto_a_v1_repo_upgrades_it_and_keeps_the_original_entry` |
| Refuses against an unresolved entry by default | `test_attach_refuses_an_unresolved_entry_and_writes_nothing` |
| Never overwrites a file it doesn't own | `test_attach_never_overwrites_an_untracked_file`, `test_attaching_the_same_template_twice_is_refused`, `test_an_unresolved_templates_files_are_still_protected` |
| The autoscaler owns replicas in the rendered chart | `test_with_scaling_the_autoscaler_owns_replicas` (real `helm template`) |
| The chart lints, and refuses impossible bounds | `test_the_chart_lints_with_scaling_attached`, `test_the_chart_refuses_to_render_impossible_bounds` |
| The two templates agree on the contract file | `test_python_service_checks_for_the_file_k8s_scaling_writes` |

Every refusal test compares a byte snapshot of the whole repo before and after.
The Helm tests skip where `helm` isn't installed.

**Decisions**

- `maxUnavailable: 1` rather than `minAvailable`: a `minAvailable` at or above
  the replica count stalls every node drain.
- Bounds are enforced where they're used: the chart fails to render when
  `minReplicas` is below 1 or above `maxReplicas`. The descriptor has no way to
  express a rule spanning two variables, and one wasn't added for this.
- The golden-output guard now keeps hashes per python-service version
  (`tests/fixtures/golden/python-service.yaml`). A version bump with no recorded
  entry fails, so a bump can't silently switch the guard off.

**Then:** review checkpoint 1, before `terraform-module` starts.

---

## M5 · `terraform-module`

**Status:** ✅ merged in #30 · **Version:** v0.5

**Goal.** A module skeleton that is valid Terraform for every supported provider,
with credential-free validation in its own generated CI.

**Generated files**

```
versions.tf  main.tf  variables.tf  outputs.tf  README.md  .gitignore
examples/basic/main.tf
.github/workflows/ansari.yml
```

- `--var provider=aws|google|azurerm` (default `aws`). `versions.tf` pins
  `required_version >= 1.6.0` and the provider to its **current major**, checked
  against the Terraform Registry when the template was written: aws `~> 6.0`,
  google `~> 8.0`, azurerm `~> 5.0`.
- The module configures **no provider**; `examples/basic/` is the root
  configuration that does. google gets `labels`, the others `tags`.
- `name` is validated in HCL: 2–63 lowercase letters, digits, or hyphens.
- `.gitignore` is copied verbatim (M3's `copy` mode) and ignores
  `.terraform.lock.hcl`, as a reusable module should.

**Generated CI:** `terraform fmt -check -recursive`, then
`terraform init -backend=false` + `terraform validate` for the module and the
example, with `permissions: contents: read`. The `plan` job is present but
**commented out and labelled**. Actions are pinned to current majors
(`actions/checkout@v7`, `hashicorp/setup-terraform@v4`).

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| Scaffolds, and `check` is clean | `test_scaffolds_the_expected_layout_and_checks_clean` |
| Output is valid Terraform | `test_terraform_validates_the_module_and_example`: real Terraform, locally for **aws, google and azurerm**, in CI for aws |
| Output is `terraform fmt`-clean | `test_terraform_fmt_accepts_the_output`, all three providers |
| The module rejects invalid names | `test_terraform_rejects_an_invalid_name` |
| Generated CI needs no credentials, and `plan` is off | `test_generated_ci_validates_without_credentials`, `test_plan_ships_commented_out` |

**Found by running the real tool.** The first version rendered the `locals` body
without indentation, because a Jinja `-%]` trims the next line's leading spaces as
well as the newline. Every other check passed, including the golden hashes, which
had recorded the broken output. `terraform fmt -check` caught it.

**CI.** A new `template-smoke` job installs Terraform and runs the template tests
with `ANSARI_TERRAFORM_VALIDATE=aws`, so a template that renders but wouldn't
validate fails the build. A provider download is several hundred megabytes, so
google and azurerm are validated on demand rather than on every run.

**Also.** The golden-output guard now covers **every** bundled template, not only
python-service, and fails when a template has no recorded output at all.

**Then:** review checkpoint 2, before `ansible-role` starts.

---

## M6 · `ansible-role`

**Status:** ✅ merged in #31 · **Version:** v0.6

**Goal.** A standard role layout that passes ansible-lint's production profile,
written without a single escaped brace.

**Generated files**

```
tasks/main.yml  handlers/main.yml  defaults/main.yml  meta/main.yml  README.md
.yamllint  .ansible-lint  .gitignore  .github/workflows/ansari.yml
molecule/default/{molecule,converge,verify}.yml     # only with with_molecule=true
```

- `render: {delimiters: alternate}`: Ansible's `{{ }}` is written exactly as
  authored, and no template source escapes a brace.
- `meta/main.yml` follows the linux-vitals `galaxy_info` convention. The role name
  is the repository name with hyphens turned into underscores, as Galaxy requires.
  Free text (`author`, `description`, `license`) is JSON-quoted, so a colon or a
  quote can't break the YAML.
- Variables: `description`, `author`, `namespace` (left out when empty),
  `license`, `min_ansible_version`, `platforms` (list), `galaxy_tags` (list), and
  `with_molecule` (bool, off by default). None is required.
- Role variables carry the role prefix (`disk_health_enabled`), which
  ansible-lint's `var-naming` rule requires.
- `.ansible-lint` sets the `production` profile; `.yamllint` is compatible with
  ansible-lint and allows GitHub's `on:` key.

**Generated CI:** `yamllint` and `ansible-lint` (settings from `.ansible-lint`)
under `permissions: contents: read`. With `with_molecule=true`, a second job runs
`molecule test` in Docker.

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| Passes ansible-lint's production profile | `test_ansible_lint_production_profile_passes`: real ansible-lint, with and without molecule |
| Passes `yamllint --strict` | `test_yamllint_strict_passes` |
| No brace escaping in any template source | `test_no_template_source_escapes_its_braces` |
| `with_molecule=false` generates and tracks no molecule files | `test_scaffolds_the_standard_role_layout_and_checks_clean` |
| The Molecule scenario converges, is idempotent, and verifies | `test_molecule_scenario_converges_idempotently`, run locally in Docker (opt-in: `ANSARI_MOLECULE_TEST=1`) |
| Metadata stays valid YAML with awkward values | `test_meta_survives_awkward_values` |

**Found by running the real tools.** Four defects, each invisible to every check
short of the tool itself:

1. ansible-lint failed the generated workflow for lacking a `---` document start.
2. It would also have failed the committed `.ansari/manifest.yaml` for the same
   reason, in every role repository's own CI. `.ansible-lint` and `.yamllint` now
   exclude `.ansari/`.
3. `molecule test` couldn't find the role at converge. Fixed with
   `ANSIBLE_ROLES_PATH`.
4. Molecule then refused to start, because an author name isn't a valid Galaxy
   namespace. Fixed with `role_name_check: 1`: the check matters for publishing,
   not for testing.

**CI.** `template-smoke` installs ansible-lint, with yamllint and ansible-core, as
an isolated `uv tool` and runs the role tests. Molecule pulls a container image,
so it's opt-in rather than part of every run.

**Then:** M7. With four template types, no fifth is proposed, so the `sync --pr`
tripwire isn't crossed.

---

## M7 · Fleet drift

**Status:** ✅ merged in #32 · **Version:** v0.7

**Goal.** Answer "who is behind, and on what?" across many repos, from the CLI and
in the API.

**CLI: `ansari check --fleet [ROOT]`**

- Reuses `check`'s existing path argument as the directory to scan, so plain
  `check` is unchanged.
- Finds every `.ansari/manifest.yaml` under ROOT, at any depth and including ROOT
  itself. Skips `.git`, `.terraform`, `node_modules`, virtualenvs and tool caches,
  and never follows a symlinked directory.
- One line per attached template per repo, then a by-template summary counting
  **attachments**: a repo that attaches a template twice counts twice.
- Exits non-zero when any repo is behind, edited, unverifiable, or has an
  unreadable manifest. **Finding no repos also exits non-zero**, because a fleet
  check pointed at the wrong directory must not pass.

```console
$ ansari check --fleet ~/src
Fleet: 4 repos under ~/src

  infra/disk-health  ansible-role 0.1.0 (current)
  infra/network      terraform-module 0.1.0 (current)
  orders             python-service 1.1.0 (current)
                     k8s-scaling 0.1.0 (current), 1 file edited
  payments           python-service 1.1.0 (current)

By template:
  ansible-role      1 attached · 0 behind · 0 edited
  k8s-scaling       1 attached · 0 behind · 1 edited
  python-service    2 attached · 0 behind · 0 edited
  terraform-module  1 attached · 0 behind · 0 edited

1 of 4 repos off the golden path.
```

**API: template bindings**

- `template_bindings` table, **one row per attached template**: `position`
  (manifest order, unique per project), `template`, `version`, `rendered_at`,
  `files`, and `behind` / `edited` / `unresolved` flags. `project_id` and
  `template` are indexed, and rows are deleted with their project.
- `PUT /projects/{id}/template-bindings` replaces a project's whole set in manifest
  order, and rejects a payload where two templates claim the same file.
  Timestamps must carry a timezone.
- `GET /projects/{id}/template-bindings`, and fleet-wide
  `GET /template-bindings?template=…&behind=…&edited=…&unresolved=…`, both
  paginated like every other list endpoint.

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| A fleet mixing template types and multi-template repos reports correctly | `test_the_summary_counts_attachments_per_template`, `test_a_mixed_fleet_reports_each_repo` |
| The exit code is non-zero if any repo isn't clean | `test_a_drifted_fleet_exits_non_zero_and_names_the_problem` |
| Unreadable manifests are reported, never skipped | `test_an_unreadable_manifest_is_reported_not_skipped` |
| An empty scan fails | `test_finding_no_repos_fails` |
| Bindings replace as a set and keep manifest order | `test_put_replaces_the_whole_set`, `test_put_then_get_keeps_manifest_order_and_drift_flags` |
| The fleet listing answers "who is behind" | `test_the_fleet_listing_answers_who_is_behind` |
| `alembic check` stays clean | CI's `alembic check`; also verified locally, with a downgrade and re-upgrade |

**Found by the tests.** A fleet where no manifest could be read crashed
`check --fleet`: with no drift reports there were no templates to summarise, and
the summary took `max()` over an empty list. It now skips the summary, and
`test_a_fleet_with_nothing_readable_fails_without_crashing` covers it.

**Not yet wired.** Nothing reports bindings to the API yet; `check --fleet` reads
repos directly. A `--report` option is the natural next step, and deliberately
isn't part of this milestone.

---

## v0.8 · Sync

**Status:** ✅ merged in #33 · **Version:** v0.8

**Goal.** Upgrade repos to the current template versions without discarding what
people changed: the step that makes drift detection worth having.

**`ansari sync [PATH] [--dry-run] [--allow-dirty] [--fleet] [--pr]`**

For every attached template that is behind, each generated file is handled by
what its recorded hash says:

| On disk | Sync does |
|---|---|
| untouched | replaces it with the new version's output |
| edited | three-way merges it; overlapping edits get conflict markers |
| deleted | leaves it deleted, and `check` keeps reporting it |
| new in this version | adds it |
| dropped by this version, untouched | removes it |
| dropped by this version, edited | keeps it, and stops tracking it |

```console
$ ansari sync --dry-run
python-service  1.0.0 → 1.1.0
  updated      helm/payments/templates/deployment.yaml
  merged       helm/payments/values.yaml

Dry run: nothing written.
```

**Where the merge ancestor comes from.** A three-way merge needs what the *old*
version generated, but this build only ships each template's current version.
The manifest recorded that output's sha256, so sync finds it in the repo's own git
history: the committed blob with that hash. The new version renders with the
variables the repo was scaffolded with, and new variables take their defaults.

**Refusals.** A template is refused, with nothing written for it, when an edited
file has no ancestor in history, a new file would land on an untracked one, a
destination belongs to another template, or a newly required variable has no
value. The whole sync refuses when the repo isn't a git working tree, has
uncommitted changes (unless `--allow-dirty`), or carries a template this build
can't resolve.

**`--pr`** commits on `ansari/sync-<template>-<version>`, pushes, and opens a pull
request through the `git` and `gh` CLIs, which carry the user's credentials, so
ANSARI holds no token. It opens nothing while a template is refused or
conflicted, so conflict markers are never committed. `--fleet` syncs every repo
under PATH, one pull request each.

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| A python-service 1.0.0 repo upgrades to 1.1.0, keeping a local edit | `test_a_python_service_1_0_0_repo_upgrades_to_the_current_version`, on a 1.0.0 reconstructed byte for byte against the golden hashes |
| Untouched files replaced, edited files merged, deleted files left deleted | `test_untouched_files_are_replaced_and_the_version_moves`, `test_an_edited_file_is_merged_keeping_both_changes`, `test_a_deleted_file_stays_deleted` |
| Overlapping edits get conflict markers and a non-zero exit | `test_overlapping_edits_get_conflict_markers`, `test_a_conflict_exits_non_zero` |
| Every refusal writes nothing | `test_an_edit_with_no_ancestor_in_history_refuses_the_template`, `test_an_untracked_file_in_the_way_of_a_new_one_refuses` |
| `--dry-run` writes nothing | `test_dry_run_writes_nothing` |
| `--pr` opens one pull request per repo, and none with conflicts | `test_pr_commits_on_a_branch_and_opens_a_pull_request`, `test_fleet_pr_opens_one_pull_request_per_repo`, `test_pr_is_not_opened_when_there_are_conflicts` |
| Refuses against unresolved entries, with no override | `test_an_unresolved_template_refuses_the_whole_sync` |

**Limit.** A file edited before the scaffold was first committed has no ancestor in
history, so its template is refused and that upgrade is done by hand.

---

## v1.0 · Dashboard + demo

**Status:** ✅ built · awaiting merge · **Version:** v1.0

**Goal.** Make the fleet's state something a person can look at, and let anyone
watch the whole loop (scaffold, drift, detect, plan the upgrade) with one command.

**`ansari dashboard [ROOT] [--output FILE]`**

- Scans exactly like `check --fleet`, from the same `FleetReport`, so the page
  and the terminal can't disagree. A test compares the two.
- Writes one self-contained HTML file: no server, nothing fetched, readable from
  disk or as a CI artifact. Light and dark follow the viewer's system setting.
- **Fleet health:** repos on the golden path, and a breakdown that counts each
  repo once under its most severe state (unreadable › cannot verify › behind ›
  edited › current), so the parts add up to the total.
- **Adoption:** for each template, how many readable repos attach it, and which
  versions are in use, with the shipped version first.
- **Drift by template type:** attachments by state, beside the same
  `N attached · N behind · N edited` line `check --fleet` prints.
- **Repos:** every repo with its state, each attached template's version, and the
  edited files. An unreadable manifest is listed with its error, never dropped.
- Exits 0 once the page is written, drift or not: `check --fleet` is the gate,
  this is the report. An empty scan still fails, for the same reason `check` does.

**`make demo`**

Seeds `.demo/fleet`, then runs `ansari check --fleet`, `ansari sync --fleet
--dry-run` and `ansari dashboard` against it, printing each exit code rather than
stopping on the expected non-zero ones.

| Repo | How it drifted | Shows as |
|---|---|---|
| `services/payments` | python-service + k8s-scaling, both current | on the golden path |
| `services/orders` | python-service 1.0.0, never upgraded | behind; sync *updates* |
| `services/checkout` | python-service 1.0.0, memory tuned by hand | behind; sync *merges* `values.yaml` |
| `services/search` | Dockerfile edited | edited |
| `infra/network` | terraform-module (aws) | on the golden path |
| `infra/dns` | terraform-module (google), example deleted | edited |
| `roles/disk-health` | ansible-role | on the golden path |
| `roles/ntp` | a template from a newer ANSARI attached | cannot verify |
| `legacy/reports` | manifest hand-edited so two templates claim one file | unreadable |

Every repo is written by the code `new` and `attach` run and committed to git, so
the dry-run sync plans against real history. The behind repos are real 1.0.0
output: `src/ansari/demo/python-service-1.0.0/` holds 1.0.0's descriptor and the
two sources 1.1.0 changed, and laid over the current template it regenerates 1.0.0
byte for byte against the golden hashes. A re-run replaces `.demo/fleet` only when
it carries the demo's marker file; any other non-empty directory is refused.

**Acceptance criteria and evidence**

| Criterion | Evidence |
|---|---|
| Health counts each repo once, under its most severe state | `test_every_repo_is_counted_once_under_its_most_severe_state` |
| Adoption counts repos; drift counts attachments | `test_adoption_counts_repos_and_drift_counts_attachments` |
| The page agrees with `check --fleet` | `test_the_summary_matches_check_fleet` |
| Paths and errors read from disk are escaped | `test_the_page_names_every_repo_and_escapes_what_it_read_from_disk` |
| Written with exit 0 on a drifted fleet; an empty scan refused | `test_dashboard_writes_the_page_and_exits_zero_despite_drift`, `test_dashboard_refuses_an_empty_fleet_and_writes_nothing` |
| The demo covers every template type and every state | `test_every_template_type_and_every_state_appears`, `test_each_repo_tells_the_story_it_is_listed_with` |
| Its behind repos are the real 1.0.0 | `test_the_old_python_service_is_the_real_1_0_0` |
| Sync can upgrade them, keeping the hand edit | `test_sync_can_upgrade_the_behind_repos_keeping_the_hand_edit` |
| Never replaces a directory it didn't create | `test_refuses_a_directory_the_demo_did_not_create` |

**Found by running it.**

1. The unreadable repo first had git conflict markers in its manifest. PyYAML's
   error for that runs to seven lines and buried the fleet report, in `check` and
   `sync` alike. The repo now carries a manifest where two templates claim one
   file: a one-line error, and a real invariant on show.
2. The palette validator failed the first state colours: *edited* (yellow) beside
   *behind* (orange) measured ΔE 13.6, under the floor for full colour vision.
   Behind is now red and unreadable violet. Every state also carries a text label,
   so none relies on colour alone.
3. Repo paths wrapped mid-word in a narrow table column; they no longer wrap.

**Decisions**

- A static file rather than an API page. Nothing reports bindings to the API yet
  (see M7), so an API-backed page would be empty; reading repos keeps the
  dashboard as offline as `check`.
- Behind outranks edited, because behind is what sync can act on and an edit may
  be deliberate.
- The demo runs as `python -m ansari.demo` rather than an `ansari demo` command,
  so a teaching aid adds nothing to the public CLI.

**Limits.** The page is a snapshot: no history, no trend. Adoption over time needs
the API, or stored reports. The CLI still prints a malformed-YAML error as
PyYAML's multi-line message.

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
