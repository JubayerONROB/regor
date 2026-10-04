# Manuscript workflow

## Sources, not outputs

You write `manuscript/sections/NN_<section>.md` (the order and names come from
`project.yaml → manuscript.sections`). `research manuscript build` resolves markers into
`manuscript/build/manuscript.md` and `build_manifest.json`, which records every claim
value, config value, table hash and citation used.

## Marker grammar

| Marker | Renders as | Audit |
|---|---|---|
| `{{claim:C001}}` | verified value of C001 (+ unit) | FAIL if C001 is unknown, unverified, failed or superseded; WARNING if needs_review or contradicted |
| `{{claimtext:C001}}` | the registered claim text | same |
| `0.153 [claim:C001]` | `0.153` | FAIL if the literal does not match C001 at its written precision (percent-aware) |
| `{{spec:EXP-1:method.params.window}}` | value from the experiment config | FAIL if the path does not resolve |
| `{{dataset:NAME:version}}` | value from the dataset manifest | FAIL if unresolved |
| `{{project:statistics.alpha}}` | value from project.yaml | FAIL if unresolved |
| `{{table:analysis/comparisons/X.json}}` | generated table (n, mean, SD, CI, test, adjusted p, effect size) | FAIL if the summary was edited after generation (hash) |
| `{{figure:analysis/visualizations/X.png\|Caption}}` | image | FAIL without a provenance sidecar; WARNING if the source summary changed |
| `[@key]`, `[@a; @b]` | `[key]` / `\cite{key}` | FAIL if the key is unregistered or unverified |

Placeholders: `[RESEARCHER INPUT REQUIRED]`, `[NEEDS VERIFIED RESULT: ...]`,
`[REFERENCE NOT VERIFIED]`, `[INSUFFICIENT EVIDENCE]`. Any placeholder makes the audit
FAIL.

## Commands

```bash
research manuscript init      # skeletons for every configured section (never overwrites)
research manuscript draft     # evidence-driven drafts: results, methodology, experimental_setup,
                              # related_work, limitations, declarations (configured ones only)
research manuscript build     # resolve markers -> manuscript/build/manuscript.md
research manuscript audit     # PASS / WARNING / FAIL + claim-to-evidence table + human checklist
```

The drafter writes a section file only if it is still the untouched skeleton. Otherwise
it writes `<section>.generated.md` next to it for a manual merge, so researcher edits are
never overwritten.

## What the drafter does and does not write

It writes structure, markers for verified claims, config-derived values, generated tables,
figures with provenance, and explicit placeholders (for example
`[INSUFFICIENT EVIDENCE] C003 (needs_review): ...`).

It never writes typed numbers, invented citations, interpretations presented as findings,
or declarations (funding, conflicts, ethics, data availability, author contributions,
acknowledgments, generative-AI use). Declarations come only from
`project.yaml → manuscript.declarations`, which the researcher fills.

## Results that conflict

Conflicting claims are flagged on both claims (`contradicted_by`). The audit warns
wherever either is used. Resolve the conflict by investigation, and record the outcome
by superseding the wrong claim with a reason (`research claim supersede`), never by
deleting it.

## Journal formatting

The scientific source stays venue-independent. `research journal export SLUG` produces:

- `manuscript.md` (copy of the build)
- `manuscript.tex` + `references.bib`: a generic article template from a conservative
  built-in Markdown→LaTeX converter (headings, emphasis, lists, pipe tables, images,
  citations). Replace the template with the journal's official class.
- `manuscript.docx` / `.pdf` **only if pandoc is installed**. Otherwise it says
  "SKIPPED".
- `cover_letter_draft.md` with placeholders

`research journal check SLUG` compares the build against the researcher-filled profile:
words, abstract words, figures, tables, keywords, required sections and statements,
placeholders, and audit status. Unknown limits are shown as `[?]`. The checklist never
claims acceptance or suitability.
