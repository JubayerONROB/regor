---
description: Kaggle submission (regor workflow)
---

# Kaggle submission

Prepare a remote run.
1. `regor remote resources` reports what the CLI can tell. Quota and GPU type are often unknown; say so.
2. Confirm execution.kaggle in project.yaml (enabled, dataset_sources, accelerator, internet).
3. `regor run <ID> --backend kaggle --dry-run` and show the plan to the researcher.
4. STOP. Only the researcher grants approval (`regor approve run ...`). Never grant it yourself.
5. After approval: `regor run <ID> --backend kaggle`; later `regor remote collect`.
Rules: never print, copy or commit credentials; never assume GPU type, quota or session limits.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
