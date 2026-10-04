"""Denoise the SYNTHETIC test split with a moving-average or median filter.

Seed semantics: the seed selects which evaluation windows of the test split are scored
(random 400-sample segments). Two experiments run with the same seed are scored on the
same segments, which makes a seed-paired comparison valid.
"""

import csv
import time
from pathlib import Path

import numpy as np

from research_engine.runtime import load_context, write_metrics


def load_split(path: Path):
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return (np.array([float(r["clean"]) for r in rows]),
            np.array([float(r["noisy"]) for r in rows]))


def filt(x: np.ndarray, method: str, window: int) -> np.ndarray:
    pad = window // 2
    xp = np.pad(x, pad, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(xp, window)
    if method == "moving_average":
        return view.mean(axis=1)
    if method == "median":
        return np.median(view, axis=1)
    raise ValueError(f"unknown method {method}")


def main() -> None:
    ctx = load_context()
    method = ctx.config["method"]["name"]
    window = int(ctx.method_params["window"])
    p = ctx.params
    clean, noisy = load_split(Path(p["data_dir"]) / "test.csv")
    rng = np.random.default_rng(ctx.seed)
    seg, n_seg = int(p["segment_length"]), int(p["n_segments"])
    starts = rng.integers(0, len(clean) - seg, n_seg)
    t0 = time.perf_counter()
    errs = []
    for s in starts:
        y = filt(noisy[s:s + seg], method, window)
        errs.append(y - clean[s:s + seg])
    elapsed_ms = (time.perf_counter() - t0) * 1000
    e = np.concatenate(errs)
    write_metrics(ctx, {"rmse": float(np.sqrt(np.mean(e ** 2))),
                        "mae": float(np.mean(np.abs(e))),
                        "runtime_ms": float(elapsed_ms)},
                  n_samples=int(e.size), segment_starts=[int(s) for s in starts])


if __name__ == "__main__":
    main()
