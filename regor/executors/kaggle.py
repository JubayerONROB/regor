"""Optional Kaggle execution adapter.

Design
------
* The experiment spec is backend-independent. Kaggle settings live in
  ``project.yaml -> execution.kaggle`` and are applied only here.
* A run is packaged as a *script kernel* whose single code file embeds a base64 zip of
  the spec's declared ``code_files``, the stdlib-only ``regor/runtime.py`` and
  the config snapshot (Kaggle uploads only the code file).
* The kernel directory is secret-scanned before every push; a finding aborts the push.
* Credentials are never written anywhere. ``CliKaggleClient`` reads a kaggle.json whose
  path is given by an environment variable (default ``REGOR_KAGGLE_CREDENTIALS``), or uses
  ``KAGGLE_USERNAME``/``KAGGLE_KEY`` already in the environment, or the CLI's own default
  config -- and passes them only to the ``kaggle`` subprocess environment.
* Nothing about quota, GPU type or session length is assumed. ``check_resources`` asks
  the CLI what it can; anything it cannot report is returned as ``"unknown"``.

Status of this adapter: implemented and covered by mocked tests. The real
``CliKaggleClient`` has **not** been exercised against live Kaggle in this repository's
test suite (tests never use credentials or network).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any, Protocol

from ..errors import ExecutionError
from ..experiments import update_run
from ..security import assert_clean
from ..util import utc_now, write_json
from .base import Executor, finalize_outputs

TERMINAL_OK = {"complete"}
TERMINAL_BAD = {"error", "cancelacknowledged", "cancelrequested", "cancelled"}
RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime.py"

KERNEL_TEMPLATE = '''"""regor kernel wrapper for run {run_id}. Generated -- do not edit."""
import base64, io, json, os, subprocess, sys, time, zipfile
from datetime import datetime, timezone

BUNDLE = "{bundle}"
CMD = {cmd}
RUN_ID = "{run_id}"
SEED = "{seed}"

# Outputs go straight into /kaggle/working, which is what `kaggle kernels output`
# downloads; the source bundle is unpacked outside it so it is not downloaded back.
out = "/kaggle/working"
src = "/tmp/regor_src"
os.makedirs(src, exist_ok=True)
os.makedirs(out, exist_ok=True)
zipfile.ZipFile(io.BytesIO(base64.b64decode(BUNDLE))).extractall(src)
env = dict(os.environ, REGOR_RUN_ID=RUN_ID, REGOR_RUN_DIR=out, REGOR_SEED=SEED,
           REGOR_CONFIG=os.path.join(src, "regor_config.json"), REGOR_DATA_DIR="/kaggle/input",
           PYTHONPATH=src, PYTHONUNBUFFERED="1")
cmd = [c.replace("{{python}}", sys.executable).replace("{{config}}", env["REGOR_CONFIG"])
        .replace("{{run_dir}}", out).replace("{{seed}}", SEED) for c in CMD]
started = datetime.now(timezone.utc).isoformat()
t0 = time.time()
with open(os.path.join(out, "execution.log"), "w") as log:
    code = subprocess.call(cmd, cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT)
status = {{"exit_code": code, "started_at": started,
          "finished_at": datetime.now(timezone.utc).isoformat(),
          "runtime_seconds": round(time.time() - t0, 3)}}
try:
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=30)
    status["gpu"] = smi.stdout.strip() or None if smi.returncode == 0 else None
except Exception:
    status["gpu"] = None
json.dump(status, open(os.path.join(out, "_kernel_status.json"), "w"), indent=2)
print(open(os.path.join(out, "execution.log")).read()[-5000:])
sys.exit(code)
'''


class KaggleClient(Protocol):
    def username(self) -> str: ...
    def push(self, kernel_dir: Path, accelerator: str | None) -> dict[str, Any]: ...
    def status(self, slug: str) -> str: ...
    def output(self, slug: str, dest: Path) -> list[str]: ...
    def check_resources(self) -> dict[str, Any]: ...


class CliKaggleClient:
    """Talks to Kaggle through the official ``kaggle`` CLI (subprocess, no shell)."""

    def __init__(self, credentials_env: str = "REGOR_KAGGLE_CREDENTIALS",
                 executable: str | None = None, timeout: int = 900):
        self.credentials_env = credentials_env
        self.exe = executable or _find_cli()
        self.timeout = timeout
        self._user: str | None = None

    # credentials stay inside this method's return value and the child env
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        cred_path = os.environ.get(self.credentials_env)
        if cred_path:
            p = Path(cred_path).expanduser()
            if not p.exists():
                raise ExecutionError(f"${self.credentials_env} points to a missing file")
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                env["KAGGLE_USERNAME"], env["KAGGLE_KEY"] = data["username"], data["key"]
            except (KeyError, json.JSONDecodeError):
                raise ExecutionError(f"${self.credentials_env} file is not a valid kaggle.json") from None
            self._user = data["username"]
        elif env.get("KAGGLE_USERNAME"):
            self._user = env["KAGGLE_USERNAME"]
        return env

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        if not self.exe:
            raise ExecutionError("the `kaggle` CLI is not installed (pip install kaggle)")
        try:
            return subprocess.run([self.exe, *args], env=self._env(), capture_output=True,
                                  text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise ExecutionError(f"kaggle {args[0]} timed out after {self.timeout}s") from None

    def cli_version(self) -> str:
        r = self._run("--version")
        m = re.search(r"(\d+\.\d+(\.\d+)*)", r.stdout + r.stderr)
        return m.group(1) if m else "unknown"

    def username(self) -> str:
        self._env()
        if self._user:
            return self._user
        r = self._run("config", "view")
        m = re.search(r"username:\s*(\S+)", r.stdout)
        if not m:
            raise ExecutionError("could not determine the Kaggle username; configure credentials")
        self._user = m.group(1)
        return self._user

    def push(self, kernel_dir: Path, accelerator: str | None) -> dict[str, Any]:
        args = ["kernels", "push", "-p", str(kernel_dir)]
        if accelerator:
            major = self.cli_version().split(".")[0]
            if not major.isdigit() or int(major) < 2:
                raise ExecutionError(
                    "an accelerator was requested but the installed kaggle CLI "
                    f"({self.cli_version()}) has no --accelerator option (needs >= 2.0). "
                    "Upgrade the CLI or set execution.kaggle.accelerator: null.")
            args += ["--accelerator", accelerator]
        r = self._run(*args)
        text = r.stdout + r.stderr
        if r.returncode != 0 or "error" in text.lower():
            raise ExecutionError(f"kaggle push failed: {_redact(text)[-800:]}")
        m = re.search(r"version\s+(\d+)", text, re.I)
        return {"version": int(m.group(1)) if m else None, "message": _redact(text)[-300:]}

    def status(self, slug: str) -> str:
        r = self._run("kernels", "status", slug)
        m = re.search(r'status\s+"?([A-Za-z_.]+)"?', r.stdout)
        if r.returncode != 0 or not m:
            raise ExecutionError(f"kaggle status failed for {slug}: {_redact(r.stdout + r.stderr)[-300:]}")
        return m.group(1).split(".")[-1].lower()

    def output(self, slug: str, dest: Path) -> list[str]:
        dest.mkdir(parents=True, exist_ok=True)
        r = self._run("kernels", "output", slug, "-p", str(dest))
        if r.returncode != 0:
            raise ExecutionError(f"kaggle output failed for {slug}: {_redact(r.stdout + r.stderr)[-300:]}")
        return sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())

    def check_resources(self) -> dict[str, Any]:
        info: dict[str, Any] = {"cli": self.exe or "not installed"}
        if not self.exe:
            return info
        info["cli_version"] = self.cli_version()
        r = self._run("kernels", "list", "--mine", "--page-size", "1")
        info["authenticated"] = r.returncode == 0
        info["accelerator_option"] = info["cli_version"].split(".")[0].isdigit() and \
            int(info["cli_version"].split(".")[0]) >= 2
        info["gpu_quota"] = "unknown: not exposed by the CLI; check kaggle.com/settings"
        info["session_limit"] = "unknown: check current Kaggle documentation"
        info["phone_verification"] = "unknown: GPU requires a phone-verified account"
        return info


def _find_cli() -> str | None:
    """Prefer the kaggle CLI installed alongside this Python, then fall back to PATH."""
    import sys
    here = Path(sys.executable).parent
    for name in ("kaggle.exe", "kaggle"):
        if (here / name).is_file():
            return str(here / name)
    return shutil.which("kaggle")


def _redact(text: str) -> str:
    """Strip anything that looks like a 32-hex key before text reaches logs/errors."""
    return re.sub(r"\b[0-9a-f]{32}\b", "[REDACTED]", text)


class MockKaggleClient:
    """In-memory Kaggle used by tests and `--mock-remote` demos. Never touches network."""

    def __init__(self, user: str = "mockuser", outcome: str = "complete",
                 metrics: dict[str, Any] | None = None, fail_pushes: int = 0,
                 polls_until_done: int = 1, exit_code: int = 0):
        self.user, self.outcome, self.metrics = user, outcome, metrics or {"score": 1.0}
        self.fail_pushes, self.polls_until_done, self.exit_code = fail_pushes, polls_until_done, exit_code
        self.pushed: dict[str, Path] = {}
        self.polls: dict[str, int] = {}
        self.push_attempts = 0

    def username(self) -> str:
        return self.user

    def push(self, kernel_dir: Path, accelerator: str | None) -> dict[str, Any]:
        self.push_attempts += 1
        if self.fail_pushes > 0:
            self.fail_pushes -= 1
            raise ExecutionError("mock transient push failure")
        meta = json.loads((kernel_dir / "kernel-metadata.json").read_text(encoding="utf-8"))
        self.pushed[meta["id"]] = kernel_dir
        self.polls[meta["id"]] = 0
        return {"version": 1, "message": "mock push ok"}

    def status(self, slug: str) -> str:
        self.polls[slug] = self.polls.get(slug, 0) + 1
        return self.outcome if self.polls[slug] >= self.polls_until_done else "running"

    def output(self, slug: str, dest: Path) -> list[str]:
        dest.mkdir(parents=True, exist_ok=True)
        files = {"execution.log": "mock kernel log\n",
                 "_kernel_status.json": json.dumps({"exit_code": self.exit_code,
                                                    "runtime_seconds": 12.5, "gpu": None})}
        if self.outcome == "complete" and self.exit_code == 0:
            files["metrics.json"] = json.dumps({"metrics": self.metrics, "n_samples": 10})
        for name, text in files.items():
            (dest / name).write_text(text, encoding="utf-8")
        return sorted(files)

    def check_resources(self) -> dict[str, Any]:
        return {"cli": "mock", "authenticated": True, "gpu_quota": "unknown (mock)"}


def build_kernel(project, rec: dict[str, Any], username: str, kcfg: dict[str, Any]) -> Path:
    """Materialise runs/remote/<run_id>/kernel/ ready for `kaggle kernels push`."""
    spec = rec["config_snapshot"]
    ep = spec.get("entrypoint") or {}
    kdir = project.path("runs", "remote", rec["run_id"], "kernel")
    if kdir.exists():
        shutil.rmtree(kdir)
    kdir.mkdir(parents=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in ep.get("code_files", []):
            p = project.path(rel)
            if not p.is_file():
                raise ExecutionError(f"code file {rel} does not exist")
            z.write(p, rel)
        z.writestr("regor/__init__.py", "")
        z.write(RUNTIME_SRC, "regor/runtime.py")
        z.writestr("regor_config.json", json.dumps(spec, indent=2, default=str))
    bundle = base64.b64encode(buf.getvalue()).decode("ascii")

    # Scan the *unpacked* inputs too: base64 would hide a secret from a text scan.
    staging = project.path("runs", "remote", rec["run_id"], "bundle_check")
    if staging.exists():
        shutil.rmtree(staging)
    zipfile.ZipFile(io.BytesIO(buf.getvalue())).extractall(staging)
    try:
        assert_clean([staging], staging, context="kernel bundle")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    code = KERNEL_TEMPLATE.format(bundle=bundle, cmd=json.dumps(ep.get("command", [])),
                                  run_id=rec["run_id"],
                                  seed=rec["seed"] if rec["seed"] is not None else 0)
    (kdir / "regor_kernel.py").write_text(code, encoding="utf-8")
    exp = re.sub(r"[^a-z0-9-]+", "-", spec["id"].lower()).strip("-")
    slug = f"{username}/regor-{exp}-{rec['run_id'].rsplit('__', 1)[-1]}"[:90]
    device = (spec.get("compute") or {}).get("device", "cpu")
    write_json(kdir / "kernel-metadata.json", {
        "id": slug,
        "title": slug.split("/", 1)[1],
        "code_file": "regor_kernel.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": bool(kcfg.get("private", True)),
        "enable_gpu": device == "gpu",
        "enable_internet": bool(kcfg.get("internet", False)),
        "dataset_sources": list(kcfg.get("dataset_sources", [])),
        "competition_sources": [],
        "kernel_sources": [],
    })
    assert_clean([kdir / "kernel-metadata.json"], kdir, context="kernel metadata")
    return kdir


class KaggleExecutor(Executor):
    name = "kaggle"

    def __init__(self, client: KaggleClient, kcfg: dict[str, Any]):
        self.client, self.kcfg = client, kcfg

    def execute(self, project, rec: dict[str, Any]) -> dict[str, Any]:
        """Package and push. Leaves the run SUBMITTED; `collect` finishes it."""
        user = self.client.username()
        kdir = build_kernel(project, rec, user, self.kcfg)
        meta = json.loads((kdir / "kernel-metadata.json").read_text(encoding="utf-8"))
        retries = int(self.kcfg.get("max_retries", 2))
        last: Exception | None = None
        for attempt in range(1, retries + 2):
            try:
                res = self.client.push(kdir, self.kcfg.get("accelerator"))
                return update_run(project, rec, status="SUBMITTED", started_at=utc_now(),
                                  remote={"backend": "kaggle", "slug": meta["id"],
                                          "pushed_at": utc_now(), "attempts": attempt,
                                          "version": res.get("version"),
                                          "accelerator": self.kcfg.get("accelerator"),
                                          "enable_gpu": meta["enable_gpu"],
                                          "mock": isinstance(self.client, MockKaggleClient)})
            except ExecutionError as exc:
                last = exc
                if attempt <= retries:
                    time.sleep(min(30, 2 ** attempt) if not isinstance(self.client, MockKaggleClient) else 0)
        return finalize_outputs(project, rec, "FAILED", finished_at=utc_now(),
                                error=f"push failed after {retries + 1} attempt(s): {last}")

    def collect(self, project, rec: dict[str, Any]) -> dict[str, Any]:
        """Poll once. On a terminal state, download outputs and finalise the run."""
        if rec["status"] != "SUBMITTED":
            return rec
        slug = rec["remote"]["slug"]
        st = self.client.status(slug)
        remote = {**rec["remote"], "last_status": st, "last_polled_at": utc_now()}
        if st not in TERMINAL_OK | TERMINAL_BAD:
            return update_run(project, rec, remote=remote)
        dest = project.runs_raw / rec["run_id"]
        try:
            self.client.output(slug, dest)
        except ExecutionError as exc:
            remote["output_error"] = str(exc)
        ks = {}
        if (dest / "_kernel_status.json").exists():
            ks = json.loads((dest / "_kernel_status.json").read_text(encoding="utf-8"))
        runtime = ks.get("runtime_seconds")
        code = ks.get("exit_code")
        remote["gpu_assigned"] = ks.get("gpu")
        if st in TERMINAL_OK and code == 0:
            return finalize_outputs(project, rec, "COMPLETED", finished_at=utc_now(),
                                    exit_code=0, runtime_seconds=runtime, remote=remote)
        why = f"kaggle status {st!r}" + (f", exit code {code}" if code is not None else "")
        return finalize_outputs(project, rec, "FAILED", finished_at=utc_now(), exit_code=code,
                                runtime_seconds=runtime, remote=remote,
                                error=f"{why}; outputs/logs saved in runs/raw/{rec['run_id']}")
