# Experiment plan: <study>

One row per experiment; each becomes experiments/configs/<ID>.yaml.

| ID | Type | RQ / H | Why needed | Independent var. | Controlled | Dataset (version, split) | Metrics (direction, unit) | Seeds | Test | Est. hours | Depends on |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EXP-BASE | baseline | RQ1/H1 | reference point | method | data, preprocessing, seeds | | | | paired by seed | | – |
| EXP-PROP | proposed | RQ1/H1 | tests H1 | method | same as baseline | | | | | | EXP-BASE |
| EXP-ABL1 | ablation | RQ2 | isolates component X | component X only | everything else | | | | | | EXP-PROP |

## Sample size
Minimum replicates (project.yaml statistics.min_replicates): __. Justification: [RESEARCHER INPUT REQUIRED]

## Confounders and how they are controlled
- [RESEARCHER INPUT REQUIRED]

## Failure criteria (decided before running)
- [RESEARCHER INPUT REQUIRED]

## Reproducibility requirements
- Seeds, pinned code commit, dataset fingerprint, environment recorded automatically.
- Known nondeterminism: [RESEARCHER INPUT REQUIRED]

## Approval
Methodological decisions recorded as D-___ in docs/decisions/decision_log.yaml.
