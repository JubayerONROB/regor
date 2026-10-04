"""Generate the SYNTHETIC demonstration dataset (fixed seed, fully reproducible).

Signal: sum of two sinusoids. Observation: signal + Gaussian noise + sparse impulses.
Time-ordered split: first 70% train, last 30% test (no shuffling, no overlap).

This data is invented for demonstrating the pipeline. It is not a measurement of
anything and must never be presented as evidence about real signals.
"""

import csv
import sys
from pathlib import Path

import numpy as np

SEED = 2026
N = 4000
FS = 100.0  # samples per second (synthetic)


def main(out_dir: str) -> None:
    rng = np.random.default_rng(SEED)
    t = np.arange(N) / FS
    clean = np.sin(2 * np.pi * 0.5 * t) + 0.5 * np.sin(2 * np.pi * 1.3 * t)
    noise = rng.normal(0, 0.1, N)
    impulses = (rng.random(N) < 0.05) * rng.choice([-1, 1], N) * rng.uniform(1.5, 3.0, N)
    noisy = clean + noise + impulses
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cut = int(0.7 * N)
    for name, sl in (("train", slice(0, cut)), ("test", slice(cut, N))):
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["t", "clean", "noisy"])
            for i in range(N)[sl]:
                w.writerow([f"{t[i]:.2f}", f"{clean[i]:.6f}", f"{noisy[i]:.6f}"])
    print(f"wrote synthetic data to {out} ({cut} train / {N - cut} test samples)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/raw/demo_signals")
