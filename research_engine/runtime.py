"""Helper for experiment scripts -- the script side of the execution contract.

Standard library only, so it can be copied verbatim into a Kaggle kernel bundle.

Contract: an executor starts the entrypoint with these environment variables:

    RP_RUN_ID      unique run identifier
    RP_RUN_DIR     directory the script must write its outputs into
    RP_CONFIG      path to the immutable config snapshot (JSON)
    RP_SEED        integer seed for this run
    RP_RESUME_DIR  (optional) outputs of the run being resumed

and expects ``metrics.json`` in RP_RUN_DIR:

    {"metrics": {"rmse": 0.12, ...}, "n_samples": 1000, "extra": {...}}

Usage in a script::

    from research_engine.runtime import load_context, write_metrics
    ctx = load_context()
    ...
    write_metrics(ctx, {"rmse": rmse}, n_samples=len(y))
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    config: dict
    seed: int
    resume_dir: Path | None

    @property
    def params(self) -> dict:
        return self.config.get("parameters", {}) or {}

    @property
    def method_params(self) -> dict:
        return (self.config.get("method") or {}).get("params", {}) or {}


def load_context(seed_everything: bool = True) -> RunContext:
    try:
        run_dir = Path(os.environ["RP_RUN_DIR"])
        cfg_path = Path(os.environ["RP_CONFIG"])
    except KeyError as exc:
        raise SystemExit(
            f"missing {exc}: this script must be launched by `research run`, "
            "which sets RP_RUN_DIR, RP_CONFIG and RP_SEED") from None
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    seed = int(os.environ.get("RP_SEED", "0"))
    resume = os.environ.get("RP_RESUME_DIR")
    run_dir.mkdir(parents=True, exist_ok=True)
    if seed_everything:
        seed_all(seed)
    return RunContext(os.environ.get("RP_RUN_ID", "unknown"), run_dir, config, seed,
                      Path(resume) if resume else None)


def seed_all(seed: int) -> None:
    """Seed Python, NumPy and (if installed) PyTorch. Record anything else yourself."""
    random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch  # type: ignore
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def write_metrics(ctx: RunContext, metrics: dict[str, Any], n_samples: int | None = None,
                  **extra: Any) -> Path:
    """Write metrics.json. Non-finite values are written as null and listed explicitly."""
    clean: dict[str, Any] = {}
    nonfinite: list[str] = []
    for k, v in metrics.items():
        if isinstance(v, float) and not math.isfinite(v):
            clean[k] = None
            nonfinite.append(k)
        else:
            clean[k] = v
    payload = {"run_id": ctx.run_id, "seed": ctx.seed, "metrics": clean,
               "n_samples": n_samples, "nonfinite_metrics": nonfinite, "extra": extra}
    path = ctx.run_dir / "metrics.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def write_artifact(ctx: RunContext, name: str, data: Any) -> Path:
    """Write an auxiliary JSON artifact (predictions, per-sample scores, ...)."""
    path = ctx.run_dir / name
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
