"""Local CPU/GPU execution through a subprocess."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from ..errors import ExecutionError
from ..experiments import update_run
from ..util import utc_now
from .base import Executor, expand_command, finalize_outputs


class LocalExecutor(Executor):
    name = "local"

    def __init__(self, default_timeout_hours: float | None = None):
        self.default_timeout_hours = default_timeout_hours

    def execute(self, project, rec: dict[str, Any]) -> dict[str, Any]:
        spec = rec["config_snapshot"]
        ep = spec.get("entrypoint") or {}
        if not ep.get("command"):
            raise ExecutionError(f"{spec['id']}: no entrypoint.command to run locally")
        raw = project.runs_raw / rec["run_id"]
        cfg_path = project.runs_meta / f"{rec['run_id']}.config.json"
        cmd = expand_command(ep["command"], config=str(cfg_path), run_dir=str(raw),
                             seed=rec["seed"])
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (ep.get("env") or {}).items()})
        env.update({
            "RP_RUN_ID": rec["run_id"], "RP_RUN_DIR": str(raw), "RP_CONFIG": str(cfg_path),
            "RP_SEED": str(rec["seed"] if rec["seed"] is not None else 0),
            "RP_PROJECT_ROOT": str(project.root), "PYTHONUNBUFFERED": "1",
        })
        # Make research_engine.runtime importable by the script even when the engine is
        # used from a source checkout rather than an installed package.
        pkg_parent = str(_engine_parent())
        env["PYTHONPATH"] = pkg_parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        if rec.get("resume_from"):
            env["RP_RESUME_DIR"] = str(project.runs_raw / rec["resume_from"])

        hours = (spec.get("compute") or {}).get("timeout_hours") or self.default_timeout_hours
        timeout = float(hours) * 3600 if hours else None
        log_path = raw / "execution.log"
        update_run(project, rec, status="RUNNING", started_at=utc_now())
        t0 = time.monotonic()
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                log.write(f"# command: {cmd}\n# cwd: {project.root}\n# started: {utc_now()}\n")
                log.flush()
                proc = subprocess.Popen(cmd, cwd=str(project.root), env=env, stdout=log,
                                        stderr=subprocess.STDOUT)
                try:
                    code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    return finalize_outputs(project, rec, "TIMED_OUT", finished_at=utc_now(),
                                            runtime_seconds=round(time.monotonic() - t0, 3),
                                            error=f"exceeded timeout of {hours} h")
                except KeyboardInterrupt:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    finalize_outputs(project, rec, "CANCELLED", finished_at=utc_now(),
                                     runtime_seconds=round(time.monotonic() - t0, 3),
                                     error="cancelled by user (KeyboardInterrupt)")
                    raise
        except FileNotFoundError as exc:
            return finalize_outputs(project, rec, "FAILED", finished_at=utc_now(),
                                    runtime_seconds=round(time.monotonic() - t0, 3),
                                    error=f"could not start command: {exc}")
        status = "COMPLETED" if code == 0 else "FAILED"
        return finalize_outputs(project, rec, status, finished_at=utc_now(), exit_code=code,
                                runtime_seconds=round(time.monotonic() - t0, 3),
                                error=None if code == 0 else f"exit code {code}; see execution.log")


def _engine_parent():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]
