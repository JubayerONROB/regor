"""Result validation: decides whether a run may be used as evidence.

Validation status (separate from execution status):

  VALIDATED    every check passed; usable for claims
  PROVISIONAL  usable only with researcher review (e.g. code version not pinned,
               dataset validation overridden, suspicious duplicates)
  INCOMPLETE   missing outputs/metrics, cancelled, timed out or still running
  INVALID      failed execution, identity mismatch, tampered raw evidence,
               non-finite or out-of-range metrics, sample-count mismatch

Raw files are only read here. Re-running validation never changes raw evidence.
"""

from __future__ import annotations

import json
import math
from typing import Any

from . import datasets
from .experiments import config_sha256, list_runs, load_run, update_run
from .util import fingerprint_paths, read_json, utc_now

RANK = {"VALIDATED": 0, "PROVISIONAL": 1, "INCOMPLETE": 2, "INVALID": 3}


class _V:
    def __init__(self) -> None:
        self.status = "VALIDATED"
        self.issues: list[dict[str, str]] = []

    def flag(self, status: str, check: str, message: str) -> None:
        self.issues.append({"severity": status, "check": check, "message": message})
        if RANK[status] > RANK[self.status]:
            self.status = status

    def info(self, check: str, message: str) -> None:
        self.issues.append({"severity": "INFO", "check": check, "message": message})


def validate_run(project, run_id: str) -> dict[str, Any]:
    rec = load_run(project, run_id)
    spec = rec["config_snapshot"]
    v = _V()

    # identity
    if config_sha256(spec) != rec["config_sha256"]:
        v.flag("INVALID", "config_identity", "config snapshot does not match its recorded hash")
    snap = read_json(project.runs_meta / f"{run_id}.config.json")
    if snap is not None and snap != spec:
        v.flag("INVALID", "config_identity", "config snapshot file differs from the run record")
    if spec.get("id") != rec["experiment_id"]:
        v.flag("INVALID", "experiment_identity", "experiment id mismatch between record and snapshot")

    if (rec.get("remote") or {}).get("mock"):
        v.flag("INVALID", "execution_status",
               "MOCK remote execution: no computation was performed; never usable as evidence")

    # execution status
    st = rec["status"]
    if st == "FAILED":
        v.flag("INVALID", "execution_status", f"execution failed: {rec.get('error')}")
    elif st in ("CANCELLED", "TIMED_OUT"):
        v.flag("INCOMPLETE", "execution_status", f"execution {st.lower()}: {rec.get('error')}")
    elif st in ("CREATED", "RUNNING", "SUBMITTED"):
        v.flag("INCOMPLETE", "execution_status", f"run is still {st}")

    # raw evidence integrity
    raw = project.runs_raw / run_id
    recorded = rec.get("outputs") or {}
    current = fingerprint_paths([raw], raw) if raw.exists() else {}
    for f, h in recorded.items():
        if f not in current:
            v.flag("INVALID", "raw_integrity", f"raw output {f} has been deleted since the run")
        elif current[f] != h:
            v.flag("INVALID", "raw_integrity", f"raw output {f} was modified after the run")
    extra = sorted(set(current) - set(recorded))
    if extra and recorded:
        v.flag("PROVISIONAL", "raw_integrity", f"files added after the run: {extra[:5]}")

    # expected outputs and metrics
    for f in spec.get("expected_outputs", ["metrics.json"]):
        if f not in current:
            v.flag("INCOMPLETE", "expected_outputs", f"expected output {f} is missing")
    mfile = raw / "metrics.json"
    metrics: dict[str, Any] = {}
    n_samples = None
    if mfile.exists():
        try:
            data = json.loads(mfile.read_text(encoding="utf-8"))
            metrics = data.get("metrics", {}) or {}
            n_samples = data.get("n_samples")
            for k in data.get("nonfinite_metrics", []) or []:
                v.flag("INVALID", "numerical_validity", f"metric {k!r} was non-finite in the run")
        except (json.JSONDecodeError, AttributeError) as exc:
            v.flag("INVALID", "output_schema", f"metrics.json unreadable: {exc}")
    elif st in ("COMPLETED", "IMPORTED"):
        v.flag("INCOMPLETE", "output_schema", "metrics.json not produced")

    declared = {m["name"]: m for m in spec.get("metrics", [])}
    if mfile.exists():
        for name, m in declared.items():
            if name not in metrics:
                v.flag("INCOMPLETE", "metric_definitions", f"declared metric {name!r} is missing")
                continue
            val = metrics[name]
            if isinstance(val, bool) or not isinstance(val, (int, float)) or val is None:
                v.flag("INVALID", "numerical_validity", f"metric {name!r} is not numeric ({val!r})")
                continue
            if not math.isfinite(float(val)):
                v.flag("INVALID", "numerical_validity", f"metric {name!r} is not finite")
                continue
            rng = m.get("valid_range")
            if rng:
                lo, hi = rng
                if (lo is not None and val < lo) or (hi is not None and val > hi):
                    v.flag("INVALID", "numerical_validity",
                           f"metric {name!r}={val} outside declared valid range {rng}")
        undeclared = sorted(set(metrics) - set(declared))
        if undeclared:
            v.info("metric_definitions", f"undeclared metrics recorded (not usable in claims): {undeclared}")

    exp_n = spec.get("expected_samples")
    if exp_n is not None:
        if n_samples is None:
            v.flag("INCOMPLETE", "sample_count", f"expected {exp_n} samples; run did not report n_samples")
        elif int(n_samples) != int(exp_n):
            v.flag("INVALID", "sample_count", f"run reports {n_samples} samples, spec expects {exp_n}")

    # dataset identity
    ds = rec.get("dataset")
    if ds:
        if ds.get("validation_status") == "OVERRIDDEN":
            v.flag("PROVISIONAL", "dataset_identity", "dataset validation was overridden for this run")
        else:
            entry = datasets.find_dataset(project, ds["name"])
            if entry is None:
                v.flag("PROVISIONAL", "dataset_identity", f"dataset {ds['name']!r} is no longer registered")
            elif datasets.fingerprint(project, entry)["combined"] != ds.get("fingerprint"):
                v.info("dataset_identity", "dataset files changed since this run; the run "
                       "remains valid for the dataset version it recorded")
        if ds.get("synthetic"):
            v.info("dataset_identity", "SYNTHETIC dataset: demonstration only")

    # reproducibility metadata
    git = (rec.get("provenance") or {}).get("git", {})
    if git.get("commit") in (None, "unavailable"):
        v.flag("PROVISIONAL", "reproducibility", "code version is not pinned (no git commit recorded)")
    elif git.get("dirty"):
        v.info("reproducibility", "working tree was dirty; exact entry-point code is pinned by checksums")
    if rec["backend"] == "manual":
        v.info("provenance", "manually imported result; see import_provenance.json")

    # suspicious duplicates: identical metrics across different seeds of one experiment
    if metrics and rec.get("seed") is not None:
        for other in list_runs(project, rec["experiment_id"]):
            if (other["run_id"] != run_id and other.get("seed") != rec.get("seed")
                    and other.get("metrics") and other.get("metrics") == metrics
                    and other["config_sha256"] == rec["config_sha256"]):
                v.flag("PROVISIONAL", "duplicates",
                       f"metrics identical to run {other['run_id']} with a different seed; "
                       "the seed may be ignored by the code")
                break

    validation = {"status": v.status, "checked_at": utc_now(), "issues": v.issues}
    update_run(project, rec, validation=validation, metrics=metrics or rec.get("metrics", {}))
    return validation


def validate_all(project, experiment_id: str | None = None) -> dict[str, dict[str, Any]]:
    return {r["run_id"]: validate_run(project, r["run_id"])
            for r in list_runs(project, experiment_id)}


def usable_runs(project, experiment_id: str, allow_provisional: bool = False) -> list[dict[str, Any]]:
    ok = {"VALIDATED"} | ({"PROVISIONAL"} if allow_provisional else set())
    return [r for r in list_runs(project, experiment_id) if r["validation"]["status"] in ok]
