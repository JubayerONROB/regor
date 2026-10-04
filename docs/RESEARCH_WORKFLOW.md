# Research workflow

The lifecycle below works for any field. Each step names the command, the files it reads
and writes, and the human decision points (marked **[R]**).

## 0. Initialise

`regor init my_study [--domain D]` creates the project tree, `project.yaml`, templates,
placeholders and Claude Code slash commands. Without `--domain` the generic profile is
used, which assumes nothing about the field.

## 1. Problem definition **[R]**

Write `research/problem_statement.md`, `objectives.md`, `research_questions.md` and
`hypotheses.md`, and mirror the IDs into `project.yaml`:

```yaml
research:
  questions:  [{id: RQ1, text: "..."}]
  hypotheses: [{id: H1, rq: RQ1, statement: "...", falsification: "...", status: proposed}]
```

`research/novelty_assessment.md` keeps the **proposed** contribution apart from the
**demonstrated** one. A contribution counts as demonstrated only once verified claims
support it.

## 2. Literature

`regor lit add|import` adds references, `regor lit verify --all` checks them
against Crossref or arXiv (or a named researcher attests them with `--manual`), and
`regor lit matrix|review|export` produces the matrix, a review skeleton and BibTeX.
Only verified references are exported or citable. A research gap stays "hypothesised"
until `literature/search_strategy.md` documents a scoped search.

## 3. Data

`regor data register` then `regor data validate`. A dataset with a FAIL, or one
whose files changed since validation, blocks every experiment that uses it.
`--allow-unvalidated` overrides the block, but the override is recorded and the
resulting runs are only PROVISIONAL. See DATA_MANAGEMENT.md.

## 4. Methodology and experiment design **[R]**

Write `research/methodology.md`, then one spec per experiment
(`regor exp new ID`). Every spec states its rationale and the RQs and hypotheses it
addresses, and declares metrics with direction, unit, definition and valid range.
Substantial choices are recorded with `regor decision add`. See
EXPERIMENT_PROTOCOL.md.

## 5. Execution

`regor run ID --dry-run` shows the plan: seeds, estimated hours, budget, dataset
gate and approval need. `regor run ID` creates one immutable run record per seed and
executes it locally. For Kaggle, use `--backend kaggle` and later
`regor remote collect`. For bench or field data, use `regor import`.

Approvals **[R]**: `regor approve run ID --backend B --runs N --by NAME`.

## 6. Validation

Validation runs automatically after each run, and on demand with `regor validate`.
See RESULT_VALIDATION.md.

## 7. Analysis

`regor analyze REF --compare A B --metric M [--plot]` writes a comparison summary in
JSON (machine-readable) and Markdown (human-readable), plus figures with provenance
sidecars.

## 8. Reports

`regor report ID|--all` writes a 21-section technical report and a JSON summary per
experiment. Interpretation sections are left for the researcher.

## 9. Evidence

`regor claim add ...` and `regor claim verify`. Claims are the only path from
results to the manuscript.

## 10. Iteration **[R]**

`regor propose`, `regor proposals approve|reject PID --by NAME`, and
`regor loop start|close|review|status`. See ITERATION_LOOP.md.

## 11. Progress

`regor status --write` regenerates `reports/progress_reports/PROGRESS.md`,
`progress.json`, `docs/experiment_history/{dependency_graph,timeline}.md` and the
decision log view. Hypothesis verdicts **[R]**:
`regor hypothesis set H1 --status supported --claims C1 C2 --by NAME`. A
supported or refuted verdict requires verified claims.

## 12. Manuscript

`regor manuscript init|draft|build|audit`. See MANUSCRIPT_WORKFLOW.md and
HALLUCINATION_PREVENTION.md.

## 13. Journal **[R]**

`regor journal init "Name"` creates the profile, which the researcher fills from the
official guidelines. Then `regor journal check slug` and `regor journal export
slug --format latex|markdown|docx|pdf|all`.

## Resuming

Everything above is reconstructible from files. After a restart, run
`regor status --write` and read PROGRESS.md.
