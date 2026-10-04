# Experiment protocol and reproducibility

## The specification (unit of work)

`experiments/configs/<ID>.yaml`, validated against `schemas/experiment.schema.json` plus
cross-reference checks (`research exp validate`):

| Field | Purpose |
|---|---|
| `id`, `title`, `type` | identity; type ∈ baseline, proposed, ablation, sensitivity, robustness, generalization, efficiency, replication, exploratory, measurement, simulation, other |
| `research_questions`, `hypotheses` | must exist in project.yaml |
| `rationale` | why the experiment is needed (required) |
| `depends_on`, `compare_with` | must name existing experiments |
| `dataset` | name and version; must be registered and validated |
| `method`, `parameters`, `variables` | what is varied and what is controlled |
| `entrypoint.command`, `code_files` | `{python}`, `{config}`, `{run_dir}` and `{seed}` placeholders; code files are checksummed |
| `seeds` | one run per seed |
| `metrics` | name, direction, unit, definition, valid_range |
| `expected_outputs`, `expected_samples` | checked by validation |
| `compute` | backend, device, estimated_hours, timeout_hours |
| `statistics` | test (auto or a named test), paired_by (seed or null) |
| `failure_criteria`, `confounders`, `nondeterminism_notes` | stated before running |

## Runs

Each execution creates `runs/metadata/<EXP>__s<seed>__<UTCstamp>__<rand>.json`
(exclusive create, so it never overwrites), a config snapshot
`<run_id>.config.json`, and `runs/raw/<run_id>/` for outputs.

Run status: `CREATED → RUNNING → COMPLETED | FAILED | CANCELLED | TIMED_OUT`, `SUBMITTED`
(remote), or `IMPORTED` (manual). A terminal status can never change: re-running means
a new run. Identity fields (`config_snapshot`, `config_sha256`, `seed`, `dataset`,
`provenance`) are immutable.

## Reproducibility record (per run)

- config snapshot and its SHA-256 identity
- dataset name, version, fingerprint (SHA-256 of every file) and validation status
- git commit, branch and dirty flag of the project (a missing commit makes the run PROVISIONAL)
- SHA-256 of each declared code file
- Python, key package versions, platform, CPU count, GPUs (`nvidia-smi`), hashed hostname
- determinism-relevant environment variables (`PYTHONHASHSEED`, `CUBLAS_WORKSPACE_CONFIG`, thread counts, …)
- seed (`runtime.seed_all` seeds Python, NumPy and PyTorch if installed)
- start and finish times, runtime, exit code, error
- SHA-256 of every output file (tamper detection)
- the spec's `nondeterminism_notes`

## Preflight gates (all checked before any record is created)

1. The spec is schema-valid and its references resolve.
2. The dataset validation passes and is current (or an override is recorded).
3. The requested GPU exists locally. There is no silent CPU fallback.
4. `stopping.compute_budget_hours` is not exceeded (used + estimated).
5. A researcher approval exists when `execution.approval` requires one.

## Local execution

A subprocess with the project root as working directory and stdout/stderr captured to
`runs/raw/<id>/execution.log`. It supports a timeout (`compute.timeout_hours` or
`execution.default_timeout_hours`) and Ctrl+C cancellation: the running run becomes
CANCELLED and any unstarted seeds are marked CANCELLED. `--parallel N` runs seeds
concurrently, up to `execution.max_concurrent`. One failure never stops the other seeds.

## Resuming

`research run ID --resume-from <run_id>` creates a new run whose script receives
`RP_RESUME_DIR` (the earlier run's outputs). Whether a script can resume is up to the
script. The engine records the link.

## Experiment types: what each should establish

- **baseline**: a reference point under the identical protocol
- **proposed**: the method under test; must `compare_with` a baseline
- **ablation**: changes exactly one setting of the experiment it `depends_on` (the audit checks this)
- **sensitivity / robustness**: sweeps or perturbations, declared in `variables`
- **generalization**: a different dataset; never pooled with in-distribution results
- **efficiency**: runtime and resource metrics with units
- **replication**: the same config with new seeds or on new hardware
- **measurement / simulation**: non-ML studies, often imported with `research import`
