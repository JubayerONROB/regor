"""Evidence registry: claims, their resolution against artifacts, and contradictions.

A claim is the only way a result can enter the manuscript. ``verify_all`` recomputes
each claim's value from its declared source, so a claim is verified by the artifacts,
never by an assertion. Conflicts between claims are recorded on both claims and left
for the researcher -- they are never resolved automatically.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from . import config as cfgmod
from . import literature
from .errors import ConfigError, EvidenceError
from .experiments import list_runs
from .util import get_path, read_json, read_yaml, sha256_file, utc_now, write_yaml

SUPERIORITY = re.compile(r"(?i)\b(significant(ly)?|outperform\w*|superior|better than|improv\w+|beats?)\b")


def _path(project) -> Path:
    return project.path("evidence", "claims.yaml")


def load(project) -> list[dict[str, Any]]:
    data = read_yaml(_path(project), {"claims": []}) or {"claims": []}
    data.setdefault("claims", [])
    cfgmod.validate(data, "claims", "evidence/claims.yaml")
    return data["claims"]


def save(project, claims: list[dict[str, Any]]) -> None:
    ids = [c["id"] for c in claims]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ConfigError(f"duplicate claim ids: {sorted(dup)}")
    data = {"claims": claims}
    cfgmod.validate(data, "claims", "evidence/claims.yaml")
    write_yaml(_path(project), data)


def get(project, cid: str) -> dict[str, Any]:
    for c in load(project):
        if c["id"] == cid:
            return c
    raise EvidenceError(f"claim {cid!r} not found")


def add(project, claim: dict[str, Any]) -> dict[str, Any]:
    claims = load(project)
    if any(c["id"] == claim["id"] for c in claims):
        raise ConfigError(f"claim {claim['id']!r} already exists")
    claim = {"experiments": [], "limitations": [], "used_in": [], "contradicted_by": [],
             "stated_value": None, "tolerance": None, "unit": None, "metric_definition": None,
             "analysis_method": None, "research_question": None, **claim,
             "status": "unverified", "verified_value": None, "verified_at": None,
             "verification_notes": None}
    src = claim["source"]
    if src.get("experiment") and src["experiment"] not in claim["experiments"]:
        claim["experiments"].append(src["experiment"])
    claims.append(claim)
    save(project, claims)
    return claim


def _stat(values: list[float], name: str) -> float:
    x = np.asarray(values, dtype=float)
    return {"mean": lambda: float(x.mean()), "median": lambda: float(np.median(x)),
            "std": lambda: float(x.std(ddof=1)) if x.size > 1 else float("nan"),
            "min": lambda: float(x.min()), "max": lambda: float(x.max()),
            "n": lambda: float(x.size), "sum": lambda: float(x.sum())}[name]()


def resolve(project, claim: dict[str, Any]) -> tuple[str, float | None, str]:
    """(status, value, notes) for one claim, computed from its declared source."""
    src = claim["source"]
    kind = src["kind"]
    if kind == "runs_metric":
        exp, metric, stat = src.get("experiment"), src.get("metric"), src.get("statistic", "mean")
        if not exp or not metric:
            return "failed", None, "runs_metric source needs experiment and metric"
        runs = list_runs(project, exp)
        valid = [r for r in runs if r["validation"]["status"] == "VALIDATED"
                 and isinstance((r.get("metrics") or {}).get(metric), (int, float))]
        prov = [r for r in runs if r["validation"]["status"] == "PROVISIONAL"]
        if not valid:
            why = f"{len(prov)} provisional run(s) need review" if prov else "no validated runs"
            return ("needs_review" if prov else "failed"), None, f"{exp}/{metric}: {why}"
        val = _stat([r["metrics"][metric] for r in valid], stat)
        excluded = len(runs) - len(valid)
        note = (f"{stat} of {metric} over {len(valid)} validated run(s) of {exp}"
                + (f"; {excluded} run(s) not validated and excluded" if excluded else ""))
        return "verified", val, note
    if kind in ("analysis", "artifact"):
        f = src.get("file")
        if not f or not project.path(f).exists():
            return "failed", None, f"artifact {f!r} does not exist"
        p = project.path(f)
        if src.get("json_path"):
            try:
                val = get_path(read_json(p), src["json_path"])
            except (KeyError, IndexError, ValueError, TypeError):
                return "failed", None, f"{f}: path {src['json_path']!r} not found"
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                return "verified" if kind == "artifact" else "failed", None, \
                    f"{f}:{src['json_path']} = {val!r} (non-numeric)"
            return "verified", float(val), f"{f}:{src['json_path']} (sha256 {sha256_file(p)[:12]})"
        return "verified", None, f"artifact present: {f} (sha256 {sha256_file(p)[:12]})"
    if kind == "literature":
        refs = src.get("references") or []
        if not refs:
            return "failed", None, "literature claim cites no references"
        ok = literature.verified_keys(project)
        bad = [r for r in refs if r not in ok]
        if bad:
            return "failed", None, f"unverified reference(s): {bad}"
        return "verified", None, f"supported by verified reference(s) {refs}; content still needs human check"
    if kind == "researcher":
        return "needs_review", None, "researcher attestation: cannot be machine-verified"
    return "failed", None, f"unknown source kind {kind!r}"


def _tol(claim: dict[str, Any], v: float) -> float:
    t = claim.get("tolerance")
    return float(t) if t is not None else 1e-9 * max(1.0, abs(v))


def verify_all(project) -> list[dict[str, Any]]:
    claims = load(project)
    for c in claims:
        if c.get("status") == "superseded":
            continue
        status, val, note = resolve(project, c)
        notes = [note]
        if status == "verified" and val is not None and c.get("stated_value") is not None:
            if math.isnan(val) or abs(float(c["stated_value"]) - val) > _tol(c, val):
                status = "failed"
                notes.append(f"stated value {c['stated_value']} != computed {val:.6g}")
        if status == "verified" and c["type"] in ("comparative", "statistical") and SUPERIORITY.search(c["text"]):
            sig = _significance_from_source(project, c)
            if sig is False:
                status = "needs_review"
                notes.append("text asserts a difference/superiority but the linked analysis is not "
                             "significant after adjustment")
            elif sig is None and c["source"]["kind"] == "runs_metric":
                status = "needs_review"
                notes.append("superiority wording needs a linked statistical analysis (source kind 'analysis')")
        if c["type"] == "novelty":
            status = "needs_review" if status == "verified" else status
            notes.append("novelty claims always require researcher review of the documented search")
        c.update(status=status, verified_value=val, verified_at=utc_now(),
                 verification_notes="; ".join(n for n in notes if n))
        c["contradicted_by"] = []
    _contradictions(claims)
    save(project, claims)
    _write_index(project, claims)
    return claims


def _significance_from_source(project, c) -> bool | None:
    src = c["source"]
    if src["kind"] != "analysis" or not src.get("file"):
        return None
    data = read_json(project.path(src["file"]))
    if not isinstance(data, dict) or "comparisons" not in data:
        return None
    flags = [comp["result"].get("significant_after_adjustment") for comp in data["comparisons"]]
    if src.get("json_path", "").startswith("comparisons."):
        try:
            idx = int(src["json_path"].split(".")[1])
            return bool(flags[idx])
        except (ValueError, IndexError):
            return None
    return all(bool(f) for f in flags) if flags else None


def _contradictions(claims: list[dict[str, Any]]) -> None:
    def key(c):
        s = c["source"]
        return (s.get("kind"), s.get("experiment"), s.get("metric"), s.get("statistic"),
                s.get("file"), s.get("json_path"))
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            if a.get("status") == "superseded" or b.get("status") == "superseded":
                continue
            if key(a) == key(b) and a.get("stated_value") is not None and b.get("stated_value") is not None:
                if abs(float(a["stated_value"]) - float(b["stated_value"])) > _tol(a, float(a["stated_value"])):
                    for x, y in ((a, b), (b, a)):
                        x["contradicted_by"].append(y["id"])
                        if x["status"] == "verified":
                            x["status"] = "needs_review"
                        x["verification_notes"] = (x.get("verification_notes") or "") + \
                            f"; contradicts {y['id']} (same source, different stated value)"


def _write_index(project, claims) -> None:
    index = []
    for c in claims:
        runs = []
        for e in c.get("experiments", []):
            runs += [r["run_id"] for r in list_runs(project, e) if r["validation"]["status"] == "VALIDATED"]
        index.append({"claim": c["id"], "status": c["status"], "type": c["type"],
                      "research_question": c.get("research_question"),
                      "experiments": c.get("experiments", []), "validated_runs": runs,
                      "artifact": c["source"].get("file"), "used_in": c.get("used_in", []),
                      "contradicted_by": c.get("contradicted_by", [])})
    write_yaml(project.path("evidence", "evidence_index.yaml"), {"generated_at": utc_now(), "index": index})


def mark_superseded(project, cid: str, by: str | None, reason: str) -> None:
    claims = load(project)
    for c in claims:
        if c["id"] == cid:
            c["status"] = "superseded"
            c["verification_notes"] = f"superseded{' by ' + by if by else ''}: {reason}"
    save(project, claims)


def format_value(claim: dict[str, Any], digits: int | None = None) -> str:
    v = claim.get("verified_value")
    if v is None:
        return ""
    d = digits if digits is not None else claim.get("display_digits", 3)
    if float(v).is_integer() and abs(v) < 1e15 and claim["source"].get("statistic") in ("n", "sum"):
        s = str(int(v))
    elif v != 0 and abs(v) < 0.5 * 10 ** (-d):
        # fixed-point would print 0.000 and hide the value (e.g. small p-values)
        s = f"{v:.{max(d - 1, 1)}e}"
    else:
        s = f"{v:.{d}f}"
    return s + (f" {claim['unit']}" if claim.get("unit") else "")
