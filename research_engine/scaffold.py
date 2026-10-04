"""Text of every file a new project starts with.

Placeholders use the engine-wide markers so the manuscript audit can find anything a
researcher has not filled in yet.
"""

from __future__ import annotations

from .domains import DomainProfile

RI = "[RESEARCHER INPUT REQUIRED]"

LIT_MATRIX_HEADER = (
    "key,title,authors,year,venue,doi,url,verification_status,research_question,"
    "methods,datasets,baselines,evaluation_protocol,results,limitations,relevance\n"
)


def _md(title: str, body: str) -> str:
    return f"# {title}\n\n{body.strip()}\n"


def render_scaffold(name: str, profile: DomainProfile) -> dict[str, str]:
    metrics = "\n".join(
        f"- `{m.name}` ({m.direction} is better{', ' + m.unit if m.unit else ''})"
        for m in profile.suggested_metrics) or "- (none suggested: define per experiment)"
    checks = ", ".join(profile.dataset_checks)
    extra = "\n".join(f"- {s}" for s in profile.report_sections) or "- (none)"

    files: dict[str, str] = {}
    files["README.md"] = _md(name, f"""
Research project managed by `research_engine`. Domain profile: **{profile.name}**.
{profile.description}

## Status
Run `research status` to rebuild the current status from the files on disk.

## Layout
- `project.yaml`: metadata, research questions, hypotheses, statistics, execution, stopping rules
- `research/`: problem statement, questions, hypotheses, methodology (prose)
- `literature/`: reference registry (`references.yaml`), BibTeX, literature matrix
- `data/`: dataset manifest and validation reports
- `experiments/configs/`: one YAML per experiment (the unit of work)
- `runs/`: immutable run records (`metadata/`) and raw outputs (`raw/`)
- `analysis/`, `reports/`: generated from validated runs only
- `evidence/claims.yaml`: every claim the manuscript may make, linked to its evidence
- `manuscript/`: section sources with `{{{{claim:ID}}}}` markers, builds and audits

## Domain suggestions
Suggested metrics:
{metrics}

Default dataset checks: {checks}

Extra report sections:
{extra}
""")
    files["research/problem_statement.md"] = _md("Problem statement", f"""
## Problem
{RI}

## Motivation
{RI}

## Scope
{RI}

## Assumptions
{RI}

## Constraints
{RI}
""")
    files["research/research_questions.md"] = _md("Research questions", f"""
The machine-readable list lives in `project.yaml` under `research.questions`.
Keep the IDs (RQ1, RQ2, ...) identical in both places.

- RQ1: {RI}
""")
    files["research/hypotheses.md"] = _md("Hypotheses", f"""
The machine-readable list lives in `project.yaml` under `research.hypotheses`.
Every hypothesis must state what result would falsify it.

- H1 (RQ1): {RI}
  - Falsified if: {RI}
""")
    files["research/objectives.md"] = _md("Objectives", f"- {RI}")
    files["research/novelty_assessment.md"] = _md("Novelty assessment", f"""
**Proposed contribution (not yet demonstrated):** {RI}

**Demonstrated contribution:** none yet. A contribution moves here only after it is
supported by verified claims in `evidence/claims.yaml`.

**Literature search backing any novelty statement:** see
`literature/search_strategy.md`. Without a documented and scoped search, novelty may
only be stated as "to our knowledge, within the scope of the search described in ...".
""")
    files["research/methodology.md"] = _md("Methodology", f"""
## Study design
{RI}

## Variables
- Independent: {RI}
- Dependent: {RI}
- Controlled: {RI}

## Evaluation protocol
{RI}

## Statistical plan
{RI}

## Deviations from the plan
Record every deviation in `docs/decisions/decision_log.yaml` (`research decision add`).
""")
    files["research/limitations.md"] = _md("Limitations", f"- {RI}")

    files["literature/search_strategy.md"] = _md("Literature search strategy", f"""
| Field | Value |
|---|---|
| Databases searched | {RI} |
| Query strings | {RI} |
| Date of search | {RI} |
| Inclusion criteria | {RI} |
| Exclusion criteria | {RI} |
| Records screened / included | {RI} |

A research gap may be called new only within the scope documented here.
""")
    files["literature/references.yaml"] = (
        "# Reference registry. Add entries with `research lit add` or `research lit import`.\n"
        "# Only entries with verification.status == verified appear in the manuscript.\n"
        "references: []\n")
    files["literature/references.bib"] = (
        "% Generated from literature/references.yaml by `research lit export`.\n"
        "% Only verified references are written here.\n")
    files["literature/literature_matrix.csv"] = LIT_MATRIX_HEADER
    files["literature/literature_review.md"] = _md("Literature review (draft)", f"""
Generate a skeleton with `research lit review`. Statements about prior work must cite a
verified reference as `[@key]`.

{RI}
""")
    files["literature/research_gap.md"] = _md("Research gap", f"""
**Status: hypothesised (not established).**

{RI}
""")

    files["data/dataset_manifest.yaml"] = """# Dataset manifest. Register datasets with `research data register`.
# Example entry (remove the leading '# ' to use):
# - name: my_dataset
#   version: "1.0"
#   synthetic: false
#   source: {kind: local, location: data/raw/my_dataset, access_verified: true}
#   license: {name: "CC-BY-4.0", url: "https://...", redistribution_allowed: true}
#   files:
#     - {path: data/raw/my_dataset/train.csv, split: train}
#     - {path: data/raw/my_dataset/test.csv, split: test}
#   target: label
#   column_checks:
#     - {column: voltage, unit: V, min: 0, max: 400}
datasets: []
"""
    files["data/data_card.md"] = _md("Data card", f"Generated per dataset by `research data validate`.\n\n{RI}")
    files["data/validation_report.md"] = _md("Dataset validation report",
                                             "Not yet run. Use `research data validate`.")

    files["evidence/claims.yaml"] = "# Claim registry. See docs/HALLUCINATION_PREVENTION.md\nclaims: []\n"
    files["evidence/evidence_index.yaml"] = "# Generated by `research evidence index`.\nindex: []\n"
    files["evidence/source_registry.yaml"] = (
        "# External, non-experimental sources (instrument datasheets, standards, ...).\n"
        "sources: []\n")
    files["experiments/plans/proposals.yaml"] = "proposals: []\n"
    files["experiments/plans/iterations.yaml"] = "iterations: []\n"
    files["experiments/configs/_TEMPLATE.yaml.example"] = EXPERIMENT_TEMPLATE
    files["docs/decisions/decision_log.yaml"] = "decisions: []\n"
    files["approvals/approvals.yaml"] = "approvals: []\n"
    files["tests/README.md"] = _md("Project tests",
                                   "Put tests of your own preprocessing and methods here.")
    files["CLAUDE.md"] = _md(f"Claude Code instructions for {name}", """
This is a `research_engine` project. Read the engine's CLAUDE.md for global rules.

- Rebuild context with `research status` before doing anything else.
- Never type a number into the manuscript: add a claim and use `{{claim:ID}}`.
- Never run `research run --backend kaggle` or any GPU / long run without a recorded
  approval (`research approve ...`) made by the researcher.
- Never edit files under `runs/raw/` or `runs/metadata/`.
""")
    files[".gitignore"] = PROJECT_GITIGNORE
    files[".env.example"] = ENV_EXAMPLE
    return files


EXPERIMENT_TEMPLATE = """# Copy to <ID>.yaml (e.g. EXP-001.yaml) and edit. Validate with `research exp validate`.
id: EXP-001
title: "Baseline: <method> on <dataset>"
type: baseline              # baseline|proposed|ablation|sensitivity|robustness|generalization|efficiency|replication|exploratory|measurement|simulation|other
status: draft
research_questions: [RQ1]
hypotheses: [H1]
rationale: "Why this experiment is needed and which question it answers."
depends_on: []
compare_with: []
dataset: {name: my_dataset, version: "1.0"}
method: {name: my_method, params: {}}
variables:
  independent: [method]
  dependent: [rmse]
  controlled: [dataset version, preprocessing, seeds]
entrypoint:
  # {python} is replaced by the current interpreter; {config} by the snapshot path.
  command: ["{python}", "experiments/scripts/run_method.py"]
  code_files: [experiments/scripts/run_method.py]
parameters: {}
seeds: [0, 1, 2]
metrics:
  - {name: rmse, direction: lower, unit: "", definition: "root-mean-square error on the test split"}
expected_outputs: [metrics.json]
expected_samples: null
compute: {backend: local, device: cpu, estimated_hours: 0.05}
statistics: {test: auto, paired_by: seed}
failure_criteria: ["any seed fails", "metric outside valid range"]
confounders: []
nondeterminism_notes: ""
"""

PROJECT_GITIGNORE = """# Secrets -- never commit
.env
*.env
pat.txt
*.pat
kaggle.json
kaggle_*.json
.kaggle/
*credentials*.json
*secret*
*.pem
*.key

# Generated run artifacts (opt in explicitly if a small artifact must be versioned)
runs/raw/
runs/processed/
runs/checkpoints/
runs/logs/
runs/remote/
manuscript/build/

# Large data
data/raw/
data/external/
*.parquet
*.h5
*.pt
*.ckpt
*.safetensors

# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
"""

ENV_EXAMPLE = """# Copy to .env (which is gitignored) or set these in your shell.
# NEVER put real values in this file -- it is committed.

# Path to a kaggle.json kept OUTSIDE this repository (e.g. C:\\Users\\you\\.kaggle\\kaggle.json)
RP_KAGGLE_CREDENTIALS=
# Alternatively the Kaggle client reads these directly:
KAGGLE_USERNAME=
KAGGLE_KEY=
# Contact e-mail sent to Crossref for polite reference lookups (optional)
RP_CROSSREF_MAILTO=
"""
