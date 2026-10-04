"""Experiment orchestration: preflight gates, dry-run plans, dispatch, collection.

Preflight (all must pass before any run record is created):
  1. the spec is schema-valid and its cross-references resolve;
  2. the dataset (if any) has a passing, up-to-date validation report;
  3. the requested device exists (no silent CPU fallback for a GPU experiment);
  4. the compute budget in project.yaml is not exhausted;
  5. a researcher approval exists if the approval rules require one.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import approvals, datasets, provenance
from .errors import ConfigError, DatasetNotValidated, ExecutionError, ResearchError
from .experiments import create_run, config_sha256, list_runs, load_run, validated_spec
from .executors.base import Executor
from .executors.local import LocalExecutor
from .results import validate_run
from .util import sha256_file


def make_executor(project, backend: str, kaggle_client=None) -> Executor:
    if backend == "local":
        return LocalExecutor(project.cfg["execution"].get("default_timeout_hours"))
    if backend == "kaggle":
        from .executors.kaggle import CliKaggleClient, KaggleExecutor
        kcfg = project.cfg["execution"]["kaggle"]
        if not kcfg.get("enabled") and kaggle_client is None:
            raise ConfigError("Kaggle is disabled: set execution.kaggle.enabled: true in project.yaml")
        client = kaggle_client or CliKaggleClient(kcfg.get("credentials_env", "REGOR_KAGGLE_CREDENTIALS"))
        return KaggleExecutor(client, kcfg)
    raise ConfigError(f"backend {backend!r} cannot execute; use `regor import` for manual results")


def used_compute_hours(project) -> float:
    total = 0.0
    for r in list_runs(project):
        if r.get("runtime_seconds"):
            total += float(r["runtime_seconds"]) / 3600
    return total


def preflight(project, exp_id: str, backend: str | None, seeds: list[int] | None,
              allow_unvalidated: bool = False) -> dict[str, Any]:
    spec = validated_spec(project, exp_id)
    compute = spec.get("compute") or {}
    backend = backend or compute.get("backend") or project.cfg["execution"]["default_backend"]
    seeds = seeds if seeds is not None else (spec.get("seeds") or [0])
    problems: list[str] = []
    warnings: list[str] = []

    ds_identity = None
    if spec.get("dataset"):
        try:
            ds_identity = datasets.require_valid(project, spec["dataset"]["name"])
            if spec["dataset"].get("version") and spec["dataset"]["version"] != ds_identity["version"]:
                problems.append(f"spec wants dataset version {spec['dataset']['version']}, "
                                f"manifest has {ds_identity['version']}")
        except DatasetNotValidated as exc:
            if allow_unvalidated:
                warnings.append(f"UNVALIDATED DATASET (override): {exc}")
                ds_identity = {"name": spec["dataset"]["name"], "validation_status": "OVERRIDDEN"}
            else:
                problems.append(str(exc))

    device = compute.get("device", "cpu")
    if backend == "local" and device == "gpu" and not provenance.gpu_available():
        problems.append("experiment requires a GPU but none was detected locally "
                        "(nvidia-smi not found); no silent CPU fallback")

    budget = project.cfg["stopping"].get("compute_budget_hours")
    est = float(compute.get("estimated_hours", 0) or 0) * len(seeds)
    used = used_compute_hours(project)
    if budget is not None and used + est > float(budget):
        problems.append(f"compute budget: {used:.2f} h used + {est:.2f} h estimated "
                        f"> {budget} h budget (project.yaml stopping.compute_budget_hours)")

    sha = config_sha256(spec)
    need = approvals.required_reasons(project, spec, backend, len(seeds))
    appr = approvals.find_valid(project, exp_id, sha, backend, len(seeds)) if need else None
    if need and appr is None:
        problems.append("approval required: " + "; ".join(need))

    return {"experiment": exp_id, "backend": backend, "seeds": seeds, "config_sha256": sha,
            "estimated_hours": est, "used_hours": round(used, 4), "budget_hours": budget,
            "dataset": ds_identity, "approval_needed": need,
            "approval_id": appr["id"] if appr else None,
            "problems": problems, "warnings": warnings, "spec": spec}


def format_plan(plan: dict[str, Any]) -> str:
    lines = [f"Experiment     : {plan['experiment']}",
             f"Backend        : {plan['backend']}",
             f"Seeds / runs   : {plan['seeds']} ({len(plan['seeds'])} run(s))",
             f"Config sha256  : {plan['config_sha256'][:16]}...",
             f"Estimated time : {plan['estimated_hours']:.3f} h "
             f"(used {plan['used_hours']:.3f} h of budget {plan['budget_hours']})",
             f"Dataset        : {plan['dataset']}",
             f"Approval       : {'not required' if not plan['approval_needed'] else (plan['approval_id'] or 'MISSING')}"]
    for w in plan["warnings"]:
        lines.append(f"WARNING        : {w}")
    for p in plan["problems"]:
        lines.append(f"BLOCKED        : {p}")
    lines.append("Result         : " + ("READY" if not plan["problems"] else "NOT READY"))
    return "\n".join(lines)


def run_experiment(project, exp_id: str, backend: str | None = None,
                   seeds: list[int] | None = None, dry_run: bool = False,
                   allow_unvalidated: bool = False, resume_from: str | None = None,
                   parallel: int = 1, kaggle_client=None) -> dict[str, Any]:
    plan = preflight(project, exp_id, backend, seeds, allow_unvalidated)
    if dry_run or plan["problems"]:
        return {"plan": plan, "runs": [], "executed": False}
    if resume_from:
        load_run(project, resume_from)  # must exist
    spec, backend = plan["spec"], plan["backend"]
    executor = make_executor(project, backend, kaggle_client)
    env = provenance.environment(project.root)
    code_ck = {f: sha256_file(project.path(f))
               for f in (spec.get("entrypoint") or {}).get("code_files", [])}
    notes = list(plan["warnings"])
    if plan["dataset"] and plan["dataset"].get("synthetic"):
        notes.append("dataset is SYNTHETIC")

    recs = [create_run(project, spec, s, backend,
                       {**env, "code_checksums": code_ck,
                        "nondeterminism_notes": spec.get("nondeterminism_notes", "")},
                       plan["dataset"], resume_from=resume_from,
                       approval_id=plan["approval_id"], notes=notes)
            for s in plan["seeds"]]
    if plan["approval_id"]:
        approvals.consume(project, plan["approval_id"], [r["run_id"] for r in recs])

    limit = max(1, min(parallel, int(project.cfg["execution"].get("max_concurrent", 1))))

    def _one(rec):
        try:
            rec = executor.execute(project, rec)
        except (ExecutionError, ResearchError) as exc:
            from .executors.base import finalize_outputs
            from .util import utc_now
            rec = finalize_outputs(project, rec, "FAILED", finished_at=utc_now(), error=str(exc))
        if rec["status"] in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED", "IMPORTED"):
            validate_run(project, rec["run_id"])
            rec = load_run(project, rec["run_id"])
        return rec

    if limit == 1 or len(recs) == 1:
        done = []
        try:
            for r in recs:
                done.append(_one(r))             # one failure never stops the others
        except KeyboardInterrupt:
            from .executors.base import finalize_outputs
            from .util import utc_now
            for r in recs[len(done) + 1:]:
                finalize_outputs(project, load_run(project, r["run_id"]), "CANCELLED",
                                 finished_at=utc_now(), error="not started: batch cancelled by user")
            raise
    else:
        with ThreadPoolExecutor(max_workers=limit) as pool:
            done = list(pool.map(_one, recs))
    return {"plan": plan, "runs": done, "executed": True}


def collect_remote(project, run_ids: list[str] | None = None, kaggle_client=None) -> list[dict[str, Any]]:
    """Poll every SUBMITTED run once; finalise and validate the finished ones."""
    out = []
    targets = [r for r in list_runs(project) if r["status"] == "SUBMITTED"
               and (run_ids is None or r["run_id"] in run_ids)]
    if not targets:
        return out
    ex = make_executor(project, "kaggle", kaggle_client)
    for rec in targets:
        rec = ex.collect(project, rec)
        if rec["status"] != "SUBMITTED":
            validate_run(project, rec["run_id"])
            rec = load_run(project, rec["run_id"])
        out.append(rec)
    return out
