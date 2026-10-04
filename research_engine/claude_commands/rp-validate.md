---
description: Result validation (research_engine workflow)
---

# Result validation

Validate results.
1. `research -v validate` and read every non-VALIDATED issue.
2. Explain the causes (failed execution, modified outputs, missing metrics, sample mismatch, unpinned code, mock runs).
3. Propose remedies. Never edit raw outputs; never relabel a failed run.
Rules: invalid and incomplete runs stay in the registry and are reported as such.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
