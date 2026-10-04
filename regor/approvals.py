"""Researcher approvals, stored as data.

An approval is single-use by default and bound to an experiment's *config hash* and
backend: changing the configuration (or retrying on a different backend) invalidates
it, so permission for one run never silently carries over to a different one.

This is a procedural control, not a security boundary: anyone with shell access can
write approvals.yaml. Claude Code should be denied `regor approve` in its permission
settings (see templates/claude_settings.example.json) so only the researcher grants them.
"""

from __future__ import annotations

from typing import Any

from .errors import ApprovalRequired
from .util import read_yaml, short_id, utc_now, write_yaml


def _path(project):
    return project.path("approvals", "approvals.yaml")


def load(project) -> list[dict[str, Any]]:
    return (read_yaml(_path(project), {}) or {}).get("approvals", [])


def save(project, items: list[dict[str, Any]]) -> None:
    write_yaml(_path(project), {"approvals": items})


def required_reasons(project, spec: dict[str, Any], backend: str,
                     n_runs: int = 1) -> list[str]:
    """Why this execution needs approval (empty list = no approval needed)."""
    rules = project.cfg["execution"]["approval"]
    compute = spec.get("compute", {}) or {}
    reasons = []
    if backend in rules.get("required_for_backends", []):
        reasons.append(f"backend '{backend}' requires approval")
    if compute.get("device", "cpu") in rules.get("required_for_devices", []):
        reasons.append(f"device '{compute.get('device')}' requires approval")
    limit = rules.get("required_above_estimated_hours")
    est = float(compute.get("estimated_hours", 0) or 0) * n_runs
    if limit is not None and est > float(limit):
        reasons.append(f"estimated {est:.2f} h exceeds the {limit} h approval threshold")
    return reasons


def grant(project, experiment_id: str, config_sha256: str, backend: str,
          granted_by: str, reason: str = "", max_runs: int = 1,
          max_hours: float | None = None) -> dict[str, Any]:
    if not granted_by.strip():
        raise ApprovalRequired("an approval must name the researcher granting it (--by)")
    item = {
        "id": f"APR-{utc_now()[:10]}-{short_id(4)}",
        "kind": "run",
        "experiment_id": experiment_id,
        "config_sha256": config_sha256,
        "backend": backend,
        "max_runs": int(max_runs),
        "max_hours": max_hours,
        "granted_by": granted_by,
        "granted_at": utc_now(),
        "reason": reason,
        "consumed_by": [],
        "status": "active",
    }
    items = load(project)
    items.append(item)
    save(project, items)
    return item


def find_valid(project, experiment_id: str, config_sha256: str, backend: str,
               n_runs: int) -> dict[str, Any] | None:
    for a in load(project):
        if (a.get("status") == "active" and a.get("experiment_id") == experiment_id
                and a.get("config_sha256") == config_sha256
                and a.get("backend") == backend
                and len(a.get("consumed_by", [])) + n_runs <= a.get("max_runs", 1)):
            return a
    return None


def consume(project, approval_id: str, run_ids: list[str]) -> None:
    items = load(project)
    for a in items:
        if a["id"] == approval_id:
            a.setdefault("consumed_by", []).extend(run_ids)
            if len(a["consumed_by"]) >= a.get("max_runs", 1):
                a["status"] = "consumed"
    save(project, items)


def revoke(project, approval_id: str) -> bool:
    items = load(project)
    hit = False
    for a in items:
        if a["id"] == approval_id and a["status"] == "active":
            a["status"] = "revoked"
            a["revoked_at"] = utc_now()
            hit = True
    save(project, items)
    return hit


def require(project, spec: dict[str, Any], config_sha256: str, backend: str,
            n_runs: int) -> dict[str, Any] | None:
    """Return the approval to consume, None if none is needed, or raise."""
    reasons = required_reasons(project, spec, backend, n_runs)
    if not reasons:
        return None
    a = find_valid(project, spec["id"], config_sha256, backend, n_runs)
    if a is None:
        raise ApprovalRequired(
            f"{spec['id']} needs researcher approval for {n_runs} run(s): "
            + "; ".join(reasons)
            + f".\n  The researcher can grant it with:\n    regor approve run {spec['id']} "
              f"--backend {backend} --runs {n_runs} --by \"<name>\" --reason \"...\"")
    return a
