---
description: Experiment design (research_engine workflow)
---

# Experiment design

Create experiments/configs/<ID>.yaml.
1. `research exp new <ID> --title ... --type ...`, then fill: rationale (which RQ/H and why), dataset, method, entrypoint and code_files, seeds, metrics (direction, unit, definition, valid_range), expected_outputs, expected_samples, compute estimate, statistics plan, failure criteria.
2. Write the script with research_engine.runtime (load_context / write_metrics).
3. `research exp validate <ID>` and `research run <ID> --dry-run`.
Rules: one variable per ablation; identical data and metric definitions for compared experiments.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
