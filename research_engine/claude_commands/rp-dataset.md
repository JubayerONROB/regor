---
description: Dataset inspection (research_engine workflow)
---

# Dataset inspection

Register and validate data.
1. Confirm source, licence and permitted use with the researcher. Never assume public availability.
2. Write a manifest entry (see the example in data/dataset_manifest.yaml): splits, target, group/id columns, column ranges and units, metadata requirements, known limitations.
3. `research data register --from-yaml ...` then `research data validate NAME`.
4. Explain every FAIL and WARN and propose fixes. Never edit raw data silently; record preprocessing in the manifest.
Rules: no download or redistribution without verified rights; never synthesise samples to fill gaps.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
