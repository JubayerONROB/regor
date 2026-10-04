"""Project status reconstruction, progress report, decision log, history views.

``status()`` rebuilds everything from files on disk. It is the entry point for resuming
work after a session ends or a machine restarts: it does not depend on any conversation
history.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .util import atomic_write_text, read_json, read_yaml, short_id, utc_now, write_json, write_yaml


# ------------------------------------------------------------------ decisions

def _dpath(project):
    return project.path("docs", "decisions", "decision_log.yaml")


def decisions(project) -> list[dict[str, Any]]:
    return (read_yaml(_dpath(project), {}) or {}).get("decisions", []) or []


def log_decision(project, title: str, motivation: str, evidence: str, alternatives: str,
                 consequences: str, by: str, kind: str = "methodological", note: str = "") -> dict[str, Any]:
    if not by or not by.strip():
        raise ValueError("a decision must name who made it")
    items = decisions(project)
    d = {"id": f"D-{len(items) + 1:03d}", "date": utc_now(), "kind": kind, "title": title,
         "motivation": motivation, "evidence": evidence, "alternatives": alternatives,
         "consequences": consequences, "decided_by": by, "note": note}
    items.append(d)
    write_yaml(_dpath(project), {"decisions": items})
    lines = ["# Decision log", "", "Generated from `decision_log.yaml`.", ""]
    for x in items:
        lines += [f"## {x['id']} {x['title']}", f"- Date: {x['date']}; kind: {x['kind']}; by: {x['decided_by']}",
                  f"- Motivation: {x['motivation']}", f"- Evidence: {x['evidence']}",
                  f"- Alternatives considered: {x['alternatives']}",
                  f"- Consequences: {x['consequences']}"] + ([f"- Note: {x['note']}"] if x.get("note") else []) + [""]
    atomic_write_text(project.path("docs", "decisions", "DECISIONS.md"), "\n".join(lines))
    return d


def set_hypothesis(project, hid: str, status: str, by: str, claims: list[str], note: str = "") -> None:
    """Record a verdict. supported/refuted require verified claims as evidence."""
    from . import evidence
    if status in ("supported", "refuted"):
        cl = {c["id"]: c for c in evidence.load(project)}
        bad = [c for c in claims if cl.get(c, {}).get("status") != "verified"]
        if not claims or bad:
            raise ValueError(f"a '{status}' verdict needs verified claims as evidence; not verified: {bad or 'none given'}")
    for h in project.cfg["research"]["hypotheses"]:
        if h["id"] == hid:
            old = h.get("status", "proposed")
            h["status"] = status
            h["evidence_claims"] = claims
            project.save()
            log_decision(project, f"Hypothesis {hid}: {old} -> {status}", "verdict on hypothesis",
                         f"claims {claims}", "supported / refuted / inconclusive", "changes manuscript framing",
                         by, kind="hypothesis", note=note)
            return
    raise KeyError(f"hypothesis {hid} not found")


# ------------------------------------------------------------------ status

def status(project) -> dict[str, Any]:
    from . import datasets, evidence, iteration, literature
    from .experiments import list_runs, list_specs
    specs = list_specs(project)
    runs = list_runs(project)
    by_exp: dict[str, Any] = {}
    for s in specs:
        rr = [r for r in runs if r["experiment_id"] == s["id"]]
        by_exp[s["id"]] = {"title": s.get("title"), "type": s.get("type"), "status": s.get("status", "draft"),
                           "runs": len(rr), "run_status": dict(Counter(r["status"] for r in rr)),
                           "validation": dict(Counter(r["validation"]["status"] for r in rr))}
    ds = []
    for d in datasets.load_manifest(project)["datasets"]:
        v = datasets.latest_validation(project, d["name"])
        ds.append({"name": d["name"], "version": d.get("version"), "synthetic": bool(d.get("synthetic")),
                   "validation": v["status"] if v else "NOT VALIDATED"})
    claims = evidence.load(project)
    refs = literature.load(project)
    props = iteration.load(project)
    audit = read_json(project.path("manuscript", "audit", "audit_report.json"))
    stop = iteration.stopping_status(project)
    st = {
        "project": project.name, "domain": project.cfg["project"]["domain"], "generated_at": utc_now(),
        "research_questions": project.cfg["research"]["questions"],
        "hypotheses": [{"id": h["id"], "status": h.get("status", "proposed"), "statement": h["statement"]}
                       for h in project.cfg["research"]["hypotheses"]],
        "experiments": by_exp,
        "runs_total": len(runs),
        "runs_by_status": dict(Counter(r["status"] for r in runs)),
        "runs_by_validation": dict(Counter(r["validation"]["status"] for r in runs)),
        "failed_runs": [r["run_id"] for r in runs if r["status"] in ("FAILED", "TIMED_OUT", "CANCELLED")],
        "pending_remote": [r["run_id"] for r in runs if r["status"] == "SUBMITTED"],
        "datasets": ds,
        "claims": dict(Counter(c["status"] for c in claims)),
        "references": dict(Counter(r["verification"]["status"] for r in refs)),
        "proposals": dict(Counter(p["status"] for p in props)),
        "pending_proposals": [p["id"] for p in props if p["status"] == "proposed"],
        "decisions": len(decisions(project)),
        "manuscript_audit": audit.get("overall") if audit else "not run",
        "stopping": stop,
    }
    st["next_steps"] = _next_steps(st)
    return st


def _next_steps(st: dict[str, Any]) -> list[str]:
    out = []
    if any(d["validation"] in ("NOT VALIDATED", "FAIL") for d in st["datasets"]):
        out.append("Validate datasets: `regor data validate <name>` and fix FAIL items")
    if not st["experiments"]:
        out.append("Define a first experiment in experiments/configs/ (copy _TEMPLATE.yaml.example)")
    if st["pending_remote"]:
        out.append(f"Collect remote runs: `regor remote collect` ({len(st['pending_remote'])} pending)")
    if st["runs_by_validation"].get("UNVALIDATED"):
        out.append("Validate results: `regor validate`")
    if st["failed_runs"]:
        out.append(f"Inspect {len(st['failed_runs'])} failed/cancelled run(s); keep them in the registry")
    if st["claims"].get("unverified") or st["claims"].get("failed"):
        out.append("Verify claims: `regor claim verify` and fix failed ones")
    if st["pending_proposals"]:
        out.append(f"Review proposals: {', '.join(st['pending_proposals'][:5])} (`regor proposals list`)")
    if st["stopping"]["review_required"]:
        out.append("Researcher review checkpoint due: `regor loop review --by NAME`")
    if st["stopping"]["must_stop"]:
        out.append("Stopping criteria met: " + "; ".join(st["stopping"]["must_stop"]))
    if st["references"].get("unverified"):
        out.append("Verify references: `regor lit verify --all`")
    return out or ["No automatic next step; consult the research plan."]


def write_progress(project) -> dict[str, Any]:
    st = status(project)
    L = [f"# Research progress: {st['project']}", "", f"_Rebuilt from project files at {st['generated_at']}._", "",
         "## Research questions"] + [f"- {q['id']}: {q['text']}" for q in st["research_questions"]] + \
        ["", "## Hypotheses"] + [f"- {h['id']} [{h['status']}]: {h['statement']}" for h in st["hypotheses"]] + \
        ["", "## Experiments", "", "| ID | type | spec status | runs | run status | validation |", "|---|---|---|---|---|---|"]
    for k, e in st["experiments"].items():
        L.append(f"| {k} | {e['type']} | {e['status']} | {e['runs']} | {e['run_status']} | {e['validation']} |")
    L += ["", "## Datasets"] + [f"- {d['name']} v{d['version']}: {d['validation']}"
                                + (" (SYNTHETIC)" if d["synthetic"] else "") for d in st["datasets"]]
    L += ["", f"## Evidence", f"- Claims: {st['claims']}", f"- References: {st['references']}",
          f"- Manuscript audit: {st['manuscript_audit']}",
          "", "## Iteration loop", f"- Iterations: {st['stopping']['iterations']}",
          f"- Compute used: {st['stopping']['compute_used_hours']} h",
          f"- Proposals: {st['proposals']}",
          f"- Must stop: {st['stopping']['must_stop'] or 'no'}",
          f"- Review required: {st['stopping']['review_required'] or 'no'}",
          f"- Open hypotheses: {st['stopping']['open_hypotheses']}",
          f"- RQs without verified claims: {st['stopping']['rqs_without_verified_claims']}",
          "", f"## Decisions recorded: {st['decisions']} (see docs/decisions/DECISIONS.md)",
          "", "## Failed / cancelled runs (preserved)"] + [f"- `{r}`" for r in st["failed_runs"]] + \
         (["- none"] if not st["failed_runs"] else []) + ["", "## Next recommended steps"] + \
         [f"- {s}" for s in st["next_steps"]]
    atomic_write_text(project.path("reports", "progress_reports", "PROGRESS.md"), "\n".join(L) + "\n")
    write_json(project.path("reports", "progress_reports", "progress.json"), st)
    _history(project)
    return st


def _history(project) -> None:
    from .experiments import list_runs, list_specs
    specs = list_specs(project)
    g = ["# Experiment dependency graph", "", "```mermaid", "graph LR"]
    for s in specs:
        g.append(f'  {s["id"].replace("-", "_")}["{s["id"]} ({s.get("type")})"]')
        for d in s.get("depends_on", []):
            g.append(f"  {d.replace('-', '_')} --> {s['id'].replace('-', '_')}")
        for c in s.get("compare_with", []):
            g.append(f"  {c.replace('-', '_')} -.compared.-> {s['id'].replace('-', '_')}")
    g.append("```")
    atomic_write_text(project.path("docs", "experiment_history", "dependency_graph.md"), "\n".join(g) + "\n")
    t = ["# Timeline", "", "| created | run | status | validation |", "|---|---|---|---|"]
    for r in list_runs(project):
        t.append(f"| {r['created_at']} | `{r['run_id']}` | {r['status']} | {r['validation']['status']} |")
    for d in decisions(project):
        t.append(f"| {d['date']} | decision {d['id']}: {d['title']} | - | - |")
    atomic_write_text(project.path("docs", "experiment_history", "timeline.md"), "\n".join(t) + "\n")
