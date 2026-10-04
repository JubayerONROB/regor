# research-pipeline

**A tool that helps you run experiments carefully and write up only what your results
actually show.**

`research-pipeline` is a free, open-source command-line tool for researchers, students
and engineers. It keeps an experiment honest from the first idea to the final paper. It
records exactly what you ran, checks whether each result can be trusted, and runs the
statistics properly. When you write your paper, it checks that every number and claim
traces back to real evidence.

It works in any field that produces measurable results: machine learning, electrical
engineering, signal processing, biomedical engineering, physics, materials science,
and others.

> **Project status:** early (version 0.1). All 91 automated tests pass. Running
> experiments on Kaggle is implemented but has only been tested with a simulated
> ("mock") Kaggle connection, not the real service. See [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Why does this exist?

Research goes wrong in quiet, ordinary ways, usually not through fraud:

- You re-run an experiment and the new results overwrite the old ones. Now you can't
  tell which number came from which version of your code.
- A result that looked great came from a run that silently crashed halfway, used the
  wrong data, or accidentally let test data leak into training.
- A number gets copied into a paper by hand, then the experiment is re-run and the paper
  is never updated.
- Two methods are compared with an unsuitable statistical test, or on slightly different
  data, and "better" is claimed when the difference could be chance.
- A citation is wrong, or does not exist. This is a growing risk when AI writing
  assistants help draft text.
- Weeks later, nobody remembers why a decision was made, or which runs failed and were
  quietly left out.

This tool turns good practice into automatic checks so these mistakes are hard to make
and easy to spot. It is especially useful if you work with an AI coding assistant (such
as Claude Code). The assistant can do the tedious work, while the tool ensures that
nothing it writes can claim more than the evidence supports.

---

## What it does, in plain terms

Think of it as a careful lab notebook combined with a strict proofreader.

| Stage | What the tool does for you |
|---|---|
| **1. Plan** | Creates a tidy folder for your study, with places to write your research questions and hypotheses, including what result would prove each hypothesis wrong. |
| **2. Check your data** | Registers your dataset and inspects it for problems: missing values, duplicates, impossible values (e.g. a voltage outside the sensor's range), gaps in time series, and *leakage*, where the same data appears in both training and test sets. Experiments won't run on data that failed its checks. |
| **3. Run experiments** | Runs your experiment once per random seed and keeps a permanent record of every run: settings, code version, data fingerprint, computer used, time taken and outputs. **Nothing is ever overwritten.** It can run on your own computer, on Kaggle (free cloud GPUs), or record measurements you took by hand on a lab bench. |
| **4. Check every result** | Marks each run as **VALIDATED**, **PROVISIONAL**, **INCOMPLETE** or **INVALID**. It catches crashed runs, missing outputs, "not a number" values, wrong sample counts, results whose files were edited afterwards, and code that ignored its random seed. |
| **5. Analyse** | Compares experiments with appropriate statistics. It checks the assumptions behind each test, explains why it chose that test, and reports effect sizes, confidence intervals and corrections for multiple comparisons. It also tells you plainly when a difference is *not* significant. |
| **6. Report** | Writes a detailed technical report for each experiment, including the failed runs. Places where a human must interpret the results are clearly marked. |
| **7. Suggest next steps** | Reads your results and proposes follow-up experiments: "you only have 2 runs, you need at least 3", "this comparison is inconclusive", "your new method has no baseline to compare against". **You** approve or reject each one. |
| **8. Write the paper** | Helps draft paper sections in which numbers are inserted automatically from verified results, never typed by hand. |
| **9. Audit the paper** | Checks the manuscript line by line. It flags typed numbers that come from nowhere, numbers that don't match the data, citations that can't be verified, words like "significantly" or "novel" without supporting evidence, and unfinished placeholders. It gives a clear **PASS / WARNING / FAIL**, plus a checklist for human review. |
| **10. Prepare for a journal** | Builds a submission checklist from the journal's guidelines (which you supply) and exports Markdown or LaTeX files. |

At any point, `research status` rebuilds a full summary of where your project stands,
straight from the saved files. If you close your laptop and come back a month later,
nothing is lost.

### What it will *not* do

- It will not invent results, references or data. Where evidence is missing, it leaves
  a visible placeholder such as `[NEEDS VERIFIED RESULT]` or
  `[REFERENCE NOT VERIFIED]`.
- It will not run expensive or remote jobs without your explicit approval.
- It will not tell you a paper is "ready" while problems remain, and it never predicts
  whether a journal will accept your work.
- It cannot judge whether your science is *good*. It checks that your claims are
  *traceable and consistent*. You and your co-authors still need to read critically.

---

## Installing it

You need **Python 3.10 or newer** and, ideally, **Git**. The tool uses Git to record
exactly which version of your code produced each result.

**Windows (PowerShell):**

```powershell
git clone https://github.com/JubayerONROB/research-pipeline.git
cd research-pipeline
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\research.exe --help
```

**macOS / Linux:**

```bash
git clone https://github.com/JubayerONROB/research-pipeline.git
cd research-pipeline
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/research --help
```

Optional extras: `matplotlib` for charts (included in `[dev]`), the `kaggle` package for
cloud runs, and `pandoc` for Word/PDF export. More detail is in
[docs/SETUP.md](docs/SETUP.md).

---

## Try the demonstration first (5 minutes)

```bash
python examples/demo_synthetic/run_demo.py
```

This runs a complete, small study from start to finish on **made-up (synthetic) data**:
does a "median filter" remove noise from a signal better than a "moving average"? Along
the way you will see:

- the dataset being checked and passing;
- 15 experiment runs recorded and validated;
- a statistical comparison with a chart;
- claims verified against the results;
- reports and suggested follow-up experiments;
- the approval gate blocking a cloud run until someone approves it;
- a draft paper being audited. The audit honestly **fails**, because sections like the
  introduction still need a human to write them.

Everything the demo produces lives in `examples/demo_synthetic/_work/`. Because the data
is synthetic, **none of it is a real scientific finding**. It only shows how the tool
works.

---

## Using it for your own study: a walk-through

Here is the typical sequence. Every command has built-in help (`research <command> -h`).

**1. Create a project**

```bash
research init my_study --domain signal_processing   # the domain is optional
cd my_study
```

Open `project.yaml` and write your research questions and hypotheses. For example:

```yaml
research:
  questions:
    - {id: RQ1, text: "Does filter B reduce noise more than filter A on our sensor data?"}
  hypotheses:
    - {id: H1, rq: RQ1, statement: "B has lower error than A",
       falsification: "No significant difference, or A has lower error", status: proposed}
```

**2. Register and check your data**

```bash
research data register --name sensors --version 1.0 \
    --file data/raw/train.csv:train --file data/raw/test.csv:test \
    --license "CC-BY-4.0" --access-verified
research data validate sensors
```

Read the report it writes in `data/validation/`. Fix anything marked FAIL.

**3. Describe an experiment**

```bash
research exp new EXP-001 --title "Baseline: filter A" --type baseline
```

This creates `experiments/configs/EXP-001.yaml`, where you list the script to run, the
random seeds, and the measurements ("metrics") it produces. Your script reads its
settings and saves its results with two lines of helper code:

```python
from research_engine.runtime import load_context, write_metrics
ctx = load_context()                     # settings, seed and output folder
# ... your experiment ...
write_metrics(ctx, {"rmse": 0.12}, n_samples=1000)
```

**4. Run it**

```bash
research run EXP-001 --dry-run    # shows the plan; runs nothing
research run EXP-001              # one run per seed, each permanently recorded
research validate                 # see which runs can be trusted
```

**5. Compare and report**

```bash
research analyze EXP-001 --compare EXP-002 --metric rmse --plot --name rq1
research report --all
```

**6. Record what you can claim**

```bash
research claim add --id C001 --text "Mean error of filter B" --type quantitative \
    --rq RQ1 --source-kind runs_metric --experiment EXP-002 --metric rmse --statistic mean
research claim verify
```

A claim is "verified" only when the tool recomputes it from validated results.

**7. Decide what to do next**

```bash
research propose            # suggested follow-ups, ranked, each with a reason
research proposals list
```

**8. Write and audit the paper**

```bash
research manuscript draft
research manuscript build
research manuscript audit
```

In the paper's source files, you write `{{claim:C001}}` instead of typing a number. The
tool fills in the verified value. If a result changes, the paper changes with it.

**Coming back later?** Run `research status --write` and open
`reports/progress_reports/PROGRESS.md`.

---

## Running experiments on Kaggle (optional)

Kaggle offers free cloud computers with GPUs. The tool can package your experiment,
send it to Kaggle, wait for it, and bring the results back. Because cloud runs use
quota (and paid services cost money), **every remote run needs your explicit approval**:

```bash
research approve run EXP-001 --backend kaggle --runs 3 --by "Your Name"
research run EXP-001 --backend kaggle
research remote collect
```

Your Kaggle password file stays outside the project and is never copied, printed or
uploaded. This feature has been tested only against a simulated Kaggle connection so
far. Read [docs/KAGGLE_INTEGRATION.md](docs/KAGGLE_INTEGRATION.md) before relying on it.

---

## Working with an AI assistant

Every new project includes ready-made instructions for Claude Code (`CLAUDE.md`) and
slash commands such as `/rp-recon` (catch up on project status), `/rp-experiment`
(design an experiment) and `/rp-audit` (audit the paper). The rules tell the assistant
never to fabricate results or citations, never to type numbers into the paper, and never
to grant approvals on your behalf. To enforce the last rule, copy
`templates/claude_settings.example.json` into your project as
`.claude/settings.json`.

---

## Key ideas, briefly

| Idea | Why it matters |
|---|---|
| **Files are the memory** | Everything is saved as readable files (YAML, JSON, Markdown). There is no hidden database, and nothing depends on remembering a past conversation. |
| **Runs are permanent** | Each run gets a unique ID and is never overwritten. Its output files are fingerprinted, so later edits are detected. |
| **"Finished" is not "trustworthy"** | A run can complete and still be marked INVALID. Only validated runs count as evidence. |
| **Failures are kept** | Failed and excluded runs stay on record and appear in reports, so results can't be cherry-picked. |
| **No hand-typed numbers** | Paper numbers come from verified claims, so the paper and the data can't drift apart. |
| **Humans make the big decisions** | Approvals, hypothesis verdicts and changes of plan are recorded with the name of the person who made them. |

---

## Glossary

- **Experiment:** one method or condition you want to test, described in a config file.
- **Run:** one execution of an experiment with one random seed.
- **Seed:** a number that controls randomness. Repeating runs with different seeds shows
  how stable a result is.
- **Metric:** a number your experiment measures, such as error or accuracy.
- **Baseline:** the standard method you compare against.
- **Ablation:** an experiment that removes or changes one part of a method to see how
  much that part matters.
- **Leakage:** test data that accidentally influences training, making results look
  better than they are.
- **Claim:** a statement you want to make in your paper, linked to the evidence behind it.
- **Statistically significant:** unlikely to be due to chance alone, *after* using an
  appropriate test.

---

## Documentation

| Document | What's in it |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Installation on Windows and VS Code, troubleshooting |
| [docs/RESEARCH_WORKFLOW.md](docs/RESEARCH_WORKFLOW.md) | The full lifecycle, step by step |
| [docs/EXPERIMENT_PROTOCOL.md](docs/EXPERIMENT_PROTOCOL.md) | Experiment configs, run records, reproducibility |
| [docs/DATA_MANAGEMENT.md](docs/DATA_MANAGEMENT.md) | Dataset registration and every data check |
| [docs/RESULT_VALIDATION.md](docs/RESULT_VALIDATION.md) | How results are judged trustworthy |
| [docs/ITERATION_LOOP.md](docs/ITERATION_LOOP.md) | Follow-up proposals and when to stop |
| [docs/MANUSCRIPT_WORKFLOW.md](docs/MANUSCRIPT_WORKFLOW.md) | Writing the paper with evidence markers |
| [docs/HALLUCINATION_PREVENTION.md](docs/HALLUCINATION_PREVENTION.md) | How unsupported claims are caught, and the limits of that |
| [docs/KAGGLE_INTEGRATION.md](docs/KAGGLE_INTEGRATION.md) | Cloud execution on Kaggle |
| [docs/SECURITY.md](docs/SECURITY.md) | Passwords, keys and safe operation |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the code is organised (for developers) |
| [docs/TESTING.md](docs/TESTING.md) | How the tool is tested, with actual results |
| [docs/ROADMAP.md](docs/ROADMAP.md) | What works, what is partial, what is planned |
| [CLAUDE.md](CLAUDE.md) | Rules for AI-assisted sessions |

## Contributing and support

Bug reports and suggestions are welcome as GitHub issues. Please report security
problems privately (see [docs/SECURITY.md](docs/SECURITY.md)). To run the test suite:
`python -m pytest`.

## Licence

MIT. You are free to use, modify and share this tool. See [LICENSE](LICENSE).
