# Data management

## Registration

```bash
research data register --from-yaml data/my_dataset.yaml
# or
research data register --name sensors --version 1.0 --file data/raw/train.csv:train \
    --file data/raw/test.csv:test --license "CC-BY-4.0" --source-kind local \
    --target fault --group-column machine_id --access-verified
```

Manifest fields (`schemas/dataset_manifest.schema.json`): name, version, synthetic,
description, source (kind ∈ local, kaggle, url, instrument, manual, generated; location;
access_verified), license (name, url, permitted_use, redistribution_allowed),
collection_methodology, files (path, split), target, features, group_column, id_column,
expected_rows per split, split_fractions, column_checks (unit, min, max, allowed,
required, max_missing_fraction), time_column and expected_interval, metadata,
metadata_requirements, custom_checks, preprocessing, known_limitations.

Registering computes a SHA-256 fingerprint of every file. A corrected entry needs
`--replace`. A changed dataset should be registered under a new version.

## Validation checks

| Check | Level | Applies to |
|---|---|---|
| licence unknown / redistribution unconfirmed | WARN / INFO | all |
| access not verified | WARN | all non-generated |
| synthetic flag | INFO, and a banner in every report | all |
| manifest `metadata_requirements` missing | FAIL | all |
| domain-suggested metadata missing | INFO | all |
| file missing | FAIL | all |
| fingerprint changed since registration | WARN | all |
| empty file, ragged rows | FAIL | CSV/TSV |
| missing values (worst column > 5 %) | WARN (else INFO) | CSV/TSV |
| duplicate rows (id column excluded) | WARN | CSV/TSV |
| IQR outliers, flagged and never removed | INFO | numeric columns |
| column range / unit / non-numeric | FAIL | declared columns |
| allowed values (label validity) | FAIL | declared columns |
| missing target values | FAIL | target |
| class distribution, imbalance ratio > 10 | WARN | categorical target |
| feature identical to target | FAIL | target leakage |
| feature with abs(r) > 0.999 to target | WARN | target leakage |
| identical rows across splits | FAIL | split integrity |
| group or id overlap across splits | FAIL | leakage (e.g. subject-level) |
| split fractions differ from manifest by > 0.02 | WARN | splits |
| expected row counts | FAIL | splits |
| time column not strictly increasing | FAIL | time series |
| gaps > 1.5 × expected interval | WARN | time series |
| custom validators (`module:function`) | as returned; FAIL if the validator crashes | any format |

Non-tabular files (images, audio, HDF5, …) get existence and fingerprint checks. Add
custom validators for their domain-specific checks.

## Outputs

`data/validation/<name>.json` (machine-readable), `data/validation/<name>.md` (report),
and `data/validation_report.md` (index).

## The gate

`datasets.require_valid` refuses to run an experiment if the dataset is unregistered,
never validated, FAIL, or changed since validation. The run record stores the dataset's
name, version, fingerprint and validation status.

## Rules

- Never assume data is public because its name is known. Record access conditions.
- Never download or redistribute without verified rights (`redistribution_allowed`).
- Never fill gaps with synthetic samples. Insufficient data is reported as a limitation.
- Raw data is gitignored by default (`data/raw/`). Commit manifests, not data.
