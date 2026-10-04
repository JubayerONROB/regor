# Roadmap: what exists, what is partial, what is planned

Legend: ✅ implemented and covered by automated tests · 🟡 implemented, limited or not
tested end to end · ⬜ planned / not implemented

## Implemented

| Capability | Status | Notes |
|---|---|---|
| Project init (with/without domain), layout, scaffold, slash commands | ✅ | never overwrites existing files |
| Config schemas + validation (`regor check`) | ✅ | project, experiment, manifest, claims, run record |
| 14 built-in domain profiles + `domain.yaml` override | ✅ | data-only adapters |
| Dataset registration, fingerprints, generic and measurement checks, leakage and split integrity, time continuity, custom validators, gate | ✅ | CSV/TSV deep checks; other formats fingerprint + custom |
| Experiment specs with cross-reference checks; config identity hash | ✅ | |
| Immutable run records, never overwritten; provenance capture | ✅ | |
| Preflight gates: dataset, GPU, budget, approvals | ✅ | |
| Local executor: timeout, cancellation, parallel seeds, resume link | ✅ / 🟡 | Ctrl+C path implemented but not covered by an automated test |
| Manual import of external measurements | ✅ | |
| Kaggle adapter: packaging, secret scan, retry, poll, collect | ✅ | mock-tested; CPU and GPU kernels live-verified on Kaggle (2026-10-04) |
| Result validation (4 statuses, tamper detection, sample counts, mock detection, seed-ignored detection) | ✅ | |
| Statistics: descriptive, t/bootstrap CIs, Welch/Student/paired t, Mann-Whitney, Wilcoxon, permutation, effect sizes, Holm/Bonferroni, assumption checks | ✅ | |
| Comparisons over validated runs with exclusion listing; figures with provenance | ✅ | |
| 21-section experiment reports + JSON summaries | ✅ | |
| Claims registry, recomputation, contradictions, evidence index | ✅ | |
| Literature registry, Crossref/arXiv verification, manual attestation, BibTeX, matrix, review skeleton | ✅ (mocked HTTP) | live lookups not exercised by tests |
| Proposals (10 rules), ranking, dedupe, decisions, iterations, stopping criteria, review checkpoints | ✅ | |
| Status reconstruction, PROGRESS.md, decision log, dependency graph, timeline | ✅ | |
| Manuscript init/draft/build with marker grammar | ✅ | |
| Manuscript audit (numbers, claims, references, methodology, language, tables, figures, placeholders) | ✅ | |
| Journal profile, checklist, Markdown/LaTeX export, cover-letter draft | ✅ | |
| Secret scanner | ✅ | |
| Synthetic end-to-end demo | ✅ | |

## Partial

| Capability | Gap |
|---|---|
| Real Kaggle execution (`CliKaggleClient`) | success path live-verified (CPU + GPU kernels); accelerator-type selection (CLI 2.x) and live failure paths not verified; quota not exposed by the CLI |
| DOCX/PDF export | requires pandoc; skipped (and reported) otherwise |
| LaTeX export | generic article template; journal classes must be applied manually |
| Methodology audit | compares specs vs runs, datasets and metric definitions, and ablation isolation; does **not** read source code to confirm a prose description matches it |
| Reference audit | verifies existence and metadata; cannot check that a paper supports the sentence citing it |
| Resource-aware scheduling | GPU presence check and concurrency limit only; no memory or VRAM scheduling |
| Non-tabular dataset checks | fingerprint + user-supplied custom validators |
| Power estimate in proposals | normal approximation, labelled indicative |

## Planned

- ⬜ Batch several seeds into one Kaggle kernel; remote cancellation
- ⬜ Other remote backends (SLURM, cloud VMs), same Executor interface
- ⬜ Mixed-effects or hierarchical models for nested designs; Bayesian alternatives
- ⬜ HTML rendering of reports
- ⬜ Semantic search over the literature matrix (still restricted to verified references)
- ⬜ Pre-commit hook that runs `regor security scan` automatically
- ⬜ Journal profile library (only with fields verified from official guidelines)
