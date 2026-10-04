---
description: Project reconnaissance (regor workflow)
---

# Project reconnaissance

Rebuild context before doing anything.
1. Run `regor status --write` and read reports/progress_reports/PROGRESS.md.
2. Read project.yaml (questions, hypotheses, statistics, stopping rules) and docs/decisions/DECISIONS.md.
3. List experiments (`regor exp list`) and runs (`regor runs list`).
4. Summarise what is validated, what failed, what is pending, open proposals and audit status.
Rules: do not rely on conversation memory; cite files for every statement; change nothing.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
