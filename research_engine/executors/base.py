"""Executor interface and the shared output-finalisation step."""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..experiments import update_run
from ..util import fingerprint_paths


class Executor(ABC):
    """Runs one run record. Must leave the record in a terminal or SUBMITTED state."""

    name: str = "base"

    @abstractmethod
    def execute(self, project, rec: dict[str, Any]) -> dict[str, Any]:
        ...


def expand_command(cmd: list[str], *, python: str | None = None, config: str = "",
                   run_dir: str = "", seed: Any = "") -> list[str]:
    subs = {"{python}": python or sys.executable, "{config}": config,
            "{run_dir}": run_dir, "{seed}": str(seed)}
    out = []
    for part in cmd:
        for k, v in subs.items():
            part = part.replace(k, v)
        out.append(part)
    return out


def finalize_outputs(project, rec: dict[str, Any], status: str, **changes: Any) -> dict[str, Any]:
    """Checksum every raw output and lift metrics.json into the record.

    The checksums make later tampering with raw evidence detectable by the validator.
    """
    raw = project.runs_raw / rec["run_id"]
    outputs = fingerprint_paths([raw], raw) if raw.exists() else {}
    metrics: dict[str, Any] = {}
    n_samples = None
    mpath = raw / "metrics.json"
    if mpath.exists():
        try:
            data = json.loads(mpath.read_text(encoding="utf-8"))
            metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
            n_samples = data.get("n_samples") if isinstance(data, dict) else None
        except json.JSONDecodeError as exc:
            changes.setdefault("error", f"metrics.json is not valid JSON: {exc}")
    if n_samples is not None:
        changes["n_samples"] = n_samples
    return update_run(project, rec, status=status, outputs=outputs, metrics=metrics, **changes)
