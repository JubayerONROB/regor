"""Experiment specifications and immutable run records.

An *experiment* is a YAML spec in ``experiments/configs/<ID>.yaml``. A *run* is one
execution of a spec with one seed. Every execution creates a new run record in
``runs/metadata/<run_id>.json`` -- even an identical configuration never reuses or
overwrites an earlier run.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from . import config as cfgmod
from .errors import ConfigError, ResearchError
from .util import read_json, read_yaml, sha256_obj, short_id, utc_now, utc_stamp, write_json

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "IMPORTED"}


# ------------------------------------------------------------------------ specs

def spec_path(project, exp_id: str) -> Path:
    return project.path("experiments", "configs", f"{exp_id}.yaml")


def list_specs(project) -> list[dict[str, Any]]:
    out = []
    for p in sorted(project.path("experiments", "configs").glob("*.yaml")):
        data = read_yaml(p)
        if isinstance(data, dict):
            out.append(data)
    return out


def load_spec(project, exp_id: str) -> dict[str, Any]:
    p = spec_path(project, exp_id)
    if not p.exists():
        raise ConfigError(f"experiment {exp_id!r} not found at {project.rel(p)}")
    spec = read_yaml(p)
    if not isinstance(spec, dict):
        raise ConfigError(f"{project.rel(p)} is not a mapping")
    if spec.get("id") != exp_id:
        raise ConfigError(f"{project.rel(p)}: id field {spec.get('id')!r} != file name {exp_id!r}")
    return spec


def check_spec(project, spec: dict[str, Any]) -> list[str]:
    """Schema errors plus cross-reference errors (RQs, hypotheses, datasets, deps)."""
    errors = cfgmod.schema_errors(spec, "experiment")
    rqs, hyps = set(project.question_ids()), set(project.hypothesis_ids())
    for rq in spec.get("research_questions", []):
        if rq not in rqs:
            errors.append(f"research_questions: {rq!r} is not defined in project.yaml")
    for h in spec.get("hypotheses", []):
        if h not in hyps:
            errors.append(f"hypotheses: {h!r} is not defined in project.yaml")
    known = {s.get("id") for s in list_specs(project)}
    for dep in spec.get("depends_on", []) + spec.get("compare_with", []):
        if dep not in known:
            errors.append(f"depends_on/compare_with: experiment {dep!r} does not exist")
    ds = spec.get("dataset")
    if ds:
        from .datasets import find_dataset
        if find_dataset(project, ds.get("name", "")) is None:
            errors.append(f"dataset: {ds.get('name')!r} is not registered in data/dataset_manifest.yaml")
    ep = spec.get("entrypoint")
    if ep:
        for f in ep.get("code_files", []):
            if not project.path(f).exists():
                errors.append(f"entrypoint.code_files: {f} does not exist")
    elif spec.get("compute", {}).get("backend", "local") != "manual":
        errors.append("entrypoint: required unless compute.backend is 'manual'")
    names = [m["name"] for m in spec.get("metrics", []) if isinstance(m, dict) and "name" in m]
    if len(names) != len(set(names)):
        errors.append("metrics: duplicate metric names")
    return errors


def validated_spec(project, exp_id: str) -> dict[str, Any]:
    spec = load_spec(project, exp_id)
    errs = check_spec(project, spec)
    if errs:
        raise ConfigError(f"experiment {exp_id} is invalid:\n  - " + "\n  - ".join(errs))
    return spec


def config_identity(spec: dict[str, Any]) -> dict[str, Any]:
    """The part of a spec that defines *what is computed* (hashed for identity).

    Bookkeeping fields (status, rationale prose, title) are excluded so that editing a
    description does not change identity; anything that changes results is included.
    """
    keep = ("id", "dataset", "method", "entrypoint", "parameters", "metrics",
            "expected_outputs", "expected_samples", "compute")
    ident = {k: copy.deepcopy(spec.get(k)) for k in keep}
    if ident.get("compute"):
        ident["compute"].pop("estimated_hours", None)
    return ident


def config_sha256(spec: dict[str, Any]) -> str:
    return sha256_obj(config_identity(spec))


# ------------------------------------------------------------------------ runs

def new_run_id(exp_id: str, seed: int | None) -> str:
    s = "na" if seed is None else str(seed)
    return f"{exp_id}__s{s}__{utc_stamp()}__{short_id(4)}"


def run_path(project, run_id: str) -> Path:
    return project.runs_meta / f"{run_id}.json"


def create_run(project, spec: dict[str, Any], seed: int | None, backend: str,
               provenance: dict[str, Any], dataset: dict[str, Any] | None,
               resume_from: str | None = None, approval_id: str | None = None,
               notes: list[str] | None = None) -> dict[str, Any]:
    run_id = new_run_id(spec["id"], seed)
    while run_path(project, run_id).exists():          # paranoia: never collide
        run_id = new_run_id(spec["id"], seed)
    rec = {
        "run_id": run_id,
        "experiment_id": spec["id"],
        "status": "CREATED",
        "validation": {"status": "UNVALIDATED", "checked_at": None, "issues": []},
        "config_sha256": config_sha256(spec),
        "config_snapshot": copy.deepcopy(spec),
        "seed": seed,
        "backend": backend,
        "dataset": dataset,
        "provenance": provenance,
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "runtime_seconds": None,
        "exit_code": None,
        "error": None,
        "outputs": {},
        "metrics": {},
        "remote": None,
        "resume_from": resume_from,
        "approval_id": approval_id,
        "notes": list(notes or []),
        "history": [{"at": utc_now(), "status": "CREATED"}],
    }
    cfgmod.validate(rec, "run_record", run_id)
    p = run_path(project, run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: a run record is born exactly once.
    with open(p, "x", encoding="utf-8") as fh:
        import json
        fh.write(json.dumps(rec, indent=2, default=str) + "\n")
    snap = project.runs_raw / run_id
    snap.mkdir(parents=True, exist_ok=False)
    write_json(project.runs_meta / f"{run_id}.config.json", rec["config_snapshot"])
    return rec


def load_run(project, run_id: str) -> dict[str, Any]:
    rec = read_json(run_path(project, run_id))
    if rec is None:
        raise ResearchError(f"run {run_id!r} not found")
    return rec


def update_run(project, rec: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Update mutable bookkeeping fields. Identity fields can never change."""
    frozen = {"run_id", "experiment_id", "config_sha256", "config_snapshot", "seed",
              "created_at", "dataset", "provenance"}
    bad = frozen & set(changes)
    if bad:
        raise ResearchError(f"refusing to modify immutable run fields: {sorted(bad)}")
    current = load_run(project, rec["run_id"])
    if current["status"] in TERMINAL and "status" in changes and changes["status"] != current["status"]:
        raise ResearchError(
            f"run {rec['run_id']} is already {current['status']}; start a new run instead")
    if "status" in changes and changes["status"] != current["status"]:
        current.setdefault("history", []).append({"at": utc_now(), "status": changes["status"]})
    current.update(changes)
    cfgmod.validate(current, "run_record", rec["run_id"])
    write_json(run_path(project, rec["run_id"]), current)
    rec.clear()
    rec.update(current)
    return rec


def list_runs(project, experiment_id: str | None = None) -> list[dict[str, Any]]:
    out = []
    if not project.runs_meta.exists():
        return out
    for p in sorted(project.runs_meta.glob("*.json")):
        if p.name.endswith(".config.json"):
            continue
        rec = read_json(p)
        if rec and (experiment_id is None or rec.get("experiment_id") == experiment_id):
            out.append(rec)
    return sorted(out, key=lambda r: r.get("created_at", ""))
