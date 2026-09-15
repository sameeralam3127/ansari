# Roadmap

## Shipped

| Version | What |
|---|---|
| v0.1 | `ansari new`, `ansari check`, REST API, CI with Trivy |
| v0.2 | Manifest schema 2: several templates per repo; older manifests still read |
| v0.3 | Pluggable templates: `--type`, `--var`, variables declared by each template |
| v0.3.1 | Render modes: alternate delimiters, verbatim copy, file modes, conditional files |
| v0.4 | `k8s-scaling` template and `ansari attach` |
| v0.5 | `terraform-module` template |
| v0.6 | `ansible-role` template |
| v0.7 | `ansari check --fleet`, and template bindings in the API |
| v0.8 | `ansari sync`: three-way merge, one pull request per repo |
| v1.0 | `ansari dashboard` and `make demo` |

## Next

- Report fleet drift to the API, so the dashboard can show history
- Move python-service's generated workflow to current GitHub Actions versions
- Move bundled templates from `cli/templates/` to `src/ansari/templates/`

## Quality bar

- `ruff` and `mypy --strict` clean, with tests for every change
- Each template's output is pinned per version; a change needs a version bump
- Generated output is checked by the real tools (`terraform`, `helm`,
  `ansible-lint`, `yamllint`) in CI

## Out of scope

- Running `terraform apply` or `ansible-playbook` against live infrastructure
- Running CI, reconciling Kubernetes, or collecting telemetry
- An out-of-tree template registry
- Multi-tenancy, SSO, and billing
