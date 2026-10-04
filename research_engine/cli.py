"""`research` command-line interface.

Every command reads and writes project files only; nothing depends on session memory.
Run `research <command> -h` for details.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import ResearchError


def _p(args):
    from .project import Project
    return Project.find(args.project) if args.project else Project.find()


def _print(obj: Any) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


# ------------------------------------------------------------------ project

def cmd_init(a):
    from .project import init_project
    target = Path(a.dir) if a.dir else Path.cwd() / a.name
    p = init_project(target, a.name, a.domain or "generic", force=a.force)
    print(f"initialised project '{p.name}' (domain: {p.domain.name}) at {p.root}")
    print("next: edit project.yaml (research questions, hypotheses), register data with "
          "`research data register`, then copy experiments/configs/_TEMPLATE.yaml.example")
    return 0


def cmd_domains(a):
    from . import domains
    for n in domains.available():
        print(f"{n:24} {domains.get_profile(n).description}")
    return 0


def cmd_check(a):
    from . import config, datasets, evidence
    from .experiments import check_spec, list_specs
    p = _p(a)
    problems = 0
    print(f"project.yaml: OK ({p.name})")
    try:
        datasets.load_manifest(p)
        print("data/dataset_manifest.yaml: OK")
    except ResearchError as e:
        problems += 1
        print(f"data/dataset_manifest.yaml: {e}")
    try:
        evidence.load(p)
        print("evidence/claims.yaml: OK")
    except ResearchError as e:
        problems += 1
        print(f"evidence/claims.yaml: {e}")
    for s in list_specs(p):
        errs = check_spec(p, s)
        problems += bool(errs)
        print(f"experiments/configs/{s.get('id')}.yaml: " + ("OK" if not errs else "\n  - " + "\n  - ".join(errs)))
    return 1 if problems else 0


def cmd_status(a):
    from .progress import status, write_progress
    p = _p(a)
    st = write_progress(p) if a.write else status(p)
    if a.json:
        _print(st)
        return 0
    print(f"Project {st['project']} [{st['domain']}]")
    print(f"  runs: {st['runs_total']} {st['runs_by_status']} validation {st['runs_by_validation']}")
    for k, e in st["experiments"].items():
        print(f"  {k:16} {e['type']:12} runs={e['runs']:3} {e['validation']}")
    print(f"  datasets: {[(d['name'], d['validation']) for d in st['datasets']]}")
    print(f"  claims: {st['claims']}  references: {st['references']}  proposals: {st['proposals']}")
    print(f"  manuscript audit: {st['manuscript_audit']}")
    print(f"  stopping: must_stop={st['stopping']['must_stop'] or 'no'} review={st['stopping']['review_required'] or 'no'}")
    print("  next steps:")
    for s in st["next_steps"]:
        print(f"    - {s}")
    if a.write:
        print("written: reports/progress_reports/PROGRESS.md")
    return 0


# ------------------------------------------------------------------ experiments

def cmd_exp(a):
    from .experiments import check_spec, list_runs, list_specs, load_spec, spec_path
    p = _p(a)
    if a.exp_cmd == "list":
        for s in list_specs(p):
            n = len(list_runs(p, s["id"]))
            print(f"{s['id']:16} {s.get('type', '?'):12} {s.get('status', 'draft'):10} runs={n:3}  {s.get('title')}")
    elif a.exp_cmd == "validate":
        ids = [a.id] if a.id else [s["id"] for s in list_specs(p)]
        bad = 0
        for i in ids:
            errs = check_spec(p, load_spec(p, i))
            bad += bool(errs)
            print(f"{i}: " + ("OK" if not errs else "INVALID\n  - " + "\n  - ".join(errs)))
        return 1 if bad else 0
    elif a.exp_cmd == "new":
        dst = spec_path(p, a.id)
        if dst.exists():
            raise ResearchError(f"{p.rel(dst)} already exists")
        tpl = p.path("experiments", "configs", "_TEMPLATE.yaml.example").read_text(encoding="utf-8")
        lines = [l for l in tpl.splitlines() if not l.startswith("# Copy to")]
        text = "\n".join(lines).replace("id: EXP-001", f"id: {a.id}")
        if a.title:
            text = text.replace('title: "Baseline: <method> on <dataset>"', f'title: "{a.title}"')
        if a.type:
            text = text.replace("type: baseline ", f"type: {a.type} ", 1)
        dst.write_text(text + "\n", encoding="utf-8")
        print(f"created {p.rel(dst)}; edit it, then `research exp validate {a.id}`")
    return 0


def _mock_client(a):
    if getattr(a, "mock_remote", False):
        from .executors.kaggle import MockKaggleClient
        return MockKaggleClient()
    return None


def cmd_run(a):
    from .engine import format_plan, run_experiment
    p = _p(a)
    res = run_experiment(p, a.id, backend=a.backend, seeds=a.seeds, dry_run=a.dry_run,
                         allow_unvalidated=a.allow_unvalidated, resume_from=a.resume_from,
                         parallel=a.parallel, kaggle_client=_mock_client(a))
    print(format_plan(res["plan"]))
    if not res["executed"]:
        if a.dry_run:
            print("dry run: nothing executed, no run records created")
        return 0 if (a.dry_run and not res["plan"]["problems"]) else (1 if res["plan"]["problems"] else 0)
    print("")
    for r in res["runs"]:
        print(f"{r['run_id']}: {r['status']} / {r['validation']['status']}"
              + (f"  error: {r['error']}" if r.get("error") else ""))
    return 0 if all(r["status"] in ("COMPLETED", "SUBMITTED") for r in res["runs"]) else 1


def cmd_remote(a):
    p = _p(a)
    if a.remote_cmd == "collect":
        from .engine import collect_remote
        out = collect_remote(p, a.run, kaggle_client=_mock_client(a))
        if not out:
            print("no SUBMITTED runs")
        for r in out:
            print(f"{r['run_id']}: {r['status']} / {r['validation']['status']} "
                  f"(remote status {(r.get('remote') or {}).get('last_status')})")
    elif a.remote_cmd == "resources":
        from .executors.kaggle import CliKaggleClient
        kc = p.cfg["execution"]["kaggle"]
        client = _mock_client(a) or CliKaggleClient(kc.get("credentials_env", "RP_KAGGLE_CREDENTIALS"))
        _print(client.check_resources())
    return 0


def cmd_import(a):
    from . import provenance
    from .executors.manual import import_run
    from .experiments import create_run, validated_spec
    from .results import validate_run
    p = _p(a)
    spec = validated_spec(p, a.id)
    ds = None
    if spec.get("dataset"):
        from .datasets import require_valid
        ds = require_valid(p, spec["dataset"]["name"])
    rec = create_run(p, spec, a.seed, "manual", {**provenance.environment(p.root), "import": True}, ds)
    rec = import_run(p, rec, Path(a.metrics), [Path(x) for x in a.attach or []], a.by, a.note or "")
    v = validate_run(p, rec["run_id"])
    print(f"{rec['run_id']}: IMPORTED / {v['status']}")
    for i in v["issues"]:
        print(f"  [{i['severity']}] {i['check']}: {i['message']}")
    return 0


def cmd_runs(a):
    from .experiments import list_runs, load_run
    p = _p(a)
    if a.runs_cmd == "list":
        for r in list_runs(p, a.exp):
            print(f"{r['run_id']:58} {r['status']:10} {r['validation']['status']:12} {r.get('metrics')}")
    else:
        _print(load_run(p, a.run_id))
    return 0


def cmd_validate(a):
    from .results import validate_all
    p = _p(a)
    res = validate_all(p, a.exp)
    for rid, v in res.items():
        print(f"{rid}: {v['status']}")
        if a.verbose:
            for i in v["issues"]:
                print(f"    [{i['severity']}] {i['check']}: {i['message']}")
    return 0


def cmd_approve(a):
    from . import approvals
    from .experiments import config_sha256, validated_spec
    p = _p(a)
    spec = validated_spec(p, a.id)
    reasons = approvals.required_reasons(p, spec, a.backend, a.runs)
    item = approvals.grant(p, a.id, config_sha256(spec), a.backend, a.by, a.reason or "",
                           max_runs=a.runs, max_hours=a.max_hours)
    print(f"granted {item['id']} for {a.id} ({a.runs} run(s) on {a.backend}), bound to config "
          f"{item['config_sha256'][:16]}. Reasons approval was needed: {reasons or 'none (recorded anyway)'}")
    return 0


def cmd_approvals(a):
    from . import approvals
    p = _p(a)
    if a.appr_cmd == "list":
        for x in approvals.load(p):
            print(f"{x['id']} {x['status']:9} {x['experiment_id']} {x['backend']} runs {len(x.get('consumed_by', []))}/"
                  f"{x['max_runs']} by {x['granted_by']} at {x['granted_at']}")
    else:
        print("revoked" if approvals.revoke(p, a.approval_id) else "no active approval with that id")
    return 0


# ------------------------------------------------------------------ data

def cmd_data(a):
    from . import datasets
    from .util import read_yaml
    p = _p(a)
    if a.data_cmd == "register":
        if a.from_yaml:
            entry = read_yaml(a.from_yaml)
        else:
            files = []
            for f in a.file or []:
                path, _, split = f.partition(":")
                files.append({"path": path, **({"split": split} if split else {})})
            entry = {"name": a.name, "version": a.version, "synthetic": a.synthetic,
                     "source": {"kind": a.source_kind, "location": a.location or "",
                                "access_verified": a.access_verified},
                     "license": {"name": a.license, "redistribution_allowed": None},
                     "files": files, "target": a.target, "group_column": a.group_column,
                     "id_column": a.id_column}
        e = datasets.register(p, entry, replace=a.replace)
        print(f"registered {e['name']} v{e['version']} ({len(e['files'])} file(s)); fingerprint "
              f"{e['fingerprint']['combined'][:16]}; missing: {e['fingerprint']['missing'] or 'none'}")
        print(f"next: research data validate {e['name']}")
    elif a.data_cmd == "validate":
        names = [d["name"] for d in datasets.load_manifest(p)["datasets"]] if a.all else [a.name]
        worst = 0
        for n in names:
            r = datasets.validate_dataset(p, n)
            worst = max(worst, {"PASS": 0, "WARN": 0, "FAIL": 1}[r["status"]])
            print(f"{n}: {r['status']}  (data/validation/{n}.md)")
            for it in r["items"]:
                if it["level"] in ("FAIL", "WARN"):
                    print(f"  [{it['level']}] {it['check']}: {it['message']}")
        return worst
    elif a.data_cmd == "list":
        for d in datasets.load_manifest(p)["datasets"]:
            v = datasets.latest_validation(p, d["name"])
            print(f"{d['name']:20} v{d['version']:8} {v['status'] if v else 'NOT VALIDATED':14}"
                  f"{'SYNTHETIC' if d.get('synthetic') else ''}")
    return 0


# ------------------------------------------------------------------ analysis / reports

def cmd_analyze(a):
    from .analysis.compare import compare, summarize_experiment, write_summary
    p = _p(a)
    if not a.compare:
        s = summarize_experiment(p, a.ref, a.metric, a.allow_provisional)
        _print({"experiment": a.ref, "metric": a.metric, "descriptive": s["descriptive"],
                "warnings": s["warnings"], "excluded": s["excluded"]})
        return 0
    paired = None if a.paired_by == "none" else a.paired_by
    s = compare(p, a.ref, a.compare, a.metric, test=a.test, paired_by=paired,
                allow_provisional=a.allow_provisional, name=a.name)
    j, m = write_summary(p, s)
    print(f"wrote {j} and {m}")
    for c in s["comparisons"]:
        r = c["result"]
        print(f"  {a.ref} vs {c['other']}: test={r.get('test')} p={r.get('p_value')} "
              f"p_adj={r.get('p_adjusted')} -> {c['interpretation_guard']}")
    if a.plot:
        from .analysis.viz import plot_comparison
        out = p.path("analysis", "visualizations", s["name"] + ".png")
        plot_comparison(s, out)
        print(f"wrote {p.rel(out)} (+ provenance sidecar)")
    return 0


def cmd_report(a):
    from .experiments import list_specs
    from .reports import experiment_report
    p = _p(a)
    ids = [s["id"] for s in list_specs(p)] if a.all else [a.id]
    for i in ids:
        r = experiment_report(p, i)
        print(f"{i}: {r['markdown']} (+ {r['json']})")
    return 0


# ------------------------------------------------------------------ evidence / literature

def cmd_claim(a):
    from . import evidence
    p = _p(a)
    if a.claim_cmd == "add":
        src: dict[str, Any] = {"kind": a.source_kind}
        for k in ("experiment", "metric", "statistic", "file", "json_path"):
            if getattr(a, k):
                src[k] = getattr(a, k)
        if a.refs:
            src["references"] = a.refs
        c = {"id": a.id, "text": a.text, "type": a.type, "research_question": a.rq, "source": src,
             "stated_value": a.value, "tolerance": a.tolerance, "unit": a.unit,
             "analysis_method": a.method}
        if a.digits is not None:
            c["display_digits"] = a.digits
        evidence.add(p, c)
        print(f"added claim {a.id} (unverified). Run `research claim verify`.")
    elif a.claim_cmd == "verify":
        for c in evidence.verify_all(p):
            print(f"{c['id']:8} {c['status']:13} value={c.get('verified_value')}  {c.get('verification_notes')}")
    elif a.claim_cmd == "list":
        for c in evidence.load(p):
            print(f"{c['id']:8} {c['status']:13} [{c['type']}] {c['text']}")
    elif a.claim_cmd == "supersede":
        evidence.mark_superseded(p, a.id, a.by_claim, a.reason)
        print(f"{a.id} marked superseded (kept in the registry)")
    return 0


def cmd_lit(a):
    from . import literature as lit
    p = _p(a)
    if a.lit_cmd == "add":
        e = lit.add(p, {"key": a.key, "title": a.title,
                        "authors": [x.strip() for x in (a.authors or "").split(";") if x.strip()],
                        "year": a.year, "venue": a.venue, "doi": a.doi, "arxiv": a.arxiv, "url": a.url})
        print(f"added {e['key']} (unverified). Verify with `research lit verify {e['key']}`")
    elif a.lit_cmd == "import":
        added = lit.import_bibtex(p, Path(a.bibfile).read_text(encoding="utf-8"))
        print(f"imported {len(added)} reference(s), all unverified: {added}")
    elif a.lit_cmd == "verify":
        if a.manual:
            v = lit.verify_manual(p, a.key, a.evidence_url, a.by, a.note or "")
            print(f"{a.key}: {v['status']} ({v['method']})")
        else:
            keys = [r["key"] for r in lit.load(p)] if a.all else [a.key]
            for k in keys:
                v = lit.verify(p, k)
                print(f"{k}: {v['status']} {v.get('method') or ''} {v['note']} {v['mismatches'] or ''}")
    elif a.lit_cmd == "export":
        ok, total = lit.export_bibtex(p)
        print(f"wrote literature/references.bib with {ok} verified of {total} references")
    elif a.lit_cmd == "matrix":
        print(f"wrote literature/literature_matrix.csv ({lit.write_matrix(p)} rows)")
    elif a.lit_cmd == "review":
        lit.review_skeleton(p)
        print("wrote literature/literature_review.md")
    elif a.lit_cmd == "list":
        for r in lit.load(p):
            print(f"{r['key']:24} {r['verification']['status']:10} {r.get('year')} {r['title'][:70]}")
    return 0


# ------------------------------------------------------------------ iteration / progress

def cmd_propose(a):
    from .iteration import generate
    new = generate(_p(a))
    if not new:
        print("no new proposals (existing ones are unchanged, or no evidence gaps were detected)")
    for x in new:
        print(f"{x['id']} score={x['ranking']['score']:.2f} [{x['kind']}] {x['title']}")
        print(f"     why: {x['necessity']}")
    return 0


def cmd_proposals(a):
    from . import iteration
    p = _p(a)
    if a.prop_cmd == "list":
        items = [x for x in iteration.load(p) if not a.status or x["status"] == a.status]
        for x in sorted(items, key=lambda x: -x["ranking"]["score"]):
            print(f"{x['id']} {x['status']:9} score={x['ranking']['score']:.2f} [{x['kind']}] {x['title']}")
            if a.verbose:
                for k in ("learned", "uncertainty", "hypothesis", "necessity", "variables_changed",
                          "controlled", "possible_outcomes", "influence_on_research", "resources"):
                    print(f"     {k}: {x[k]}")
    else:
        x = iteration.decide(p, a.pid, a.prop_cmd == "approve", a.by, a.note or "")
        print(f"{x['id']} -> {x['status']} (decision logged)")
        if x["status"] == "approved" and (x.get("draft_spec") or {}).get("action") == "run":
            d = x["draft_spec"]
            print(f"suggested next command: research run {d['experiment']} --seeds "
                  + " ".join(map(str, d["seeds"])) + " --dry-run")
    return 0


def cmd_loop(a):
    from . import iteration
    p = _p(a)
    if a.loop_cmd == "status":
        _print(iteration.stopping_status(p))
    elif a.loop_cmd == "start":
        _print(iteration.start_iteration(p, a.by))
    elif a.loop_cmd == "close":
        _print(iteration.close_iteration(p, a.summary or ""))
    elif a.loop_cmd == "review":
        iteration.review(p, a.by, a.note or "")
        print("review recorded")
    return 0


def cmd_decision(a):
    from .progress import log_decision
    d = log_decision(_p(a), a.title, a.motivation, a.evidence, a.alternatives, a.consequences, a.by, a.kind)
    print(f"recorded {d['id']}")
    return 0


def cmd_hypothesis(a):
    from .progress import set_hypothesis
    set_hypothesis(_p(a), a.id, a.status, a.by, a.claims or [], a.note or "")
    print(f"{a.id} -> {a.status} (decision logged)")
    return 0


# ------------------------------------------------------------------ manuscript / journal

def cmd_manuscript(a):
    p = _p(a)
    if a.ms_cmd == "init":
        from .manuscript.draft import init_sections
        print("\n".join(init_sections(p)) or "all sections already exist")
    elif a.ms_cmd == "draft":
        from .manuscript.draft import draft
        for k, v in draft(p, a.section).items():
            print(f"{k}: {v}")
    elif a.ms_cmd == "build":
        from .manuscript.render import build
        m = build(p)
        print(f"wrote {m['output']}; claims used: {len(m['claims'])}; citations: {len(m['citations'])}")
    elif a.ms_cmd == "audit":
        from .manuscript.audit import run_audit
        r = run_audit(p)
        print(f"overall: {r['overall']}  submission-ready (automated criteria): "
              f"{'yes' if r['submission_ready'] else 'NO'}  counts: {r['counts']}")
        for i in r["findings"]:
            if i["status"] == "FAIL" or (a.verbose and i["status"] == "WARNING"):
                print(f"  {i['status']:7} [{i['category']}] {i['location']} {i['message']}")
        print("report: manuscript/audit/audit_report.md")
        return 0 if r["overall"] != "FAIL" else 1
    return 0


def cmd_journal(a):
    from .manuscript import journal
    p = _p(a)
    if a.j_cmd == "init":
        print(f"created {p.rel(journal.init_profile(p, a.name))}: fill it from the official guidelines")
    elif a.j_cmd == "check":
        r = journal.check(p, a.slug)
        for it in r["items"]:
            print(f"  [{'x' if it['ok'] else (' ' if it['ok'] is False else '?')}] {it['item']}: {it['detail']}")
        print("all formal requirements met" if r["all_met"] else "requirements NOT all met (or unknown)")
    elif a.j_cmd == "export":
        for w in journal.export(p, a.slug, a.format):
            print(w)
    return 0


def cmd_security(a):
    from .security import scan_paths
    root = Path(a.path or ".").resolve()
    f = scan_paths([root], root)
    for x in f:
        print(x)
    print(f"{len(f)} finding(s) (contents never shown)")
    return 1 if f else 0


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="research", description="Evidence-grounded research pipeline.")
    ap.add_argument("--version", action="version", version=f"research-engine {__version__}")
    ap.add_argument("--project", help="project directory (default: search upwards from cwd)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a new research project")
    s.add_argument("name"); s.add_argument("--domain"); s.add_argument("--dir"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)
    sub.add_parser("domains", help="list built-in domain adapters").set_defaults(fn=cmd_domains)
    sub.add_parser("check", help="validate all configuration files").set_defaults(fn=cmd_check)
    s = sub.add_parser("status", help="rebuild project status from files")
    s.add_argument("--write", action="store_true", help="also write PROGRESS.md and history views")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_status)

    s = sub.add_parser("exp", help="experiment specifications")
    es = s.add_subparsers(dest="exp_cmd", required=True)
    es.add_parser("list")
    x = es.add_parser("validate"); x.add_argument("id", nargs="?")
    x = es.add_parser("new"); x.add_argument("id"); x.add_argument("--title"); x.add_argument("--type")
    s.set_defaults(fn=cmd_exp)

    s = sub.add_parser("run", help="run an experiment (one run per seed)")
    s.add_argument("id"); s.add_argument("--backend", choices=["local", "kaggle"])
    s.add_argument("--seeds", type=int, nargs="+"); s.add_argument("--dry-run", action="store_true")
    s.add_argument("--allow-unvalidated", action="store_true",
                   help="run despite a missing/failed dataset validation (recorded; results become PROVISIONAL)")
    s.add_argument("--resume-from"); s.add_argument("--parallel", type=int, default=1)
    s.add_argument("--mock-remote", action="store_true", help="use the mock Kaggle client (demo only; never evidence)")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("remote", help="remote (Kaggle) runs")
    rs = s.add_subparsers(dest="remote_cmd", required=True)
    x = rs.add_parser("collect"); x.add_argument("--run", nargs="*"); x.add_argument("--mock-remote", action="store_true")
    x = rs.add_parser("resources"); x.add_argument("--mock-remote", action="store_true")
    s.set_defaults(fn=cmd_remote)

    s = sub.add_parser("import", help="import externally produced results as a run")
    s.add_argument("id"); s.add_argument("--metrics", required=True); s.add_argument("--attach", nargs="*")
    s.add_argument("--seed", type=int); s.add_argument("--by", required=True); s.add_argument("--note")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("runs", help="inspect run records")
    rs = s.add_subparsers(dest="runs_cmd", required=True)
    x = rs.add_parser("list"); x.add_argument("--exp")
    x = rs.add_parser("show"); x.add_argument("run_id")
    s.set_defaults(fn=cmd_runs)

    s = sub.add_parser("validate", help="validate run results")
    s.add_argument("--exp"); s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("approve", help="(researcher only) approve runs that require approval")
    s.add_argument("kind", choices=["run"]); s.add_argument("id")
    s.add_argument("--backend", default="local", choices=["local", "kaggle"])
    s.add_argument("--runs", type=int, default=1); s.add_argument("--by", required=True)
    s.add_argument("--reason"); s.add_argument("--max-hours", type=float)
    s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("approvals", help="list or revoke approvals")
    asub = s.add_subparsers(dest="appr_cmd", required=True)
    asub.add_parser("list")
    x = asub.add_parser("revoke"); x.add_argument("approval_id")
    s.set_defaults(fn=cmd_approvals)

    s = sub.add_parser("data", help="dataset registration and validation")
    ds = s.add_subparsers(dest="data_cmd", required=True)
    x = ds.add_parser("register")
    x.add_argument("--from-yaml"); x.add_argument("--name"); x.add_argument("--version", default="1.0")
    x.add_argument("--file", action="append", help="path[:split], repeatable")
    x.add_argument("--license", default="unknown"); x.add_argument("--source-kind", default="local")
    x.add_argument("--location"); x.add_argument("--target"); x.add_argument("--group-column")
    x.add_argument("--id-column"); x.add_argument("--synthetic", action="store_true")
    x.add_argument("--access-verified", action="store_true"); x.add_argument("--replace", action="store_true")
    x = ds.add_parser("validate"); x.add_argument("name", nargs="?"); x.add_argument("--all", action="store_true")
    ds.add_parser("list")
    s.set_defaults(fn=cmd_data)

    s = sub.add_parser("analyze", help="descriptive stats or comparison between experiments")
    s.add_argument("ref"); s.add_argument("--metric", required=True); s.add_argument("--compare", nargs="*")
    s.add_argument("--test", choices=["auto", "welch_t", "student_t", "paired_t", "mann_whitney",
                                      "wilcoxon", "permutation", "none"])
    s.add_argument("--paired-by", default="auto", choices=["auto", "seed", "none"])
    s.add_argument("--allow-provisional", action="store_true"); s.add_argument("--plot", action="store_true")
    s.add_argument("--name"); s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("report", help="generate experiment technical report(s)")
    s.add_argument("id", nargs="?"); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_report)

    s = sub.add_parser("claim", help="evidence registry")
    cs = s.add_subparsers(dest="claim_cmd", required=True)
    x = cs.add_parser("add")
    x.add_argument("--id", required=True); x.add_argument("--text", required=True)
    x.add_argument("--type", required=True, choices=["quantitative", "comparative", "statistical", "qualitative",
                                                    "methodological", "efficiency", "limitation", "literature", "novelty"])
    x.add_argument("--rq"); x.add_argument("--source-kind", required=True,
                                            choices=["runs_metric", "analysis", "artifact", "literature", "researcher"])
    x.add_argument("--experiment"); x.add_argument("--metric")
    x.add_argument("--statistic", choices=["mean", "median", "std", "min", "max", "n", "sum"])
    x.add_argument("--file"); x.add_argument("--json-path"); x.add_argument("--refs", nargs="*")
    x.add_argument("--value", type=float); x.add_argument("--tolerance", type=float)
    x.add_argument("--unit"); x.add_argument("--method"); x.add_argument("--digits", type=int)
    cs.add_parser("verify"); cs.add_parser("list")
    x = cs.add_parser("supersede"); x.add_argument("id"); x.add_argument("--by-claim"); x.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("lit", help="literature registry")
    ls = s.add_subparsers(dest="lit_cmd", required=True)
    x = ls.add_parser("add")
    for k in ("--key", "--title"):
        x.add_argument(k, required=True)
    x.add_argument("--authors", help="'Family, Given; Family, Given'"); x.add_argument("--year", type=int)
    x.add_argument("--venue"); x.add_argument("--doi"); x.add_argument("--arxiv"); x.add_argument("--url")
    x = ls.add_parser("import"); x.add_argument("bibfile")
    x = ls.add_parser("verify"); x.add_argument("key", nargs="?"); x.add_argument("--all", action="store_true")
    x.add_argument("--manual", action="store_true"); x.add_argument("--evidence-url"); x.add_argument("--by")
    x.add_argument("--note")
    for n in ("export", "matrix", "review", "list"):
        ls.add_parser(n)
    s.set_defaults(fn=cmd_lit)

    sub.add_parser("propose", help="generate evidence-based follow-up proposals").set_defaults(fn=cmd_propose)
    s = sub.add_parser("proposals", help="list / approve / reject proposals")
    ps = s.add_subparsers(dest="prop_cmd", required=True)
    x = ps.add_parser("list"); x.add_argument("--status")
    for n in ("approve", "reject"):
        x = ps.add_parser(n); x.add_argument("pid"); x.add_argument("--by", required=True); x.add_argument("--note")
    s.set_defaults(fn=cmd_proposals)

    s = sub.add_parser("loop", help="iteration loop and stopping criteria")
    lsub = s.add_subparsers(dest="loop_cmd", required=True)
    lsub.add_parser("status")
    x = lsub.add_parser("start"); x.add_argument("--by", required=True)
    x = lsub.add_parser("close"); x.add_argument("--summary")
    x = lsub.add_parser("review"); x.add_argument("--by", required=True); x.add_argument("--note")
    s.set_defaults(fn=cmd_loop)

    s = sub.add_parser("decision", help="record a research decision")
    ds2 = s.add_subparsers(dest="dec_cmd", required=True)
    x = ds2.add_parser("add")
    for k in ("--title", "--motivation", "--evidence", "--alternatives", "--consequences", "--by"):
        x.add_argument(k, required=True)
    x.add_argument("--kind", default="methodological")
    s.set_defaults(fn=cmd_decision)

    s = sub.add_parser("hypothesis", help="record a hypothesis verdict")
    hs = s.add_subparsers(dest="h_cmd", required=True)
    x = hs.add_parser("set"); x.add_argument("id")
    x.add_argument("--status", required=True, choices=["proposed", "supported", "refuted", "inconclusive", "withdrawn"])
    x.add_argument("--by", required=True); x.add_argument("--claims", nargs="*"); x.add_argument("--note")
    s.set_defaults(fn=cmd_hypothesis)

    s = sub.add_parser("manuscript", help="draft, build and audit the manuscript")
    ms = s.add_subparsers(dest="ms_cmd", required=True)
    ms.add_parser("init")
    x = ms.add_parser("draft"); x.add_argument("--section", nargs="*")
    ms.add_parser("build"); ms.add_parser("audit")
    s.set_defaults(fn=cmd_manuscript)

    s = sub.add_parser("journal", help="journal-specific preparation")
    js = s.add_subparsers(dest="j_cmd", required=True)
    x = js.add_parser("init"); x.add_argument("name")
    x = js.add_parser("check"); x.add_argument("slug")
    x = js.add_parser("export"); x.add_argument("slug")
    x.add_argument("--format", default="all", choices=["markdown", "latex", "docx", "pdf", "all"])
    s.set_defaults(fn=cmd_journal)

    s = sub.add_parser("security", help="secret scanning")
    ss = s.add_subparsers(dest="sec_cmd", required=True)
    x = ss.add_parser("scan"); x.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_security)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return int(args.fn(args) or 0)
    except ResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
