---
description: Experiment design (regor workflow)
---

# Experiment design

Create experiments/configs/<ID>.yaml.
1. `regor exp new <ID> --title ... --type ...`, then fill: rationale (which RQ/H and why), dataset, method, entrypoint and code_files, seeds, metrics (direction, unit, definition, valid_range), expected_outputs, expected_samples, compute estimate, statistics plan, failure criteria.
2. Write the script with regor.runtime (load_context / write_metrics).
3. `regor exp validate <ID>` and `regor run <ID> --dry-run`.
Rules: one variable per ablation; identical data and metric definitions for compared experiments.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
