# Templates

| File | Use |
|---|---|
| `research_specification.md` | problem, RQs, hypotheses, scope (copy into `research/`) |
| `experiment_plan.md` | plan table before writing specs |
| `../research_engine/scaffold.py` → `experiments/configs/_TEMPLATE.yaml.example` | experiment spec (created in every project) |
| `dataset_manifest_entry.yaml` | `research data register --from-yaml` (measurement example) |
| `claims_examples.yaml` | one example per claim source kind |
| `manuscript_section.md` | marker grammar in context |
| `claude_settings.example.json` | Claude Code permission deny list for a project |
| `../research_engine/claude_commands/*.md` | Claude Code slash commands (installed by `research init`) |

Experiment reports, proposals, progress reports and audit reports are generated, not
templated: see `reports.py`, `iteration.py`, `progress.py` and `manuscript/audit.py`.
