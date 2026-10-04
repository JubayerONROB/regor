---
description: Claim verification (research_engine workflow)
---

# Claim verification

Maintain the evidence registry.
1. Register a claim for every statement the manuscript needs (`research claim add ...`), pointing at runs, an analysis JSON path, an artifact, or verified references.
2. `research claim verify`; investigate failed and needs_review claims and contradictions.
Rules: never resolve a contradiction by deleting the inconvenient claim; supersede it with a reason.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
