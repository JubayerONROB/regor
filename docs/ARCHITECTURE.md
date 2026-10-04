# Architecture

## Principles

1. **Files are the state.** Every module reads and writes plain files inside a project
   directory. There is no database and no daemon, and nothing lives only in memory.
   `regor status` rebuilds the full picture from disk.
2. **Schemas are the interfaces.** Modules communicate through documented file formats
   (`regor/schemas/*.schema.json`), validated on every load and save.
3. **The core is domain-free.** No module branches on a field or a model type. Domain
   knowledge lives in data (`domains.py` profiles, or a project's `domain.yaml`).
4. **Evidence flows one way.** raw outputs → run record → validation → analysis →
   claims → manuscript. A later stage never edits an earlier one.
5. **Consequential actions are gated.** Approvals, decisions and hypothesis verdicts are
   records with a named researcher.

## Module map

| Module | Responsibility | Reads | Writes |
|---|---|---|---|
| `cli.py` | `regor` command | everything | via modules |
| `project.py` | locate, load and validate the project, `init` scaffolding | `project.yaml` | project tree |
| `config.py` | JSON-schema validation, defaults | `schemas/` | – |
| `domains.py` | domain adapter profiles | `domain.yaml` | – |
| `scaffold.py` | text of new-project files | – | – |
| `datasets.py` | registration, fingerprints, validation, gate | manifest, data files | `data/validation/*` |
| `experiments.py` | spec loading and checks, config identity hash, immutable run records | `experiments/configs/` | `runs/metadata/` |
| `provenance.py` | environment, hardware, git, package versions | system | – |
| `approvals.py` | single-use approvals bound to the config hash | `approvals/approvals.yaml` | same |
| `engine.py` | preflight gates, dry-run plans, dispatch, remote collection | all of the above | run records |
| `executors/local.py` | subprocess execution, timeout, cancellation | spec | `runs/raw/<id>/` |
| `executors/kaggle.py` | kernel packaging, secret scan, push, poll, download (real CLI and mock clients) | spec, `execution.kaggle` | `runs/remote/`, `runs/raw/` |
| `executors/manual.py` | import external measurements with provenance | user files | `runs/raw/<id>/imported/` |
| `executors/base.py` | output checksums, metric lifting | raw dir | run record |
| `runtime.py` | script-side contract (stdlib only, bundled into kernels) | env vars | `metrics.json` |
| `results.py` | validation status per run | run record, raw dir | run record (`validation`) |
| `analysis/stats.py` | descriptive statistics, tests with assumption checks, effect sizes, CIs, corrections | – | – |
| `analysis/compare.py` | aggregation and comparison over validated runs | run records | `analysis/comparisons/*.json/.md` |
| `analysis/viz.py` | figures with provenance sidecars | comparison summary | `analysis/visualizations/` |
| `reports.py` | 21-section experiment reports | runs, analyses, claims | `reports/experiment_reports/` |
| `evidence.py` | claim registry, resolution, contradictions, evidence index | claims, runs, analyses | `evidence/*.yaml` |
| `literature.py` | reference registry, Crossref/arXiv verification, BibTeX, matrix | `literature/references.yaml` | same, `.bib`, `.csv` |
| `iteration.py` | proposals, decisions, iterations, stopping rules | everything | `experiments/plans/*.yaml` |
| `progress.py` | status reconstruction, PROGRESS.md, decision log, history views | everything | `reports/progress_reports/`, `docs/` |
| `manuscript/markers.py` | marker grammar (shared by render and audit) | – | – |
| `manuscript/draft.py` | section skeletons and evidence-driven drafts | specs, claims, data | `manuscript/sections/` |
| `manuscript/render.py` | resolve markers into a Markdown build | sections, evidence | `manuscript/build/` |
| `manuscript/audit.py` | numerical, claim, reference, methodology and language audit | sections, evidence, specs, runs | `manuscript/audit/` |
| `manuscript/journal.py` | journal profile, checklist, LaTeX/Markdown/(pandoc) export | build, profile | `manuscript/journal_format/<slug>/` |
| `security.py` | secret scanner (never echoes matches) | files | – |

## Data contracts (schemas)

| Schema | File | Key fields |
|---|---|---|
| `project` | `project.yaml` | project, research (questions, hypotheses), statistics, execution (approval, kaggle), stopping, manuscript |
| `experiment` | `experiments/configs/<ID>.yaml` | id, type, rationale, RQs and hypotheses, dataset, method, entrypoint, seeds, metrics, expected outputs and samples, compute, statistics |
| `dataset_manifest` | `data/dataset_manifest.yaml` | name, version, source, licence, files and splits, target/group/id columns, column checks, metadata requirements, custom checks |
| `run_record` | `runs/metadata/<run_id>.json` | run_id, experiment_id, status, validation, config_sha256, config_snapshot, seed, backend, dataset, provenance, timings, outputs (checksums), metrics, remote, approval_id |
| `claims` | `evidence/claims.yaml` | id, text, type, research_question, source (runs_metric, analysis, artifact, literature, researcher), stated_value, tolerance, status, verified_value, contradicted_by, used_in |

## Run identity

`config_sha256 = sha256(canonical JSON of id, dataset, method, entrypoint, parameters,
metrics, expected_outputs, expected_samples, compute minus estimated_hours)`. Editing
prose (title, rationale) does not change identity. Anything that changes results does.
Approvals are bound to this hash.

## Execution contract

The executor sets `REGOR_RUN_ID`, `REGOR_RUN_DIR`, `REGOR_CONFIG`, `REGOR_SEED` (and
`REGOR_RESUME_DIR` when resuming) and expects `metrics.json` in `REGOR_RUN_DIR`. The same
script runs locally and on Kaggle unchanged.

## Extending

- **New domain:** add `domain.yaml` to the project (no code needed).
- **New dataset check:** `custom_checks: ["mymodule:check"]` in the manifest. The
  function returns `[{level, check, message}]`.
- **New executor:** subclass `executors.base.Executor`, register it in
  `engine.make_executor`.
- **New statistical test:** extend `analysis/stats.compare_two`. Keep the "rationale +
  assumptions + warnings" contract.
