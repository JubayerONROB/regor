---
description: Research planning (regor workflow)
---

# Research planning

Turn the researcher's idea into a plan.
1. Draft research/problem_statement.md, objectives.md, research_questions.md, hypotheses.md.
2. Mirror RQ and H ids into project.yaml (research.questions / research.hypotheses); every hypothesis needs a falsification criterion.
3. Separate the PROPOSED contribution from anything demonstrated (research/novelty_assessment.md).
4. Run `regor check`.
Rules: no novelty claim without a documented search; leave [RESEARCHER INPUT REQUIRED] where only the researcher can decide; ask before changing an existing RQ or hypothesis and log it with `regor decision add`.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
