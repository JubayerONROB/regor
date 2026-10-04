# Hallucination prevention

An LLM assistant (or a tired human) can produce plausible numbers, citations and
conclusions that are not supported. This pipeline makes that **structurally visible**
rather than relying on discipline. The mechanisms, from data to manuscript:

## 1. Results cannot be typed

- A manuscript number must be a `{{claim:ID}}` marker, an annotated literal
  (`0.153 [claim:C001]`), or a config/dataset/project marker.
- Any other number in a results-bearing section (`manuscript.results_sections`) is a
  **FAIL** ("unsupported number"). In other sections it is a WARNING. Years, list
  numbering, headings and identifiers (`RQ1`, `Fig. 2`, `EXP-3`, `window-5`) are
  excluded.

## 2. Claims are verified by recomputation

`regor claim verify` recomputes each claim from its declared source:

| Source kind | Verification |
|---|---|
| `runs_metric` | statistic over **VALIDATED** runs of the experiment (provisional only → needs_review; none → failed) |
| `analysis` | value at a JSON path inside an analysis summary (hash-tracked) |
| `artifact` | the file exists (checksum recorded); optional JSON path |
| `literature` | every cited reference is verified |
| `researcher` | always `needs_review`: attestations cannot be machine-verified |

Additional rules:

- A `stated_value` that differs from the recomputed value beyond the tolerance → failed.
- A comparative or statistical claim whose text asserts superiority or significance
  while the linked analysis is not significant after adjustment → needs_review. If no
  analysis is linked at all → needs_review.
- Novelty claims are always needs_review.
- Two claims with the same source but different stated values are cross-flagged as
  contradictions and kept.

## 3. Citations must exist and match

Only references verified against Crossref or arXiv metadata (title similarity ≥ 0.9,
year, first author) or attested by a named researcher with an evidence URL are
citable. Unregistered keys → FAIL ("possibly nonexistent"). Unverified or mismatched →
FAIL. Sentences about prior work without a citation → WARNING. The engine never creates
a reference to fill a gap.

## 4. Methods must match the implementation

The audit FAILs when the current spec differs from what the validated runs executed. It
warns when validated runs span different configurations or code checksums (unless the
decision log documents the change). It FAILs compared experiments that use different
datasets or metric definitions. It warns on ablations that change more than one
setting. Configured values enter the text only through `{{spec:...}}`.

## 5. Language guards

| Pattern | Status |
|---|---|
| "novel", "first to …" without a novelty claim | FAIL (WARNING if a novelty claim is present) |
| "significant(ly)" without a verified statistical claim in the sentence | FAIL in results sections, WARNING elsewhere |
| "outperforms", "better than", "superior", … without any claim | FAIL; WARNING if backed only by non-comparative claims |
| "prove", "state-of-the-art", "guarantee", "definitively", "generalize", promotional words | WARNING |

## 6. Tables and figures are generated

Tables come from hashed comparison summaries (editing a summary → FAIL). Figures need
provenance sidecars listing experiments, run IDs, the metric definition and the source
summary hash. Every individual run is drawn next to the aggregate, and there are no bar
charts with truncated baselines.

## 7. Nothing incomplete passes

Any placeholder, failed claim, superseded claim, unresolved marker or missing configured
section → FAIL, and `submission_ready: false`.

## 8. Synthetic and mock data are labelled

Synthetic datasets carry a banner in validation reports, experiment reports and the
setup draft. Mock remote runs validate as INVALID.

## What this does **not** guarantee

The audit checks traceability and consistency, not truth. It cannot tell whether a
correctly traced number came from a flawed experiment, whether a verified reference
actually says what the sentence claims, or whether the interpretation is sound. Every
audit report therefore ends with a human-review checklist, and the tests in
`tests/test_manuscript_audit.py` show what it does catch: unsupported numbers, literal
mismatches, unknown or failed claims, nonexistent and unverified citations,
comparative, significance and novelty wording, placeholders, tampered table sources,
spec drift and unfair comparisons.
