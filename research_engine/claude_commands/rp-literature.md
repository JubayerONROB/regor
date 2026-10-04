---
description: Literature organisation (research_engine workflow)
---

# Literature organisation

Organise references.
1. Add references the researcher supplies (`research lit add` / `research lit import file.bib`).
2. Verify them: `research lit verify --all`. For entries without a DOI or arXiv id, ask the researcher for manual verification with an evidence URL.
3. Fill the matrix fields (methods, datasets, results as reported, limitations, relevance), then `research lit matrix` and `research lit review`.
Rules: NEVER invent a paper, author, DOI, venue, year or result. An unverifiable reference stays unverified and is excluded. Research gaps stay "hypothesised" in literature/research_gap.md until a documented search supports them.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
