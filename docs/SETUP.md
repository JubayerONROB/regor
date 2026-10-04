# Setup (Windows + VS Code)

## Requirements

- Python 3.10+ (tested with 3.10.7 on Windows 11)
- Git (optional but recommended: runs without a git commit are only PROVISIONAL)
- Optional: matplotlib (figures), `kaggle` CLI (remote runs; ≥ 2.0 for accelerator
  selection), pandoc (DOCX/PDF export), a LaTeX distribution (compiling `.tex` exports)

## Install

```powershell
cd <path-to>\research-pipeline
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\research.exe --version
```

Use an absolute interpreter path (`py -3.10` or `C:\Python310\python.exe`) to create the
venv. If another project's virtual environment is active in the terminal, `python` may
resolve to it.

In Git Bash: `./.venv/Scripts/python.exe -m pytest`.

## VS Code

1. Open the folder, then **Python: Select Interpreter** → `.venv\Scripts\python.exe`.
2. Testing panel: pytest, folder `tests` (configured in `pyproject.toml`).
3. Claude Code: open a research project folder (created with `research init`). Its
   `.claude/commands/rp-*.md` appear as slash commands (`/rp-recon`, `/rp-audit`, …).
   Copy `templates/claude_settings.example.json` to the project's
   `.claude/settings.json` to deny approval and push commands to the assistant.

## Optional: Kaggle

```powershell
.\.venv\Scripts\python.exe -m pip install kaggle
setx RP_KAGGLE_CREDENTIALS "C:\Users\<you>\.kaggle\kaggle.json"   # file stays outside repos
research remote resources
```

Then set `execution.kaggle.enabled: true` in the project. See KAGGLE_INTEGRATION.md.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `no project.yaml in ...` | run inside a project or pass `--project DIR` |
| runs are PROVISIONAL "code version is not pinned" | the project is not a git repo or has no commit: `git init && git add -A && git commit` |
| `dataset ... changed since it was validated` | re-run `research data validate NAME` (or register a new version) |
| `approval required` | the researcher runs `research approve run ID --backend B --runs N --by NAME` |
| `compute budget` blocked | raise `stopping.compute_budget_hours` deliberately, recording a decision |
| `experiment requires a GPU but none was detected` | run on a GPU machine or backend; there is no silent CPU fallback |
| `matplotlib is not installed` | `pip install matplotlib` |
| unicode errors in Windows console | set `PYTHONUTF8=1` |
| claims `needs_review` "provisional runs" | resolve the provisional issues (see `research -v validate`) |
| audit FAIL "unsupported number" | replace the number with `{{claim:ID}}` or annotate it `N [claim:ID]` |
