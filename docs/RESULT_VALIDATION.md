# Result validation

Raw evidence, processed results, derived statistics and interpretation are kept apart:

| Layer | Location | Who writes it |
|---|---|---|
| Raw evidence | `runs/raw/<run_id>/` | the experiment script or the import (never edited afterwards) |
| Run record | `runs/metadata/<run_id>.json` | engine (identity immutable; bookkeeping only) |
| Derived statistics | `analysis/comparisons/*.json` (hashed) | `research analyze` |
| Interpretation | report sections marked [INTERPRETATION], manuscript prose | researcher |

## Validation status

| Status | Meaning | Usable for claims |
|---|---|---|
| VALIDATED | all checks passed | yes |
| PROVISIONAL | usable only after review | no (claims become needs_review) |
| INCOMPLETE | missing outputs or metrics; cancelled, timed out or still running | no |
| INVALID | failed, tampered, identity mismatch, non-finite or out-of-range, wrong sample count, mock | no |

## Checks (results.py)

| Check | Outcome on failure |
|---|---|
| config snapshot hash equals recorded `config_sha256` | INVALID |
| snapshot file equals the record's snapshot | INVALID |
| experiment id consistency | INVALID |
| mock remote execution | INVALID |
| execution FAILED | INVALID |
| CANCELLED / TIMED_OUT / still running | INCOMPLETE |
| recorded output deleted or modified (SHA-256) | INVALID |
| files added after the run | PROVISIONAL |
| expected outputs present | INCOMPLETE |
| metrics.json readable | INVALID |
| every declared metric present | INCOMPLETE |
| declared metrics numeric and finite | INVALID |
| declared `valid_range` | INVALID |
| `expected_samples` equals `n_samples` | INVALID (INCOMPLETE if not reported) |
| dataset validation overridden | PROVISIONAL |
| dataset no longer registered | PROVISIONAL |
| no git commit recorded | PROVISIONAL |
| identical metrics for different seeds with the same config | PROVISIONAL (seed probably ignored) |
| dirty working tree, dataset changed later, synthetic data, manual import | INFO |

Re-validation (`research validate`) is safe at any time. It reads raw files and updates
only the record's `validation` field.

## Rules

- Invalid and incomplete runs remain in the registry and are listed in every report and
  comparison summary ("Excluded runs").
- Comparative claims use VALIDATED runs only (PROVISIONAL needs an explicit
  `--allow-provisional`, which is recorded in the summary).
- A failed experiment is reported as failed. Negative results are results.
