# Testing

## Running

```powershell
.\.venv\Scripts\python.exe -m pytest            # all tests (about 5 minutes on a laptop)
.\.venv\Scripts\python.exe -m pytest tests\test_manuscript_audit.py -v
python examples\demo_synthetic\run_demo.py       # end-to-end demonstration
```

The tests need **no network, no GPU, no paid service and no credentials**:

- the Kaggle adapter is tested with `MockKaggleClient`, and the CLI client only for
  credential handling (with a fake key built at runtime) and missing-executable errors;
- reference verification uses an injected fake HTTP fetcher with artificial fixture
  references, which are never real literature;
- every test project is created in a temporary directory with synthetic data, and its
  own git repository so that runs are code-pinned;
- token-shaped strings in security tests are assembled at runtime, so the repository
  contains no secret-like literals.

## Actual results (recorded 2026-10-04)

Environment: Windows 11, Python 3.10.7, numpy 2.2.6, scipy 1.15.3, PyYAML 6.0.3,
jsonschema 4.26.0, matplotlib 3.10.9, pytest 9.1.1.

```
91 passed in 360.25s (0:06:00)
```

(An earlier run of the same suite took 278 s. Duration varies with machine load: most
time goes to subprocess launches and git commits in fixtures.)

| File | Tests | Covers |
|---|---|---|
| `test_project_config.py` | 9 | init with or without domain, no-overwrite, unknown domain, custom `domain.yaml`, schema error collection, project discovery, CLI init/check/status/exp new, clean CLI errors |
| `test_datasets.py` | 10 | passing dataset, split leakage, group leakage, ranges, units, missing values, target leakage, metadata requirements, licence and access warnings, missing files and the gate, changed data needs re-validation, duplicate registration, custom and broken validators, time continuity |
| `test_engine_local.py` | 17 | dry run creates nothing, provenance, never-overwrite, **tampered raw output → INVALID**, failures recorded without stopping the queue, missing/NaN/out-of-range metrics, sample-count mismatch, ignored-seed detection, timeout, GPU gate, budget gate, single-use config-bound approvals, unvalidated dataset override, immutable fields, manual import |
| `test_kaggle_mock.py` | 8 | approval required, packaging and metadata, **mock runs validate INVALID**, remote failure, polling until done, push retry and exhaustion, **secret in code blocks the push**, credentials only in the child env, redaction, missing CLI |
| `test_stats.py` | 11 | describe/CI vs scipy, Welch and paired t vs scipy, auto selection with rationale and assumptions, no test with n<3, small-n Wilcoxon warning, permutation, Holm/Bonferroni, bootstrap determinism |
| `test_evidence_analysis.py` | 5 | comparisons use only validated runs and list exclusions, figure provenance, claim recomputation, stated-value mismatch, significance guard, missing runs, unverified literature, novelty review, contradictions, superseded claims, no "0.0000" rendering |
| `test_literature.py` | 8 | Crossref match, mismatch, nonexistent DOI, network failure stays unverified, no identifier needs manual verification, arXiv, BibTeX import and verified-only export, matrix, review skeleton, key validation |
| `test_manuscript_audit.py` | 13 | clean manuscript passes and builds; **deliberately introduced** unsupported numbers, literal mismatches, unknown and failed claims, nonexistent and unverified citations, comparative, novelty and significance wording, uncited prior work, placeholders, tampered table source, spec drift, unfair comparison, missing section, unresolved config references are all detected; journal check and LaTeX export |
| `test_iteration_progress.py` | 6 | proposal rules and fields, dedupe, inconclusive-comparison proposals, decisions, iteration start/close, stopping and review checkpoints, hypothesis verdicts need verified claims, 21-section report lists failures, status rebuilt from files in a fresh process |
| `test_security.py` | 4 | token patterns detected without echoing them, sensitive filenames, `.env.example` allowed, opt-out marker, generic assignments |

## Demonstration run (recorded 2026-10-04)

`examples/demo_synthetic/run_demo.py` exited 0:

- dataset `demo_signals`: PASS
- 15 local runs (3 experiments × 5 seeds): all VALIDATED
- 1 mock Kaggle run: blocked before approval; after the demo approval it was SUBMITTED,
  then COMPLETED / **INVALID** (mock, as designed)
- 7 claims: all verified by recomputation
- manuscript audit: **FAIL** (16 placeholder FAILs for title, keywords, introduction,
  figure captions, discussion, conclusion and declarations, which need a human; 69 PASS;
  7 WARNING for unsupplied declarations). This is the correct outcome for an unfinished
  manuscript.
- journal checklist: profile not verified and limits unknown, reported as `[?]`

## Not covered by automated tests

- Live Kaggle API calls (`CliKaggleClient.push/status/output` against real Kaggle)
- Live Crossref and arXiv lookups
- pandoc-based DOCX/PDF export (skipped when pandoc is absent)
- Ctrl+C cancellation of a running local batch (implemented, not automated)
- GPU execution (no GPU code path in the engine itself; the GPU gate is tested by monkeypatching)
