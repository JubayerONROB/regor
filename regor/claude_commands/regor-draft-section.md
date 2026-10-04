---
description: Manuscript section drafting (regor workflow)
---

# Manuscript section drafting

Draft a manuscript section.
1. `regor claim verify`. Only verified claims may carry results.
2. `regor manuscript draft --section <name>`, then write prose AROUND the markers: {{claim:ID}}, {{claimtext:ID}}, {{spec:EXP:path}}, {{dataset:NAME:path}}, {{project:path}}, {{table:...}}, {{figure:...}}, citations [@key].
3. Never type a number unless it is a marker or an annotated literal such as `0.153 [claim:C001]`.
4. `regor manuscript audit` and fix every FAIL.
Rules: formal, precise, non-promotional; keep prior work, method, measured findings and interpretation distinct; never fabricate declarations.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
