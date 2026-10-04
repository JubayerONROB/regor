"""Experiment technical reports, generated from run records and analysis artifacts.

Labels used in every report:
  [MEASURED]        values read from validated raw outputs
  [DERIVED]         statistics computed from measured values
  [OBSERVATION]     automatically detected facts (failures, warnings, flags)
  [INTERPRETATION]  researcher-written meaning -- never generated as fact

The engine never writes interpretation or conclusions in prose. Where a human must
think, the report contains [RESEARCHER INPUT REQUIRED].
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import yaml

from . import datasets, evidence
from .analysis import stats
from .experiments import list_runs, load_spec
from .util import atomic_write_text, read_json, read_yaml, utc_now, write_json

RI = "[RESEARCHER INPUT REQUIRED]"


def _fmt(x: Any, nd: int = 5) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}g}"
    return str(x)


def _comparisons_for(project, exp_id: str) -> list[dict[str, Any]]:
    out = []
    for p in sorted(project.path("analysis", "comparisons").glob("*.json")):
        s = read_json(p)
        if not s or "comparisons" not in s:
            continue
        exps = [s["reference"]["experiment"]] + [c["other"] for c in s["comparisons"]]
        if exp_id in exps:
            out.append({"file": project.rel(p), "summary": s})
    return out


def _figures_for(project, exp_id: str) -> list[str]:
    out = []
    for p in sorted(project.path("analysis", "visualizations").glob("*.provenance.json")):
        prov = read_json(p) or {}
        if exp_id in prov.get("experiments", []):
            out.append(project.rel(p.with_name(prov["figure"])))
    return out


def experiment_report(project, exp_id: str) -> dict[str, Any]:
    spec = load_spec(project, exp_id)
    runs = list_runs(project, exp_id)
    rqs = {q["id"]: q["text"] for q in project.cfg["research"]["questions"]}
    hyps = {h["id"]: h for h in project.cfg["research"]["hypotheses"]}
    status_counts = Counter(r["status"] for r in runs)
    val_counts = Counter(r["validation"]["status"] for r in runs)
    validated = [r for r in runs if r["validation"]["status"] == "VALIDATED"]
    min_rep = project.cfg["statistics"].get("min_replicates", 3)
    L: list[str] = []
    add = L.append

    add(f"# Experiment report: {spec['id']} {spec['title']}")
    add("")
    add(f"_Generated {utc_now()} from {len(runs)} run record(s). Regenerate with "
        f"`regor report {exp_id}`; do not edit numbers by hand._")
    add("")
    if any((r.get("dataset") or {}).get("synthetic") for r in runs):
        add("> **SYNTHETIC DATA.** These results demonstrate the pipeline and are not scientific evidence.")
        add("")
    add("**Execution outcome [OBSERVATION]:** " +
        ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())) +
        " | **Validation:** " + ", ".join(f"{k}={v}" for k, v in sorted(val_counts.items())))
    add("")

    # 1-2
    add("## 1. Identification")
    add(f"- ID: `{spec['id']}`; type: {spec['type']}; status: {spec.get('status', 'draft')}")
    add("## 2. Date and execution environment [OBSERVATION]")
    if runs:
        add(f"- First run created: {runs[0]['created_at']}; last: {runs[-1]['created_at']}")
        backends = Counter(r["backend"] for r in runs)
        add(f"- Backends: {dict(backends)}")
        plats = {(r.get('provenance') or {}).get('platform') for r in runs}
        pys = {((r.get('provenance') or {}).get('packages') or {}).get('python') for r in runs}
        add(f"- Platforms: {sorted(p for p in plats if p)}; Python: {sorted(p for p in pys if p)}")
        hw = {json.dumps(((r.get('provenance') or {}).get('hardware') or {}).get('gpus')) for r in runs}
        add(f"- GPUs reported: {sorted(hw)}")
    else:
        add("- No runs recorded.")
    # 3-4
    add("## 3. Research question(s)")
    for rq in spec.get("research_questions", []) or ["(none linked)"]:
        add(f"- {rq}: {rqs.get(rq, '')}")
    add("## 4. Hypothesis(es)")
    for h in spec.get("hypotheses", []) or ["(none linked)"]:
        hh = hyps.get(h, {})
        add(f"- {h}: {hh.get('statement', '')} (falsified if: {hh.get('falsification', 'n/a')}; "
            f"current status: {hh.get('status', 'n/a')})")
    # 5
    add("## 5. Methodology")
    add(f"- Rationale: {spec.get('rationale')}")
    m = spec.get("method") or {}
    add(f"- Method: {m.get('name', 'n/a')}. {m.get('description', '')}")
    v = spec.get("variables") or {}
    for k in ("independent", "dependent", "controlled"):
        add(f"- {k.capitalize()} variables: {v.get(k, RI)}")
    # 6
    add("## 6. Dataset and version")
    ds = spec.get("dataset")
    if ds:
        val = datasets.latest_validation(project, ds["name"])
        add(f"- {ds['name']} v{ds.get('version')}; validation: {val['status'] if val else 'NOT VALIDATED'} "
            f"(`data/validation/{ds['name']}.md`)")
        fps = {(r.get("dataset") or {}).get("fingerprint") for r in runs}
        add(f"- Dataset fingerprints used by runs: {sorted(str(f)[:16] for f in fps if f)}")
    else:
        add("- No dataset declared.")
    # 7
    add("## 7. Configuration")
    hashes = Counter(r["config_sha256"][:16] for r in runs)
    add(f"- Config hashes (runs): {dict(hashes)}")
    add("```yaml")
    add(yaml.safe_dump({k: spec.get(k) for k in ("method", "parameters", "seeds", "compute", "entrypoint")},
                       sort_keys=False).strip())
    add("```")
    # 8-9
    add("## 8. Baselines and comparisons")
    add(f"- compare_with: {spec.get('compare_with') or 'none declared'}")
    add("## 9. Evaluation protocol")
    for md in spec.get("metrics", []):
        add(f"- `{md['name']}` ({md['direction']} is better{', ' + md['unit'] if md.get('unit') else ''}): "
            f"{md.get('definition') or RI}")
    add(f"- Statistical plan: {spec.get('statistics') or 'project defaults'}; "
        f"alpha={project.cfg['statistics']['alpha']}, correction={project.cfg['statistics']['multiple_comparison']}")
    # 10
    add("## 10. Actual results [MEASURED]")
    names = [md["name"] for md in spec.get("metrics", [])]
    add("| run_id | seed | backend | status | validation | " + " | ".join(names) + " | runtime (s) |")
    add("|---|---|---|---|---|" + "---|" * len(names) + "---|")
    for r in runs:
        vals = " | ".join(_fmt((r.get("metrics") or {}).get(n)) for n in names)
        add(f"| `{r['run_id']}` | {r.get('seed')} | {r['backend']} | {r['status']} | "
            f"{r['validation']['status']} | {vals} | {_fmt(r.get('runtime_seconds'))} |")
    add("")
    add("All runs are listed, including failed and unvalidated ones. Only VALIDATED runs enter statistics.")
    # 11
    add("## 11. Statistical analysis [DERIVED]")
    conf = project.cfg["statistics"].get("confidence_level", 0.95)
    desc_all = {}
    for n in names:
        vals = [r["metrics"][n] for r in validated if isinstance((r.get("metrics") or {}).get(n), (int, float))]
        d = stats.describe(vals, conf)
        desc_all[n] = d
        add(f"- `{n}`: n={d['n']}, mean={_fmt(d.get('mean'))}, std={_fmt(d.get('std'))}, "
            f"{conf:.0%} CI=[{_fmt(d.get('ci_low'))}, {_fmt(d.get('ci_high'))}] ({d.get('ci_method', '')})")
    comps = _comparisons_for(project, exp_id)
    for c in comps:
        add(f"- Comparison summary: `{c['file']}`")
    # 12
    add("## 12. Figures and tables")
    figs = _figures_for(project, exp_id)
    add("\n".join(f"- `{f}` (provenance sidecar alongside)" for f in figs) or
        "- None generated yet (`regor analyze ... --plot`).")
    # 13
    add("## 13. Comparison with previous experiments [DERIVED]")
    if not comps:
        add("- No comparison has been run.")
    for c in comps:
        s = c["summary"]
        for cc in s["comparisons"]:
            r = cc["result"]
            add(f"- {s['reference']['experiment']} vs {cc['other']} on `{s['metric']}`: test {r.get('test')}, "
                f"mean diff {_fmt(r.get('mean_difference'))}, p={_fmt(r.get('p_value'))}, "
                f"adjusted p={_fmt(r.get('p_adjusted'))}. Guard: {cc['interpretation_guard']}")
    # 14
    add("## 14. Observed errors [OBSERVATION]")
    errs = [(r["run_id"], r.get("error")) for r in runs if r.get("error")]
    issues = [(r["run_id"], i) for r in runs for i in r["validation"].get("issues", [])
              if i.get("severity") in ("INVALID", "INCOMPLETE", "PROVISIONAL")]
    add("\n".join(f"- `{rid}`: {e}" for rid, e in errs) or "- No execution errors recorded.")
    add("\n".join(f"- `{rid}` [{i['severity']}] {i['check']}: {i['message']}" for rid, i in issues)
        or "- No validation issues above INFO.")
    # 15
    add("## 15. Limitations")
    lim = []
    if len(validated) < min_rep:
        lim.append(f"[OBSERVATION] only {len(validated)} validated run(s); project minimum is {min_rep}")
    for n, d in desc_all.items():
        if d.get("cv") and d["cv"] > 0.2:
            lim.append(f"[OBSERVATION] `{n}` has a high coefficient of variation ({d['cv']:.2f})")
    if any((r.get("dataset") or {}).get("synthetic") for r in runs):
        lim.append("[OBSERVATION] synthetic data: no claim about real-world behaviour is supported")
    lim.append(f"[INTERPRETATION] {RI}")
    add("\n".join(f"- {x}" for x in lim))
    # 16
    add("## 16. Unexpected outcomes")
    add(f"- Failure criteria declared: {spec.get('failure_criteria') or 'none'}. Check them against "
        f"section 10. The engine does not evaluate free-text criteria.")
    add(f"- [INTERPRETATION] {RI}")
    # 17
    add("## 17. Reproducibility information")
    seeds = sorted({r.get('seed') for r in runs if r.get('seed') is not None})
    commits = Counter(((r.get('provenance') or {}).get('git') or {}).get('commit', 'n/a')[:12] for r in runs)
    add(f"- Seeds: {seeds}")
    add(f"- Code commits: {dict(commits)}")
    cks = {json.dumps((r.get('provenance') or {}).get('code_checksums', {}), sort_keys=True) for r in runs}
    add(f"- Entry-point checksums: {len(cks)} distinct set(s)")
    add(f"- Nondeterminism notes: {spec.get('nondeterminism_notes') or 'none recorded'}")
    add(f"- Reproduce: `regor run {exp_id} --seeds {' '.join(map(str, seeds)) or '0'}` "
        "(creates new run records, never overwrites these)")
    # 18
    add("## 18. Scientific interpretation [INTERPRETATION]")
    add(f"{RI}: write the interpretation here and label it as interpretation. Do not restate it as a finding.")
    # 19-20
    claims = [c for c in evidence.load(project) if exp_id in c.get("experiments", [])]
    add("## 19. Supported conclusions (verified claims only)")
    sup = [c for c in claims if c["status"] == "verified"]
    add("\n".join(f"- {c['id']}: {c['text']} (value {evidence.format_value(c) or 'n/a'})" for c in sup)
        or "- None. No claim linked to this experiment is verified.")
    add("## 20. Unsupported or unresolved questions")
    uns = [c for c in claims if c["status"] != "verified"]
    add("\n".join(f"- {c['id']} [{c['status']}]: {c['text']}. {c.get('verification_notes') or ''}" for c in uns)
        or "- No unresolved claims linked.")
    for h in spec.get("hypotheses", []):
        if hyps.get(h, {}).get("status", "proposed") == "proposed":
            add(f"- Hypothesis {h} has no verdict yet.")
    # 21
    add("## 21. Proposed follow-up experiments")
    props = [p for p in (read_yaml(project.path("experiments", "plans", "proposals.yaml"), {}) or {}).get("proposals", [])
             if exp_id in p.get("based_on", [])]
    add("\n".join(f"- {p['id']} [{p['status']}] {p['title']}" for p in props) or
        "- None yet. Run `regor propose` to generate evidence-based proposals.")

    text = "\n".join(L) + "\n"
    base = project.path("reports", "experiment_reports", exp_id)
    atomic_write_text(base.with_suffix(".md"), text)
    machine = {"experiment": exp_id, "generated_at": utc_now(), "status_counts": dict(status_counts),
               "validation_counts": dict(val_counts), "descriptive": desc_all,
               "validated_run_ids": [r["run_id"] for r in validated],
               "comparisons": [c["file"] for c in comps], "figures": figs,
               "verified_claims": [c["id"] for c in sup], "unresolved_claims": [c["id"] for c in uns]}
    write_json(base.with_suffix(".json"), machine)
    return {"markdown": project.rel(base.with_suffix(".md")), "json": project.rel(base.with_suffix(".json")),
            "summary": machine}
