"""Dataset registration, fingerprinting and validation.

Field-independent by construction: tabular files (CSV/TSV) get generic quality checks;
measurement datasets get unit/range/metadata/time-continuity checks declared in the
manifest; anything else gets existence and fingerprint checks plus optional custom
validators (``module:function`` inside the project). A validation report must exist,
must not be FAIL, and must match the files' current fingerprint before an experiment
that uses the dataset may run.

Nothing is downloaded, generated or imputed here. Insufficient data is reported, never
padded.
"""

from __future__ import annotations

import csv
import importlib
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import config as cfgmod
from .errors import ConfigError, DatasetNotValidated
from .util import (atomic_write_text, fingerprint_paths, read_json, read_yaml, sha256_obj,
                   sha256_text, utc_now, write_json, write_yaml)

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "?", "-"}
TABULAR = {".csv": ",", ".tsv": "\t"}
LEVELS = ("PASS", "INFO", "WARN", "FAIL")


# ------------------------------------------------------------------ manifest IO

def manifest_path(project) -> Path:
    return project.path("data", "dataset_manifest.yaml")


def load_manifest(project) -> dict[str, Any]:
    data = read_yaml(manifest_path(project), {"datasets": []}) or {"datasets": []}
    data.setdefault("datasets", [])
    cfgmod.validate(data, "dataset_manifest", "data/dataset_manifest.yaml")
    return data


def save_manifest(project, data: dict[str, Any]) -> None:
    cfgmod.validate(data, "dataset_manifest", "data/dataset_manifest.yaml")
    write_yaml(manifest_path(project), data)


def find_dataset(project, name: str) -> dict[str, Any] | None:
    for d in load_manifest(project)["datasets"]:
        if d["name"] == name:
            return d
    return None


def fingerprint(project, entry: dict[str, Any]) -> dict[str, Any]:
    files = [project.path(f["path"]) for f in entry["files"]]
    existing = [p for p in files if p.exists()]
    per_file = fingerprint_paths(existing, project.root)
    return {"files": per_file, "combined": sha256_obj(per_file),
            "missing": [project.rel(p) for p in files if not p.exists()]}


def register(project, entry: dict[str, Any], replace: bool = False) -> dict[str, Any]:
    data = load_manifest(project)
    names = [d["name"] for d in data["datasets"]]
    if entry.get("name") in names and not replace:
        raise ConfigError(f"dataset {entry['name']!r} already registered (use --replace "
                          "for a corrected entry, or register a new version name)")
    entry = dict(entry)
    entry["fingerprint"] = fingerprint(project, entry)
    entry.setdefault("registered_at", utc_now())
    data["datasets"] = [d for d in data["datasets"] if d["name"] != entry["name"]] + [entry]
    save_manifest(project, data)
    return entry


# ------------------------------------------------------------------ table reading

def _read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    delim = TABULAR[path.suffix.lower()]
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=delim)
        rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _is_missing(v: str) -> bool:
    return v.strip().lower() in MISSING_TOKENS


def _to_float(v: str) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _numeric_columns(header: list[str], rows: list[list[str]]) -> dict[str, list[float]]:
    out = {}
    for j, col in enumerate(header):
        vals = [r[j] for r in rows if j < len(r) and not _is_missing(r[j])]
        nums = [_to_float(v) for v in vals]
        if vals and all(n is not None for n in nums):
            out[col] = [n for n in nums if n is not None]
    return out


# ------------------------------------------------------------------ validation

class _Report:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, level: str, check: str, message: str, **data: Any) -> None:
        assert level in LEVELS
        self.items.append({"level": level, "check": check, "message": message, **data})

    @property
    def status(self) -> str:
        levels = {i["level"] for i in self.items}
        return "FAIL" if "FAIL" in levels else "WARN" if "WARN" in levels else "PASS"


def _check_table(rep: _Report, label: str, header: list[str], rows: list[list[str]],
                 entry: dict[str, Any]) -> dict[str, Any]:
    n = len(rows)
    summary: dict[str, Any] = {"rows": n, "columns": len(header), "header": header}
    if n == 0:
        rep.add("FAIL", "rows", f"{label}: file has no data rows")
        return summary
    ragged = sum(1 for r in rows if len(r) != len(header))
    if ragged:
        rep.add("FAIL", "structure", f"{label}: {ragged} row(s) have a different field count than the header")

    # missing values
    missing = {}
    for j, col in enumerate(header):
        m = sum(1 for r in rows if j >= len(r) or _is_missing(r[j]))
        if m:
            missing[col] = m
    summary["missing"] = missing
    if missing:
        worst = max(missing.values()) / n
        rep.add("WARN" if worst > 0.05 else "INFO", "missing_values",
                f"{label}: missing values in {len(missing)} column(s); worst column {worst:.1%}",
                counts=missing)
    else:
        rep.add("PASS", "missing_values", f"{label}: no missing values")

    # duplicates (excluding the id column, which would hide them)
    id_col = entry.get("id_column")
    idx = [j for j, c in enumerate(header) if c != id_col]
    keys = Counter(tuple(r[j] for j in idx if j < len(r)) for r in rows)
    dups = sum(c - 1 for c in keys.values() if c > 1)
    summary["duplicate_rows"] = dups
    rep.add("WARN" if dups else "PASS", "duplicates",
            f"{label}: {dups} duplicate row(s)" if dups else f"{label}: no duplicate rows")

    # outliers (IQR rule) -- flagged, never removed
    numeric = _numeric_columns(header, rows)
    outliers = {}
    for col, vals in numeric.items():
        if len(vals) < 8 or col in (id_col, entry.get("target")):
            continue
        q = statistics.quantiles(vals, n=4)
        iqr = q[2] - q[0]
        if iqr == 0:
            continue
        lo, hi = q[0] - 1.5 * iqr, q[2] + 1.5 * iqr
        k = sum(1 for v in vals if v < lo or v > hi)
        if k:
            outliers[col] = k
    summary["outliers_iqr"] = outliers
    if outliers:
        rep.add("INFO", "outliers", f"{label}: IQR outliers flagged (not removed) in "
                f"{len(outliers)} column(s)", counts=outliers)

    # declared column checks: presence, units, ranges, allowed values, missingness
    for chk in entry.get("column_checks", []):
        col = chk["column"]
        if col not in header:
            if chk.get("required", True):
                rep.add("FAIL", "column_ranges", f"{label}: required column {col!r} is absent")
            continue
        j = header.index(col)
        vals = [r[j] for r in rows if j < len(r) and not _is_missing(r[j])]
        frac_missing = 1 - len(vals) / n
        if "max_missing_fraction" in chk and frac_missing > chk["max_missing_fraction"]:
            rep.add("FAIL", "missing_observations",
                    f"{label}: {col!r} is {frac_missing:.1%} missing (limit {chk['max_missing_fraction']:.1%})")
        if chk.get("min") is not None or chk.get("max") is not None:
            nums = [_to_float(v) for v in vals]
            bad_type = sum(1 for x in nums if x is None)
            if bad_type:
                rep.add("FAIL", "units", f"{label}: {col!r} has {bad_type} non-numeric value(s)")
            lo, hi = chk.get("min"), chk.get("max")
            out = sum(1 for x in nums if x is not None and
                      ((lo is not None and x < lo) or (hi is not None and x > hi)))
            unit = f" {chk['unit']}" if chk.get("unit") else ""
            rep.add("FAIL" if out else "PASS", "column_ranges",
                    f"{label}: {col!r} {out} value(s) outside [{lo}, {hi}]{unit}"
                    if out else f"{label}: {col!r} within [{lo}, {hi}]{unit}")
        if chk.get("allowed"):
            allowed = {str(a) for a in chk["allowed"]}
            bad = sorted({v for v in vals if v not in allowed})
            if bad:
                rep.add("FAIL", "label_validity",
                        f"{label}: {col!r} has {len(bad)} value(s) outside the allowed set",
                        examples=bad[:5])

    # target: label validity and distribution
    target = entry.get("target")
    if target:
        if target not in header:
            rep.add("FAIL", "label_validity", f"{label}: target column {target!r} is absent")
        else:
            j = header.index(target)
            labels = [r[j] for r in rows if j < len(r)]
            n_missing = sum(1 for v in labels if _is_missing(v))
            if n_missing:
                rep.add("FAIL", "label_validity", f"{label}: {n_missing} row(s) with a missing target")
            if target not in numeric or len(set(labels)) <= 20:
                dist = Counter(v for v in labels if not _is_missing(v))
                summary["class_distribution"] = dict(dist)
                if len(dist) >= 2:
                    ratio = max(dist.values()) / max(1, min(dist.values()))
                    rep.add("WARN" if ratio > 10 else "INFO", "class_distribution",
                            f"{label}: {len(dist)} classes, imbalance ratio {ratio:.1f}",
                            distribution=dict(dist))
                elif len(dist) == 1:
                    rep.add("WARN", "class_distribution", f"{label}: only one target value present")
            # target leakage: a feature identical to (or perfectly correlated with) the target
            for k, col in enumerate(header):
                if col in (target, id_col):
                    continue
                same = all(k < len(r) and r[k] == r[j] for r in rows)
                if same:
                    rep.add("FAIL", "leakage", f"{label}: column {col!r} is identical to the target")
                elif col in numeric and target in numeric and len(numeric[col]) == len(numeric[target]) > 2:
                    r = _corr(numeric[col], numeric[target])
                    if r is not None and abs(r) > 0.999:
                        rep.add("WARN", "leakage",
                                f"{label}: column {col!r} correlates |r|={abs(r):.4f} with the target")

    # time continuity
    tcol, interval = entry.get("time_column"), entry.get("expected_interval")
    if tcol and tcol in header and tcol in numeric:
        ts = numeric[tcol]
        nonmono = sum(1 for a, b in zip(ts, ts[1:]) if b <= a)
        if nonmono:
            rep.add("FAIL", "timestamp_continuity", f"{label}: {tcol!r} is not strictly increasing at {nonmono} point(s)")
        if interval:
            gaps = sum(1 for a, b in zip(ts, ts[1:]) if b - a > 1.5 * float(interval))
            rep.add("WARN" if gaps else "PASS", "missing_observations",
                    f"{label}: {gaps} gap(s) larger than 1.5 x expected interval" if gaps
                    else f"{label}: no gaps beyond 1.5 x expected interval")
    return summary


def _corr(a: list[float], b: list[float]) -> float | None:
    try:
        return statistics.correlation(a, b)
    except (statistics.StatisticsError, ValueError):
        return None


def validate_dataset(project, name: str) -> dict[str, Any]:
    entry = find_dataset(project, name)
    if entry is None:
        raise ConfigError(f"dataset {name!r} is not registered")
    rep = _Report()

    # provenance and access
    lic = entry.get("license", {})
    if str(lic.get("name", "")).strip().lower() in ("", "unknown", "none", "tbd"):
        rep.add("WARN", "license", "licence is unknown: usage and redistribution rights are unverified")
    else:
        rep.add("PASS", "license", f"licence recorded: {lic.get('name')}")
    if lic.get("redistribution_allowed") is not True:
        rep.add("INFO", "license", "redistribution not confirmed: do not publish or upload this data")
    src = entry.get("source", {})
    if src.get("kind") not in ("generated",) and not src.get("access_verified", False):
        rep.add("WARN", "access", "access/usage conditions not marked as verified (source.access_verified)")
    if entry.get("synthetic"):
        rep.add("INFO", "synthetic", "dataset is SYNTHETIC: results on it are not evidence about real phenomena")

    # metadata requirements (manifest-declared are mandatory; domain-suggested advisory)
    meta = entry.get("metadata", {}) or {}
    for key in entry.get("metadata_requirements", []):
        if meta.get(key) in (None, ""):
            rep.add("FAIL", "instrument_metadata", f"required metadata {key!r} is missing")
    for key in project.domain.metadata_requirements:
        if key not in entry.get("metadata_requirements", []) and meta.get(key) in (None, ""):
            rep.add("INFO", "instrument_metadata", f"domain suggests recording metadata {key!r}")

    # files
    fp = fingerprint(project, entry)
    for m in fp["missing"]:
        rep.add("FAIL", "files_exist", f"file missing: {m}")
    reg_fp = (entry.get("fingerprint") or {}).get("combined")
    if reg_fp and reg_fp != fp["combined"]:
        rep.add("WARN", "fingerprint", "files changed since registration (fingerprint differs); "
                "register a new version if the data was intentionally changed")

    split_rows: dict[str, list[tuple]] = defaultdict(list)
    split_groups: dict[str, set] = defaultdict(set)
    split_ids: dict[str, set] = defaultdict(set)
    summaries: dict[str, Any] = {}
    for f in entry["files"]:
        p = project.path(f["path"])
        if not p.exists():
            continue
        label = f"{f.get('split', 'all')}:{Path(f['path']).name}"
        if p.suffix.lower() in TABULAR:
            header, rows = _read_table(p)
            summaries[label] = _check_table(rep, label, header, rows, entry)
            split = f.get("split", "all")
            id_col, g_col = entry.get("id_column"), entry.get("group_column")
            idx = [j for j, c in enumerate(header) if c != id_col]
            split_rows[split].extend(tuple(r[j] for j in idx if j < len(r)) for r in rows)
            if g_col and g_col in header:
                gj = header.index(g_col)
                split_groups[split].update(r[gj] for r in rows if gj < len(r))
            if id_col and id_col in header:
                ij = header.index(id_col)
                split_ids[split].update(r[ij] for r in rows if ij < len(r))
            exp = (entry.get("expected_rows") or {}).get(split)
            if exp is not None and exp != len(rows):
                rep.add("FAIL", "sample_count", f"{label}: {len(rows)} rows, manifest expects {exp}")
        else:
            summaries[label] = {"bytes": p.stat().st_size, "note": "non-tabular: existence and fingerprint only"}

    # split integrity / leakage across splits
    splits = sorted(split_rows)
    if len(splits) > 1:
        for i, a in enumerate(splits):
            for b in splits[i + 1:]:
                overlap = len(set(split_rows[a]) & set(split_rows[b]))
                rep.add("FAIL" if overlap else "PASS", "split_integrity",
                        f"{overlap} identical row(s) shared by splits {a!r} and {b!r}"
                        if overlap else f"no identical rows shared by {a!r} and {b!r}")
                if split_groups[a] or split_groups[b]:
                    g = len(split_groups[a] & split_groups[b])
                    rep.add("FAIL" if g else "PASS", "leakage",
                            f"{g} group(s) of {entry.get('group_column')!r} appear in both {a!r} and {b!r}"
                            if g else f"no group overlap between {a!r} and {b!r}")
                if split_ids[a] or split_ids[b]:
                    k = len(split_ids[a] & split_ids[b])
                    if k:
                        rep.add("FAIL", "leakage", f"{k} id(s) appear in both {a!r} and {b!r}")
        fr = entry.get("split_fractions") or {}
        total = sum(len(v) for v in split_rows.values())
        for s, want in fr.items():
            got = len(split_rows.get(s, [])) / total if total else 0
            if abs(got - float(want)) > 0.02:
                rep.add("WARN", "split_integrity", f"split {s!r} is {got:.3f} of rows, manifest says {want}")

    # custom validators
    for spec in entry.get("custom_checks", []):
        _run_custom(project, entry, spec, rep)

    result = {
        "dataset": name,
        "version": entry.get("version"),
        "synthetic": bool(entry.get("synthetic")),
        "status": rep.status,
        "checked_at": utc_now(),
        "fingerprint": fp["combined"],
        "items": rep.items,
        "summaries": summaries,
    }
    out_dir = project.path("data", "validation")
    write_json(out_dir / f"{name}.json", result)
    atomic_write_text(out_dir / f"{name}.md", render_report(result, entry))
    _write_index(project)
    return result


def _run_custom(project, entry, spec: str, rep: _Report) -> None:
    mod_name, _, fn_name = spec.partition(":")
    root = str(project.root)
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        fn = getattr(importlib.import_module(mod_name), fn_name)
        for item in fn(project, entry) or []:
            rep.add(item.get("level", "WARN"), item.get("check", spec), item.get("message", ""))
    except Exception as exc:  # a broken validator is itself a failure, not a pass
        rep.add("FAIL", "custom_check", f"custom check {spec} raised {type(exc).__name__}: {exc}")
    finally:
        if added:
            sys.path.remove(root)


def render_report(result: dict[str, Any], entry: dict[str, Any]) -> str:
    lines = [f"# Dataset validation: {result['dataset']} v{result['version']}", ""]
    if result["synthetic"]:
        lines += ["> **SYNTHETIC DATA.** Results computed on this dataset are demonstrations, "
                  "not scientific evidence.", ""]
    lines += [f"- **Status:** {result['status']}", f"- **Checked:** {result['checked_at']}",
              f"- **Fingerprint:** `{result['fingerprint'][:16]}...`",
              f"- **Source:** {entry.get('source', {}).get('kind')} "
              f"{entry.get('source', {}).get('location', '')}",
              f"- **Licence:** {entry.get('license', {}).get('name')}", "",
              "| Level | Check | Finding |", "|---|---|---|"]
    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "PASS": 3}
    for it in sorted(result["items"], key=lambda i: order[i["level"]]):
        lines.append(f"| {it['level']} | {it['check']} | {it['message'].replace('|', '/')} |")
    lines += ["", "## File summaries", ""]
    for label, s in result["summaries"].items():
        lines.append(f"- `{label}`: " + ", ".join(
            f"{k}={v}" for k, v in s.items() if k in ("rows", "columns", "duplicate_rows", "bytes", "note")))
    if entry.get("known_limitations"):
        lines += ["", "## Known limitations", ""] + [f"- {x}" for x in entry["known_limitations"]]
    return "\n".join(lines) + "\n"


def _write_index(project) -> None:
    lines = ["# Dataset validation report", "", "| Dataset | Version | Status | Checked | Details |",
             "|---|---|---|---|---|"]
    for d in load_manifest(project)["datasets"]:
        r = read_json(project.path("data", "validation", f"{d['name']}.json"))
        if r:
            lines.append(f"| {d['name']} | {d.get('version')} | {r['status']} | {r['checked_at']} "
                         f"| [report](validation/{d['name']}.md) |")
        else:
            lines.append(f"| {d['name']} | {d.get('version')} | NOT VALIDATED | - | - |")
    atomic_write_text(project.path("data", "validation_report.md"), "\n".join(lines) + "\n")


def latest_validation(project, name: str) -> dict[str, Any] | None:
    return read_json(project.path("data", "validation", f"{name}.json"))


def require_valid(project, name: str) -> dict[str, Any]:
    """Gate used by the experiment engine. Returns dataset identity for the run record."""
    entry = find_dataset(project, name)
    if entry is None:
        raise DatasetNotValidated(f"dataset {name!r} is not registered")
    v = latest_validation(project, name)
    if v is None:
        raise DatasetNotValidated(f"dataset {name!r} has never been validated "
                                  f"(run `regor data validate {name}`)")
    if v["status"] == "FAIL":
        raise DatasetNotValidated(f"dataset {name!r} validation status is FAIL; see "
                                  f"data/validation/{name}.md")
    current = fingerprint(project, entry)["combined"]
    if current != v["fingerprint"]:
        raise DatasetNotValidated(f"dataset {name!r} changed since it was validated; re-validate it")
    return {"name": name, "version": entry.get("version"), "fingerprint": current,
            "validation_status": v["status"], "synthetic": bool(entry.get("synthetic"))}
