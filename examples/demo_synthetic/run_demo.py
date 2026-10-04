"""End-to-end demonstration of the research engine on SYNTHETIC data.

    python examples/demo_synthetic/run_demo.py [--workdir DIR]

Copies ./template into a fresh work directory (default: ./_work, gitignored), then
drives the full lifecycle through the real `regor` CLI:

  init -> data register/validate -> experiment validation -> dry run -> local runs ->
  result validation -> comparison + figures -> claims -> reports -> proposals ->
  approval gate + MOCK Kaggle round trip (always INVALID as evidence) ->
  manuscript draft/build/audit -> journal checklist -> progress report

Everything produced is a demonstration. The data is synthetic; no output is a
scientific finding. Needs no network, GPU, paid service or credential.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from regor.cli import main as research  # noqa: E402
from regor.project import init_project  # noqa: E402

ABSTRACT = """# Abstract

DEMONSTRATION ON SYNTHETIC DATA. On a synthetic impulsive-noise benchmark, the median filter
reached a mean RMSE of {{claim:C001}}, against {{claim:C002}} for the moving-average baseline.
{{claimtext:C003}} ({{claim:C004}} mean paired difference, Holm-adjusted p = {{claim:C005}}).
{{claimtext:C006}}
"""

RESULTS_EXTRA = """
## Narrative (demonstration)

The median filter's mean RMSE was {{claim:C001}} and the baseline's {{claim:C002}}.
The paired difference was {{claim:C004}}.
"""


def step(title: str, *argv: str, project: Path, allow_fail: bool = False) -> int:
    print(f"\n$ research {' '.join(argv)}    # {title}")
    code = research(["--project", str(project), *argv])
    if code != 0 and not allow_fail:
        raise SystemExit(f"demo step failed: {title} (exit {code})")
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=str(HERE / "_work"))
    a = ap.parse_args()
    work = Path(a.workdir).resolve()
    if work.exists():
        def _force(func, path, _exc):          # git objects are read-only on Windows
            import os, stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(work, onerror=_force)
    shutil.copytree(HERE / "template", work)
    init_project(work, "demo_synthetic", "signal_processing", force=True)
    print(f"demo project at {work}  (SYNTHETIC DATA -- demonstration only)")
    # Pin the demo's code with its own git snapshot: without a recorded commit every run
    # is (correctly) only PROVISIONAL. runs/ and data/raw/ are gitignored by the scaffold.
    git = ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.invalid", "-c", "core.autocrlf=false"]
    subprocess.run(git + ["init", "-q"], cwd=work, check=True)
    subprocess.run(git + ["add", "-A"], cwd=work, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "demo snapshot"], cwd=work, check=True)

    subprocess.run([sys.executable, "scripts/generate_data.py", "data/raw/demo_signals"], cwd=work, check=True)
    P = dict(project=work)
    step("register dataset", "data", "register", "--from-yaml", str(work / "data/demo_signals.dataset.yaml"), **P)
    step("validate dataset", "data", "validate", "demo_signals", **P)
    step("validate experiment specs", "exp", "validate", **P)
    step("dry run (no records created)", "run", "EXP-BASE", "--dry-run", **P)
    for e in ("EXP-BASE", "EXP-PROP", "EXP-ABL"):
        step(f"run {e} locally", "run", e, **P)
    step("validate all results", "validate", **P)
    step("compare RQ1", "analyze", "EXP-BASE", "--compare", "EXP-PROP", "--metric", "rmse",
         "--plot", "--name", "rq1_rmse", **P)
    step("compare RQ2 (ablation)", "analyze", "EXP-PROP", "--compare", "EXP-ABL", "--metric", "rmse",
         "--plot", "--name", "rq2_window", **P)

    claims = [
        ["--id", "C001", "--text", "Mean RMSE of the window-5 median filter on the synthetic benchmark",
         "--type", "quantitative", "--rq", "RQ1", "--source-kind", "runs_metric",
         "--experiment", "EXP-PROP", "--metric", "rmse", "--statistic", "mean", "--digits", "4"],
        ["--id", "C002", "--text", "Mean RMSE of the window-5 moving-average filter on the synthetic benchmark",
         "--type", "quantitative", "--rq", "RQ1", "--source-kind", "runs_metric",
         "--experiment", "EXP-BASE", "--metric", "rmse", "--statistic", "mean", "--digits", "4"],
        ["--id", "C003", "--text", "On this synthetic benchmark the median filter had lower RMSE than the "
         "moving average, and the paired difference was significant after Holm correction",
         "--type", "statistical", "--rq", "RQ1", "--source-kind", "analysis",
         "--file", "analysis/comparisons/rq1_rmse.json", "--json-path", "comparisons.0.result.p_adjusted"],
        ["--id", "C004", "--text", "Mean paired RMSE difference (median minus moving average)",
         "--type", "comparative", "--rq", "RQ1", "--source-kind", "analysis",
         "--file", "analysis/comparisons/rq1_rmse.json", "--json-path", "comparisons.0.result.mean_difference",
         "--digits", "4"],
        ["--id", "C005", "--text", "Holm-adjusted p-value of the RQ1 comparison",
         "--type", "statistical", "--rq", "RQ1", "--source-kind", "analysis",
         "--file", "analysis/comparisons/rq1_rmse.json", "--json-path", "comparisons.0.result.p_adjusted",
         "--digits", "4"],
        ["--id", "C006", "--text", "All results come from synthetic data and do not support claims about real signals",
         "--type", "limitation", "--source-kind", "artifact", "--file", "data/validation/demo_signals.md"],
        ["--id", "C007", "--text", "Mean RMSE of the window-3 median filter (ablation)",
         "--type", "quantitative", "--rq", "RQ2", "--source-kind", "runs_metric",
         "--experiment", "EXP-ABL", "--metric", "rmse", "--statistic", "mean", "--digits", "4"],
    ]
    for c in claims:
        step(f"add claim {c[1]}", "claim", "add", *c, **P)
    step("verify claims against artifacts", "claim", "verify", **P)
    step("experiment reports", "report", "--all", **P)
    step("evidence-based follow-up proposals", "propose", **P)

    print("\n--- approval gate and MOCK remote execution (demonstrates guardrails; never evidence) ---")
    step("Kaggle run WITHOUT approval (expected to be blocked)", "run", "EXP-PROP", "--backend", "kaggle",
         "--seeds", "0", "--mock-remote", allow_fail=True, **P)
    step("researcher approval (demo identity)", "approve", "run", "EXP-PROP", "--backend", "kaggle",
         "--runs", "1", "--by", "DEMO RESEARCHER", "--reason", "demonstrate the approval gate", **P)
    step("mock Kaggle submission", "run", "EXP-PROP", "--backend", "kaggle", "--seeds", "0", "--mock-remote", **P)
    step("collect mock remote run (validates as INVALID by design)", "remote", "collect", "--mock-remote", **P)

    step("manuscript skeleton", "manuscript", "init", **P)
    step("evidence-driven drafts", "manuscript", "draft", **P)
    secs = work / "manuscript" / "sections"
    (next(secs.glob("*_abstract.md"))).write_text(ABSTRACT, encoding="utf-8")
    res = next(p for p in secs.glob("*_results.md") if not p.name.endswith(".generated.md"))
    res.write_text(res.read_text(encoding="utf-8") + RESULTS_EXTRA, encoding="utf-8")
    step("build manuscript", "manuscript", "build", **P)
    step("audit manuscript (placeholders remain, so FAIL is the honest outcome)", "manuscript", "audit",
         allow_fail=True, **P)
    step("journal profile skeleton", "journal", "init", "Example Journal", **P)
    step("journal checklist (unknown limits stay unknown)", "journal", "check", "example-journal", **P)
    step("progress report", "status", "--write", **P)
    print(f"\nDemo finished. Inspect {work}/reports, {work}/analysis and {work}/manuscript/audit.")
    print("Reminder: SYNTHETIC data -- these outputs demonstrate the pipeline, not a finding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
