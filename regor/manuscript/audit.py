"""Manuscript audit: numerical, claim-evidence, reference, methodology, language.

Status per finding and overall:
  PASS     supported by verified evidence
  WARNING  evidence exists but needs researcher review
  FAIL     unsupported, contradictory, unverifiable or inconsistent

A manuscript is "submission-ready" only if the overall status is PASS. Even then, the
report ends with a human-review checklist: an automated audit is a quality-control
mechanism, not proof that the manuscript is error-free.
"""

from __future__ import annotations

import bisect
import re
from collections import Counter
from typing import Any

from .. import evidence, literature
from ..experiments import config_identity, list_runs, list_specs, load_spec
from ..errors import ConfigError
from ..progress import decisions
from ..util import atomic_write_text, get_path, read_json, sha256_obj, utc_now, write_json
from . import markers as M

OVERSTATEMENT = [
    (re.compile(r"(?i)\bprov(e|es|ed|en)\b"), "'prove' overstates empirical evidence"),
    (re.compile(r"(?i)\bstate[- ]of[- ]the[- ]art\b"), "state-of-the-art claim needs a fair, cited comparison"),
    (re.compile(r"(?i)\b(the )?first (to|work|study|method|approach)\b"), "priority claim requires a documented, scoped search"),
    (re.compile(r"(?i)\bnovel(ty)?\b"), "novelty wording must be qualified by the documented search"),
    (re.compile(r"(?i)\b(unprecedented|groundbreaking|revolutionary|breakthrough|remarkabl[ey])\b"), "promotional language"),
    (re.compile(r"(?i)\b(guarantee[sd]?|definitive(ly)?|conclusively|undeniabl[ey])\b"), "certainty not supported by finite experiments"),
    (re.compile(r"(?i)\bgenerali[sz](e|es|ation|able)\b"), "generalisation must be scoped to evaluated conditions"),
]
SIGNIFICANT = re.compile(r"(?i)\bsignificant(ly)?\b")
COMPARATIVE = re.compile(r"(?i)\b(outperform\w*|better than|superior|beats?|surpass\w*|improv(es|ed|ement) over)\b")
PRIOR_WORK = re.compile(r"(?i)\b(et al\.|previous (work|studies|research)|prior (work|studies)|has been shown|"
                        r"have shown|it is known|studies show)\b")


class Findings:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, status: str, category: str, message: str, location: str = "", **extra: Any) -> None:
        self.items.append({"status": status, "category": category, "message": message,
                           "location": location, **extra})

    @property
    def overall(self) -> str:
        s = {i["status"] for i in self.items}
        return "FAIL" if "FAIL" in s else "WARNING" if "WARNING" in s else "PASS"


def _line_index(text: str):
    starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
    return lambda pos: bisect.bisect_right(starts, pos)


def _blank(text: str, rx: re.Pattern) -> str:
    return rx.sub(lambda m: " " * len(m.group(0)), text)


def _decimals(lit: str) -> int:
    return len(lit.split(".")[1]) if "." in lit else 0


def _literal_matches(lit: str, pct: bool, value: float, unit: str | None) -> bool:
    x = float(lit)
    d = _decimals(lit)
    cands = [value]
    if pct and (unit or "").strip() != "%":
        cands.append(value * 100)          # 0.153 -> 15.3 %
    return any(abs(x - round(c, d)) <= 0.5 * 10 ** (-d) + 1e-12 for c in cands)


def audit_text(project, text: str, section: str, F: Findings, ctx: dict[str, Any]) -> None:
    claims, refs = ctx["claims"], ctx["refs"]
    results_like = section in ctx["results_sections"]
    clean = M.strip_noncontent(text)
    line_of = _line_index(clean)

    def loc(pos):
        return f"{section}:{line_of(pos)}"

    for m in M.PLACEHOLDER.finditer(clean):
        F.add("FAIL", "placeholder", f"unresolved placeholder [{m.group(1)[:60]}]", loc(m.start()))

    def check_claim(cid, pos, kind):
        c = claims.get(cid)
        ctx["used"].setdefault(cid, []).append(loc(pos))
        if c is None:
            F.add("FAIL", "claim_evidence", f"{kind} references unknown claim {cid}", loc(pos)); return None
        st = c["status"]
        if st == "verified":
            if c.get("contradicted_by"):
                F.add("WARNING", "claim_evidence", f"claim {cid} is contradicted by {c['contradicted_by']}", loc(pos))
            else:
                F.add("PASS", "claim_evidence", f"claim {cid} verified", loc(pos))
        elif st == "needs_review":
            F.add("WARNING", "claim_evidence", f"claim {cid} needs researcher review: {c.get('verification_notes')}", loc(pos))
        else:
            F.add("FAIL", "claim_evidence", f"claim {cid} is {st}: {c.get('verification_notes')}", loc(pos))
        return c

    for m in M.CLAIM.finditer(clean):
        c = check_claim(m.group(1), m.start(), "value marker")
        if c is not None and c["status"] == "verified" and c.get("verified_value") is None:
            F.add("FAIL", "claim_evidence", f"claim {c['id']} has no numeric value; use {{{{claimtext:...}}}}", loc(m.start()))
    for m in M.CLAIMTEXT.finditer(clean):
        check_claim(m.group(1), m.start(), "text marker")
    for m in M.LITERAL_CLAIM.finditer(clean):
        c = check_claim(m.group(3), m.start(), "annotated number")
        if c is not None and c["status"] in ("verified", "needs_review"):
            if c.get("verified_value") is None:
                F.add("FAIL", "numerical", f"number {m.group(1)} is annotated with claim {c['id']}, which has no value", loc(m.start()))
            elif not _literal_matches(m.group(1), bool(m.group(2)), float(c["verified_value"]), c.get("unit")):
                F.add("FAIL", "numerical", f"number {m.group(1)}{(m.group(2) or '').strip()} does not match claim "
                      f"{c['id']} verified value {c['verified_value']:.6g}", loc(m.start()))
            else:
                F.add("PASS", "numerical", f"number {m.group(1)} matches claim {c['id']}", loc(m.start()))
    for m in M.SPEC.finditer(clean):
        try:
            get_path(load_spec(project, m.group(1)), m.group(2))
            F.add("PASS", "methodology", f"config value {m.group(1)}:{m.group(2)} resolves", loc(m.start()))
            ctx["spec_refs"].add(m.group(1))
        except (KeyError, IndexError, ValueError, ConfigError):
            F.add("FAIL", "methodology", f"config reference {m.group(1)}:{m.group(2)} does not resolve", loc(m.start()))
    for m in M.PROJECT.finditer(clean):
        try:
            get_path(project.cfg, m.group(1))
        except (KeyError, IndexError, ValueError):
            F.add("FAIL", "methodology", f"project reference {m.group(1)} does not resolve", loc(m.start()))
    for m in M.DATASET.finditer(clean):
        from ..datasets import find_dataset
        entry = find_dataset(project, m.group(1))
        try:
            if entry is None:
                raise KeyError(m.group(1))
            get_path(entry, m.group(2))
        except (KeyError, IndexError, ValueError):
            F.add("FAIL", "methodology", f"dataset reference {m.group(1)}:{m.group(2)} does not resolve", loc(m.start()))
    for m in M.TABLE.finditer(clean):
        p = project.path(m.group(1).strip())
        s = read_json(p)
        if not s or "sha256" not in s:
            F.add("FAIL", "tables", f"table source {m.group(1)} missing or not a comparison summary", loc(m.start()))
        else:
            body = {k: v for k, v in s.items() if k not in ("created_at", "sha256")}
            if sha256_obj(body) != s["sha256"]:
                F.add("FAIL", "tables", f"table source {m.group(1)} was edited after generation (hash mismatch)", loc(m.start()))
            else:
                F.add("PASS", "tables", f"table generated from {m.group(1)}", loc(m.start()))
                ctx["table_exps"].update([s["reference"]["experiment"]] + [c["other"] for c in s["comparisons"]])
    for m in M.FIGURE.finditer(clean):
        path = m.group(1).strip()
        prov = read_json(project.path(path).with_suffix(".provenance.json"))
        if not project.path(path).exists() or prov is None:
            F.add("FAIL", "figures", f"figure {path} missing or has no provenance sidecar", loc(m.start()))
            continue
        src = read_json(project.path("analysis", "comparisons", prov["source_summary"] + ".json"))
        if not src or src.get("sha256") != prov.get("source_summary_sha256"):
            F.add("WARNING", "figures", f"figure {path} may be stale: its source summary changed", loc(m.start()))
        else:
            F.add("PASS", "figures", f"figure {path} traceable to {prov['source_summary']}", loc(m.start()))
    for m in M.MD_IMAGE.finditer(clean):
        F.add("WARNING", "figures", f"raw image {m.group(1)} has no provenance; use {{{{figure:...}}}}", loc(m.start()))
    for m in M.CITE.finditer(clean):
        for k in [x.strip().lstrip("@") for x in m.group(1).split(";")]:
            ctx["cited"].add(k)
            r = refs.get(k)
            if r is None:
                F.add("FAIL", "references", f"citation [@{k}] is not in the reference registry (possibly nonexistent)", loc(m.start()))
            elif r["verification"]["status"] != "verified":
                F.add("FAIL", "references", f"citation [@{k}] is {r['verification']['status']}: "
                      f"{r['verification'].get('note')}", loc(m.start()))
            else:
                F.add("PASS", "references", f"citation [@{k}] verified ({r['verification']['method']})", loc(m.start()))

    # bare numbers: blank out everything that legitimately contains digits
    scan = clean
    for rx in (M.LITERAL_CLAIM, M.ANY_MARKER, M.CITE, M.MD_LINK_URL, M.IDENTIFIER, M.HEADING_NUM, M.LIST_ENUM,
               M.PLACEHOLDER):
        scan = _blank(scan, rx)
    for m in M.NUMBER.finditer(scan):
        tok = m.group(0).strip()
        if M.YEAR.match(tok):
            continue
        if results_like:
            F.add("FAIL", "numerical", f"unsupported number '{tok}' in a results-bearing section "
                  f"(use {{{{claim:ID}}}} or '{tok} [claim:ID]')", loc(m.start()))
        else:
            F.add("WARNING", "numerical", f"number '{tok}' is not linked to evidence or configuration "
                  "(use {{spec:...}}, {{claim:...}} or justify)", loc(m.start()))

    # sentence-level language checks
    for sm in re.finditer(r"[^.!?\n][^.!?]*[.!?]?", clean):
        sent = sm.group(0)
        pos = sm.start()
        sent_claims = [claims.get(x) for x in
                       [c.group(1) for c in M.CLAIM.finditer(sent)] + [c.group(1) for c in M.CLAIMTEXT.finditer(sent)] +
                       [c.group(3) for c in M.LITERAL_CLAIM.finditer(sent)]]
        sent_claims = [c for c in sent_claims if c]
        for rx, why in OVERSTATEMENT:
            if rx.search(sent):
                novelty_ok = any(c["type"] == "novelty" and c["status"] in ("verified", "needs_review") for c in sent_claims)
                if "novel" in why or "priority" in why:
                    F.add("WARNING" if novelty_ok else "FAIL", "overstatement", f"{why}: \"{sent.strip()[:90]}\"", loc(pos))
                else:
                    F.add("WARNING", "overstatement", f"{why}: \"{sent.strip()[:90]}\"", loc(pos))
        if SIGNIFICANT.search(sent):
            if not any(c["type"] == "statistical" and c["status"] == "verified" for c in sent_claims):
                F.add("FAIL" if results_like else "WARNING", "statistics",
                      f"'significant' without a verified statistical claim in the sentence: \"{sent.strip()[:90]}\"", loc(pos))
        if COMPARATIVE.search(sent):
            if not sent_claims:
                F.add("FAIL", "comparison", f"comparative claim without evidence: \"{sent.strip()[:90]}\"", loc(pos))
            elif not any(c["type"] in ("comparative", "statistical") for c in sent_claims):
                F.add("WARNING", "comparison", f"comparative wording supported only by non-comparative claims: "
                      f"\"{sent.strip()[:90]}\"", loc(pos))
        if PRIOR_WORK.search(sent) and not M.CITE.search(sent):
            F.add("WARNING", "references", f"statement about prior work without a citation: \"{sent.strip()[:90]}\"", loc(pos))


def audit_methodology(project, F: Findings, exps: set[str]) -> None:
    specs = {s["id"]: s for s in list_specs(project)}
    dlog = " ".join(str(d) for d in decisions(project))
    for eid in sorted(exps):
        s = specs.get(eid)
        if s is None:
            F.add("FAIL", "methodology", f"experiment {eid} used by the manuscript has no spec")
            continue
        runs = [r for r in list_runs(project, eid) if r["validation"]["status"] == "VALIDATED"]
        hashes = {r["config_sha256"] for r in runs}
        if len(hashes) > 1:
            F.add("INFO" if eid in dlog else "WARNING", "methodology",
                  f"{eid}: validated runs use {len(hashes)} different configurations"
                  + (" (documented in decision log)" if eid in dlog else "; document the protocol change"))
        cks = {sha256_obj((r.get("provenance") or {}).get("code_checksums", {})) for r in runs}
        if len(cks) > 1:
            F.add("WARNING", "methodology", f"{eid}: entry-point code changed between validated runs")
        if runs and runs[0]["config_snapshot"] != s:
            if config_identity(runs[0]["config_snapshot"]) != config_identity(s):
                F.add("FAIL", "methodology", f"{eid}: the current spec differs from what the runs executed; "
                      "the manuscript would describe a protocol that was not run")
        for other in s.get("compare_with", []):
            o = specs.get(other)
            if not o:
                continue
            if (o.get("dataset") or {}).get("name") != (s.get("dataset") or {}).get("name") or \
                    (o.get("dataset") or {}).get("version") != (s.get("dataset") or {}).get("version"):
                F.add("FAIL", "methodology", f"{eid} vs {other}: different datasets/versions, comparison is unfair")
            mo = {m["name"]: (m.get("direction"), m.get("unit", ""), m.get("definition", "")) for m in o.get("metrics", [])}
            for m in s.get("metrics", []):
                if m["name"] in mo and mo[m["name"]] != (m.get("direction"), m.get("unit", ""), m.get("definition", "")):
                    F.add("FAIL", "methodology", f"{eid} vs {other}: metric {m['name']} defined differently")
        if s.get("type") == "ablation":
            base = (s.get("depends_on") or s.get("compare_with") or [None])[0]
            b = specs.get(base) if base else None
            if b:
                diffs = _leaf_diffs({"m": s.get("method"), "p": s.get("parameters")},
                                    {"m": b.get("method"), "p": b.get("parameters")})
                if len(diffs) != 1:
                    F.add("WARNING", "methodology", f"ablation {eid} differs from {base} in {len(diffs)} settings "
                          f"({diffs[:5]}); an ablation should isolate one variable")
                else:
                    F.add("PASS", "methodology", f"ablation {eid} isolates {diffs[0]}")


def _leaf_diffs(a, b, prefix=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _leaf_diffs(a.get(k), b.get(k), f"{prefix}.{k}" if prefix else k)
        return out
    return [] if a == b else [prefix]


def run_audit(project) -> dict[str, Any]:
    F = Findings()
    claims = {c["id"]: c for c in evidence.load(project)}
    refs = {r["key"]: r for r in literature.load(project)}
    ctx = {"claims": claims, "refs": refs, "used": {}, "cited": set(), "spec_refs": set(),
           "table_exps": set(), "results_sections": set(project.cfg["manuscript"]["results_sections"])}
    files = M.section_files(project)
    if not files:
        F.add("FAIL", "structure", "no manuscript sections found (regor manuscript init)")
    present = {M.section_name(p) for p in files}
    for s in project.cfg["manuscript"]["sections"]:
        if s not in present:
            F.add("FAIL", "structure", f"configured section {s!r} is missing")
    for p in files:
        audit_text(project, p.read_text(encoding="utf-8"), M.section_name(p), F, ctx)

    exps = set(ctx["spec_refs"]) | set(ctx["table_exps"])
    for cid in ctx["used"]:
        if cid in claims:
            exps.update(claims[cid].get("experiments", []))
    audit_methodology(project, F, exps)

    for cid, c in claims.items():
        if c["status"] == "superseded" and cid in ctx["used"]:
            F.add("FAIL", "claim_evidence", f"superseded claim {cid} is used in the manuscript")
        if c["status"] == "verified" and cid not in ctx["used"]:
            F.add("INFO", "claim_evidence", f"verified claim {cid} is not used in the manuscript")
    decl = project.cfg["manuscript"]["declarations"]
    for k, v in decl.items():
        if not v:
            F.add("WARNING", "declarations", f"declaration '{k}' not supplied in project.yaml "
                  "(researcher input; never inferred)")

    table = []
    for cid, locs in sorted(ctx["used"].items()):
        c = claims.get(cid)
        table.append({"claim": cid, "text": c["text"] if c else "(unknown)",
                      "status": c["status"] if c else "missing",
                      "evidence": c["source"] if c else None,
                      "verified_value": c.get("verified_value") if c else None,
                      "contradicted_by": c.get("contradicted_by", []) if c else [],
                      "locations": locs})
    overall = F.overall
    counts = Counter(i["status"] for i in F.items)
    report = {"generated_at": utc_now(), "overall": overall,
              "submission_ready": overall == "PASS", "counts": dict(counts),
              "findings": F.items, "claim_evidence_table": table,
              "citations": sorted(ctx["cited"])}
    write_json(project.path("manuscript", "audit", "audit_report.json"), report)
    atomic_write_text(project.path("manuscript", "audit", "audit_report.md"), render_report(report))
    return report


HUMAN_CHECKLIST = [
    "Read every cited paper section that supports each related-work statement.",
    "Re-derive at least the headline numbers from raw outputs by hand.",
    "Confirm the methodology section matches the code that produced the validated runs.",
    "Confirm that no failed, excluded or unfavourable run was omitted without a stated reason.",
    "Confirm that statistical tests match the design (paired vs independent, corrections).",
    "Confirm limitations and threats to validity are complete and honest.",
    "Confirm all declarations (funding, conflicts, ethics, data availability, contributions) are true.",
    "Confirm journal-specific requirements against the official author guidelines.",
    "Obtain approval from all co-authors before submission.",
]


def render_report(r: dict[str, Any]) -> str:
    L = [f"# Manuscript audit report", "", f"- Generated: {r['generated_at']}",
         f"- **Overall: {r['overall']}**",
         f"- Submission-ready (automated criteria only): **{'yes' if r['submission_ready'] else 'NO'}**",
         f"- Findings: {r['counts']}", ""]
    order = {"FAIL": 0, "WARNING": 1, "INFO": 2, "PASS": 3}
    for status in ("FAIL", "WARNING"):
        items = [i for i in r["findings"] if i["status"] == status]
        L += [f"## {status} ({len(items)})", ""]
        L += [f"- [{i['category']}] {i['location']} {i['message']}" for i in items] or ["- none"]
        L.append("")
    L += ["## Claim-to-evidence table", "", "| Claim | Status | Value | Evidence | Contradicted by | Locations |",
          "|---|---|---|---|---|---|"]
    for t in r["claim_evidence_table"]:
        ev = t["evidence"] or {}
        evs = ev.get("kind", "") + ":" + str(ev.get("experiment") or ev.get("file") or ev.get("references") or "")
        L.append(f"| {t['claim']} | {t['status']} | {t['verified_value']} | {evs} | "
                 f"{', '.join(t['contradicted_by']) or '-'} | {', '.join(t['locations'][:4])} |")
    passes = sum(1 for i in r["findings"] if i["status"] == "PASS")
    L += ["", f"## PASS items: {passes} (see audit_report.json)", "",
          "## Human review checklist (required regardless of automated status)", ""]
    L += [f"- [ ] {x}" for x in HUMAN_CHECKLIST]
    L += ["", "_This audit is automated quality control, not proof of correctness._"]
    return "\n".join(L) + "\n"
