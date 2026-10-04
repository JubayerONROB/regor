"""Reproducibility metadata: environment, hardware, git state, dependency versions.

Every function here is best-effort and never raises: a missing tool becomes an explicit
``"unavailable"`` entry rather than a silently omitted field.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Environment variables that change numerical results or determinism. Their *values*
# are recorded -- they are never secrets. Secrets are never read from the environment
# here.
DETERMINISM_ENV = ("PYTHONHASHSEED", "CUBLAS_WORKSPACE_CONFIG", "OMP_NUM_THREADS",
                   "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUDA_VISIBLE_DEVICES",
                   "TF_DETERMINISTIC_OPS")


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 10) -> str | None:
    try:
        out = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                             text=True, timeout=timeout)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def git_state(repo: Path) -> dict[str, Any]:
    sha = _run(["git", "rev-parse", "HEAD"], repo)
    if sha is None:
        return {"commit": "unavailable", "dirty": None, "reason": "not a git repository or git missing"}
    porcelain = _run(["git", "status", "--porcelain"], repo) or ""
    return {"commit": sha, "dirty": bool(porcelain.strip()),
            "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)}


def package_versions(extra: tuple[str, ...] = ()) -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version
    names = ("numpy", "scipy", "pyyaml", "jsonschema", "matplotlib", "pandas",
             "scikit-learn", "torch", "research-engine") + tuple(extra)
    out = {"python": sys.version.split()[0]}
    for n in names:
        try:
            out[n] = version(n)
        except PackageNotFoundError:
            out[n] = "absent"
    return out


def hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
    }
    smi = shutil.which("nvidia-smi")
    if smi:
        q = _run([smi, "--query-gpu=name,memory.total,driver_version",
                  "--format=csv,noheader"])
        info["gpus"] = [g.strip() for g in q.splitlines()] if q else []
    else:
        info["gpus"] = []
    return info


def gpu_available() -> bool:
    return bool(hardware().get("gpus"))


def environment(project_root: Path) -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "hostname_hash": _hash_host(),
        "packages": package_versions(),
        "hardware": hardware(),
        "git": git_state(project_root),
        "determinism_env": {k: os.environ.get(k) for k in DETERMINISM_ENV},
    }


def _hash_host() -> str:
    """Hostname is hashed: enough to tell machines apart, not an identifier."""
    import hashlib
    return hashlib.sha256(platform.node().encode()).hexdigest()[:12]
