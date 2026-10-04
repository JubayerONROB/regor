"""Aggregation and comparison of experiments, from validated runs only.

Every summary lists the runs it used *and the runs it excluded with the reason*, so a
reader can see that nothing unfavourable was dropped silently.
"""

from __future__ import annotations

from typing import Any

from ..errors import ResearchError
from ..experiments import list_runs, load_spec
from ..util import atomic_write_text, sha256_obj, utc_now, write_json
from . import stats


def metric_def(spec: dict[str, Any], metric: str) -> dict[str, Any]:
    for m in spec.get("metrics", []):
        if m["name"] == metric:
            return m
    raise ResearchError(f"metric {metric!r} is not declared by experiment {spec['id']}")


def collect_values(project, exp_id: str, metric: str,
                   allow_provisional: bool = False) -> dict[str, Any]:
    spec = load_spec(project, exp_id)
    mdef = metric_def(spec, metric)
    ok = {"VALIDATED"} | ({"PROVISIONAL"} if allow_provisional else set())
    used, excluded = [], []
    for r in list_runs(project, exp_id):
        vs = r["validation"]["status"]
        val = (r.get("metrics") or {}).get(metric)
        if vs not in ok:
            excluded.append({"run_id": r["run_id"], "seed": r.get("seed"),
                             "reason": f"validation {vs}", "status": r["status"]})
        elif not isinstance(val, (int, float)) or isinstance(val, bool):
            excluded.append({"run_id": r["run_id"], "seed": r.get("seed"),
                             "reason": "metric missing", "status": r["status"]})
        else:
            used.append({"run_id": r["run_id"], "seed": r.get("seed"), "value": float(val),
                         "validation": vs, "config_sha256": r["config_sha256"],
                         "backend": r["backend"]})
    return {"experiment": exp_id, "metric": metric, "definition": mdef, "runs": used,
            "excluded": excluded, "values": [u["value"] for u in used]}


def summarize_experiment(project, exp_id: str, metric: str,
                         allow_provisional: bool = False) -> dict[str, Any]:
    cv = collect_values(project, exp_id, metric, allow_provisional)
    conf = project.cfg["statistics"].get("confidence_level", 0.95)
    desc = stats.describe(cv["values"], conf)
    mr = project.cfg["statistics"].get("min_replicates", 3)
    warnings = []
    if desc["n"] < mr:
        warnings.append(f"only {desc['n']} validated run(s); project minimum is {mr}")
    configs = {r["config_sha256"] for r in cv["runs"]}
    if len(configs) > 1:
        warnings.append(f"runs span {len(configs)} different configurations; aggregation mixes them")
    return {**cv, "descriptive": desc, "warnings": warnings,
            "allow_provisional": allow_provisional}


def compare(project, reference: str, others: list[str], metric: str,
            test: str | None = None, paired_by: str | None = "auto",
            allow_provisional: bool = False, name: str | None = None) -> dict[str, Any]:
    st = project.cfg["statistics"]
    alpha = st.get("alpha", 0.05)
    conf = st.get("confidence_level", 0.95)
    ref_spec = load_spec(project, reference)
    test = test or (ref_spec.get("statistics") or {}).get("test") or st.get("default_test", "auto")
    if paired_by == "auto":
        paired_by = (ref_spec.get("statistics") or {}).get("paired_by")
    ref = summarize_experiment(project, reference, metric, allow_provisional)
    direction = ref["definition"].get("direction", "none")
    comps, pvals = [], []
    for o in others:
        oth = summarize_experiment(project, o, metric, allow_provisional)
        if oth["definition"].get("direction") != direction or \
                oth["definition"].get("unit", "") != ref["definition"].get("unit", ""):
            raise ResearchError(f"metric {metric!r} is defined differently in {reference} and {o}; "
                                "comparison would be unfair")
        a, b, paired, pairs = ref["values"], oth["values"], False, None
        if paired_by == "seed":
            ra = {r["seed"]: r["value"] for r in ref["runs"]}
            rb = {r["seed"]: r["value"] for r in oth["runs"]}
            common = sorted(set(ra) & set(rb), key=lambda s: (s is None, s))
            a, b, paired, pairs = [ra[s] for s in common], [rb[s] for s in common], True, common
        res = stats.compare_two(a, b, paired=paired, test=test or "auto", alpha=alpha,
                                confidence=conf)
        md = res.get("mean_difference")
        if md is None or direction == "none":
            better = "undetermined"
        elif res.get("p_value") is None:
            better = "untested"
        else:
            better = "other" if ((md > 0) == (direction == "higher")) and md != 0 else \
                ("reference" if md != 0 else "equal")
        comps.append({"other": o, "other_summary": {k: oth[k] for k in ("descriptive", "warnings", "excluded")},
                      "other_runs": oth["runs"], "paired_seeds": pairs, "result": res,
                      "point_estimate_favours": better})
        pvals.append(res.get("p_value"))
    method = st.get("multiple_comparison", "holm")
    adj = stats.adjust_pvalues(pvals, method)
    for c, pa in zip(comps, adj):
        c["result"]["p_adjusted"] = pa
        c["result"]["p_adjustment"] = method if len([p for p in pvals if p is not None]) > 1 else "none (single test)"
        c["result"]["significant_after_adjustment"] = pa is not None and pa < alpha
        c["interpretation_guard"] = _guard(c, alpha)
    summary = {
        "name": name or f"{reference}__vs__{'_'.join(others)}__{metric}",
        "created_at": utc_now(),
        "metric": metric,
        "metric_definition": ref["definition"],
        "reference": {"experiment": reference, "descriptive": ref["descriptive"],
                      "runs": ref["runs"], "excluded": ref["excluded"], "warnings": ref["warnings"]},
        "comparisons": comps,
        "settings": {"alpha": alpha, "confidence": conf, "test": test, "paired_by": paired_by,
                     "multiple_comparison": method, "allow_provisional": allow_provisional},
    }
    summary["sha256"] = sha256_obj({k: v for k, v in summary.items() if k != "created_at"})
    return summary


def _guard(c: dict[str, Any], alpha: float) -> str:
    r = c["result"]
    if r.get("p_value") is None:
        return "No inferential claim is supported (no test was run)."
    if not r.get("significant_after_adjustment"):
        return (f"The difference is not statistically significant at alpha={alpha} after "
                "adjustment; do not describe one condition as better.")
    return ("Statistically significant after adjustment; report the effect size and interval, "
            "and do not generalise beyond the evaluated conditions.")


def write_summary(project, summary: dict[str, Any]) -> tuple[str, str]:
    base = project.path("analysis", "comparisons", summary["name"])
    write_json(base.with_suffix(".json"), summary)
    atomic_write_text(base.with_suffix(".md"), render_summary(summary))
    return project.rel(base.with_suffix(".json")), project.rel(base.with_suffix(".md"))


def _fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}g}"
    return str(x)


def render_summary(s: dict[str, Any]) -> str:
    m = s["metric_definition"]
    lines = [f"# Comparison: {s['name']}", "",
             f"- Metric: `{s['metric']}` ({m.get('direction')} is better"
             f"{', unit ' + m['unit'] if m.get('unit') else ''})",
             f"- Definition: {m.get('definition') or '[RESEARCHER INPUT REQUIRED]'}",
             f"- Settings: {s['settings']}", f"- Summary hash: `{s['sha256'][:16]}`", "",
             "## Descriptive statistics (validated runs only)", "",
             "| Experiment | n | mean | std | 95% CI | median | min | max |",
             "|---|---|---|---|---|---|---|---|"]
    rows = [(s["reference"]["experiment"], s["reference"]["descriptive"])] + \
           [(c["other"], c["other_summary"]["descriptive"]) for c in s["comparisons"]]
    for name, d in rows:
        ci = f"[{_fmt(d.get('ci_low'))}, {_fmt(d.get('ci_high'))}]"
        lines.append(f"| {name} | {d.get('n')} | {_fmt(d.get('mean'))} | {_fmt(d.get('std'))} | "
                     f"{ci} | {_fmt(d.get('median'))} | {_fmt(d.get('min'))} | {_fmt(d.get('max'))} |")
    lines += ["", "## Inferential comparisons", ""]
    for c in s["comparisons"]:
        r = c["result"]
        es = r.get("effect_size") or {}
        lines += [f"### {s['reference']['experiment']} vs {c['other']}", "",
                  f"- Test: **{r.get('test')}**. Rationale: {r.get('rationale')}",
                  f"- n: {r['n_a']} vs {r['n_b']} (paired: {r['paired']})",
                  f"- Mean difference (other - reference): {_fmt(r.get('mean_difference'))}; "
                  f"CI: {r.get('diff_ci')}",
                  f"- Statistic: {_fmt(r.get('statistic'))}; p = {_fmt(r.get('p_value'))}; "
                  f"adjusted p = {_fmt(r.get('p_adjusted'))} ({r.get('p_adjustment')})",
                  f"- Effect size: {es.get('name')} = {_fmt(es.get('value'))}",
                  f"- Assumption checks: {r.get('assumptions')}",
                  f"- Point estimate favours: {c['point_estimate_favours']}",
                  f"- **Interpretation guard:** {c['interpretation_guard']}"]
        for w in r.get("warnings", []):
            lines.append(f"- WARNING: {w}")
        lines.append("")
    lines += ["## Individual runs", "", "| Experiment | seed | value | validation | run_id |",
              "|---|---|---|---|---|"]
    for r in s["reference"]["runs"]:
        lines.append(f"| {s['reference']['experiment']} | {r['seed']} | {_fmt(r['value'], 6)} | {r['validation']} | `{r['run_id']}` |")
    for c in s["comparisons"]:
        for r in c["other_runs"]:
            lines.append(f"| {c['other']} | {r['seed']} | {_fmt(r['value'], 6)} | {r['validation']} | `{r['run_id']}` |")
    excl = s["reference"]["excluded"] + [e for c in s["comparisons"] for e in c["other_summary"]["excluded"]]
    lines += ["", "## Excluded runs (kept in the registry, not used here)", ""]
    lines += [f"- `{e['run_id']}` (seed {e['seed']}): {e['reason']}" for e in excl] or ["- none"]
    return "\n".join(lines) + "\n"
