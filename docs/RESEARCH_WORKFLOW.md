# Research workflow

The lifecycle below works for any field. Each step names the command, the files it reads
and writes, and the human decision points (marked **[R]**).

## 0. Initialise

`research init my_study [--domain D]` creates the project tree, `project.yaml`, templates,
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

`research lit add|import` adds references, `research lit verify --all` checks them
against Crossref or arXiv (or a named researcher attests them with `--manual`), and
`research lit matrix|review|export` produces the matrix, a review skeleton and BibTeX.
Only verified references are exported or citable. A research gap stays "hypothesised"
until `literature/search_strategy.md` documents a scoped search.

## 3. Data

`research data register` then `research data validate`. A dataset with a FAIL, or one
whose files changed since validation, blocks every experiment that uses it.
`--allow-unvalidated` overrides the block, but the override is recorded and the
resulting runs are only PROVISIONAL. See DATA_MANAGEMENT.md.

## 4. Methodology and experiment design **[R]**

Write `research/methodology.md`, then one spec per experiment
(`research exp new ID`). Every spec states its rationale and the RQs and hypotheses it
addresses, and declares metrics with direction, unit, definition and valid range.
Substantial choices are recorded with `research decision add`. See
EXPERIMENT_PROTOCOL.md.

## 5. Execution

`research run ID --dry-run` shows the plan: seeds, estimated hours, budget, dataset
gate and approval need. `research run ID` creates one immutable run record per seed and
executes it locally. For Kaggle, use `--backend kaggle` and later
`research remote collect`. For bench or field data, use `research import`.

Approvals **[R]**: `research approve run ID --backend B --runs N --by NAME`.

## 6. Validation

Validation runs automatically after each run, and on demand with `research validate`.
See RESULT_VALIDATION.md.

## 7. Analysis

`research analyze REF --compare A B --metric M [--plot]` writes a comparison summary in
JSON (machine-readable) and Markdown (human-readable), plus figures with provenance
sidecars.

## 8. Reports

`research report ID|--all` writes a 21-section technical report and a JSON summary per
experiment. Interpretation sections are left for the researcher.

## 9. Evidence

`research claim add ...` and `research claim verify`. Claims are the only path from
results to the manuscript.

## 10. Iteration **[R]**

`research propose`, `research proposals approve|reject PID --by NAME`, and
`research loop start|close|review|status`. See ITERATION_LOOP.md.

## 11. Progress

`research status --write` regenerates `reports/progress_reports/PROGRESS.md`,
`progress.json`, `docs/experiment_history/{dependency_graph,timeline}.md` and the
decision log view. Hypothesis verdicts **[R]**:
`research hypothesis set H1 --status supported --claims C1 C2 --by NAME`. A
supported or refuted verdict requires verified claims.

## 12. Manuscript

`research manuscript init|draft|build|audit`. See MANUSCRIPT_WORKFLOW.md and
HALLUCINATION_PREVENTION.md.

## 13. Journal **[R]**

`research journal init "Name"` creates the profile, which the researcher fills from the
official guidelines. Then `research journal check slug` and `research journal export
slug --format latex|markdown|docx|pdf|all`.

## Resuming

Everything above is reconstructible from files. After a restart, run
`research status --write` and read PROGRESS.md.
