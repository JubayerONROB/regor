# CLAUDE.md: working with regor in Claude Code

This repository holds the research engine (`regor/`). Research projects are
separate directories created with `regor init`, and each gets its own short CLAUDE.md
and slash commands in `.claude/commands/` (`/regor-recon`, `/regor-plan`, `/regor-experiment`,
`/regor-analyze`, `/regor-audit`, …).

## Resume an interrupted session

1. `regor --project <dir> status --write`, then read `reports/progress_reports/PROGRESS.md`.
2. Read `project.yaml`, `docs/decisions/DECISIONS.md` and `experiments/plans/proposals.yaml`.
3. Continue from "Next recommended steps". **Never rely on conversation memory** for
   results, decisions or approvals. The files are the record.

## Architecture in one paragraph

`project.py` (layout, config) → `datasets.py` (register, validate, fingerprint) →
`experiments.py` (specs, immutable run records) → `engine.py` (preflight gates, dispatch)
→ `executors/` (local, kaggle, manual) → `results.py` (validation status) →
`analysis/` (stats, compare, viz) → `reports.py` → `evidence.py` and `literature.py`
(claims, references) → `iteration.py` (proposals, stopping rules) → `manuscript/` (draft,
render, audit, journal). See docs/ARCHITECTURE.md.

## Important commands

```
regor init NAME [--domain D]          regor check
regor data register|validate|list     regor exp new|validate|list
regor run ID [--dry-run] [--seeds ..] regor validate
regor analyze REF --compare X --metric M [--plot]
regor report --all                    regor claim add|verify|list
regor lit add|import|verify|export    regor propose / proposals list
regor loop status                     regor manuscript draft|build|audit
regor journal init|check|export       regor security scan [PATH]
```

## Hard rules

1. **Never fabricate** results, citations, DOIs, datasets, sources, declarations or
   author contributions. If evidence is missing, write the placeholder
   (`[NEEDS VERIFIED RESULT: ...]`, `[REFERENCE NOT VERIFIED]`,
   `[RESEARCHER INPUT REQUIRED]`, `[INSUFFICIENT EVIDENCE]`).
2. **Never type a number into a manuscript section.** Add a claim and use
   `{{claim:ID}}`, or an annotated literal such as `0.153 [claim:C001]`, or a
   `{{spec:...}}`/`{{dataset:...}}`/`{{project:...}}` marker.
3. **Never grant approvals** (`regor approve`) or approve proposals on the researcher's
   behalf. Remote, GPU and long runs need a researcher-granted, single-use approval.
4. **Never edit `runs/raw/` or `runs/metadata/`.** Raw evidence is checksummed, and
   editing it makes runs INVALID.
5. **Never present synthetic, mocked, planned or simulated runs as executed science.**
   Mock remote runs validate as INVALID by design.
6. **Never resolve conflicting results silently.** Contradictions are recorded on both
   claims, and a claim is superseded with a reason rather than deleted.
7. **Never change** a research question, dataset, methodology or evaluation protocol
   without the researcher's approval. Record the change with `regor decision add`.
8. **Never claim** statistical significance without an analysis, generalisation beyond
   the evaluated conditions, or novelty without a documented, scoped literature search.
9. Inconclusive is inconclusive. Failed is failed. Report both.

## Security rules

- Never print, copy, commit or log credentials (`pat.txt`, `kaggle*.json`, `.env`,
  tokens). Credentials live outside repositories. The Kaggle adapter reads a path from
  `$REGOR_KAGGLE_CREDENTIALS` and passes the values only to the `kaggle` subprocess.
- Before every commit: `regor security scan .`, then review `git status` and
  `git diff --cached --stat`. Stage explicit paths. Never `git add -A` in a repository
  that holds data or credentials.
- Do not read files in other repositories unless the researcher asks, and never modify
  them.

## Configuration conventions

- IDs: `RQ1`, `H1`, `EXP-...` (any `[A-Za-z][A-Za-z0-9_.-]*`), claims `C...`, proposals
  `P-NNN`, decisions `D-NNN`.
- All configs are validated against `regor/schemas/*.schema.json`
  (`regor check`).
- Experiment scripts use `regor.runtime` (`load_context`, `write_metrics`).

## Experiment lifecycle

spec (draft) → `exp validate` → `run --dry-run` → approval if needed → `run` → automatic
validation → `analyze` → `report` → claims → `claim verify` → `propose` → researcher
decision → next iteration.

## Evidence and writing

A sentence in the manuscript is acceptable only if each number traces to a verified
claim or configuration, each prior-work statement cites a verified reference, and each
comparative or significance statement is backed by a verified comparative or
statistical claim. Run `regor manuscript audit` after every edit. A manuscript with
any FAIL is not submission-ready, and even a PASS needs the human checklist.

## Environment notes (Windows)

- On Windows, write LaTeX and regex-heavy files with an editor or file tool, not
  shell heredocs. Backslashes and quotes get mangled without any error.
- Use the repository's own `.venv`. Do not install into other projects' environments.
