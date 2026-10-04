"""Figures generated directly from comparison summaries.

Rules enforced here:
  * every individual run is drawn (no hiding of runs behind an aggregate);
  * aggregates (mean and CI) are drawn distinctly from individual points;
  * no bars, so there is no truncated-baseline problem; the axis is auto-scaled to
    include every point and every interval;
  * a provenance sidecar (<figure>.provenance.json) records the experiments, run IDs,
    metric definition and the hash of the summary the figure was drawn from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import ResearchError
from ..util import utc_now, write_json


def plot_comparison(summary: dict[str, Any], out_png: Path) -> dict[str, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ResearchError("matplotlib is not installed (pip install matplotlib)") from exc

    groups = [(summary["reference"]["experiment"], summary["reference"]["runs"],
               summary["reference"]["descriptive"])]
    groups += [(c["other"], c["other_runs"], c["other_summary"]["descriptive"])
               for c in summary["comparisons"]]
    fig, ax = plt.subplots(figsize=(1.6 + 1.3 * len(groups), 3.6), dpi=150)
    for i, (name, runs, d) in enumerate(groups):
        ys = [r["value"] for r in runs]
        xs = [i + (k - (len(ys) - 1) / 2) * 0.06 for k in range(len(ys))]
        ax.scatter(xs, ys, s=18, color="#4C72B0", alpha=0.75, zorder=3,
                   label="individual runs" if i == 0 else None)
        if d.get("mean") is not None:
            lo, hi = d.get("ci_low"), d.get("ci_high")
            if lo is not None:
                ax.errorbar([i + 0.28], [d["mean"]], yerr=[[d["mean"] - lo], [hi - d["mean"]]],
                            fmt="D", color="#C44E52", capsize=4, zorder=4,
                            label="mean ± CI" if i == 0 else None)
            else:
                ax.plot([i + 0.28], [d["mean"]], "D", color="#C44E52", zorder=4)
    m = summary["metric_definition"]
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[0] for g in groups], rotation=15, ha="right", fontsize=8)
    unit = f" [{m['unit']}]" if m.get("unit") else ""
    ax.set_ylabel(f"{summary['metric']}{unit} ({m.get('direction')} is better)", fontsize=8)
    ax.margins(y=0.15)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=7, loc="best")
    n_text = ", ".join(f"{g[0]}: n={len(g[1])}" for g in groups)
    ax.set_title(n_text, fontsize=7)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)

    prov = {
        "figure": out_png.name,
        "created_at": utc_now(),
        "source_summary": summary["name"],
        "source_summary_sha256": summary["sha256"],
        "metric": summary["metric"],
        "metric_definition": m,
        "experiments": [g[0] for g in groups],
        "run_ids": {g[0]: [r["run_id"] for r in g[1]] for g in groups},
        "excluded_runs": summary["reference"]["excluded"] +
        [e for c in summary["comparisons"] for e in c["other_summary"]["excluded"]],
        "encoding": "points = individual validated runs; diamond = mean with CI",
    }
    write_json(out_png.with_suffix(".provenance.json"), prov)
    return prov
