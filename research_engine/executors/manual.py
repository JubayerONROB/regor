"""Import externally produced results (bench measurements, lab notebooks, other tools).

The original files are *copied* (never moved) into the run's raw directory, and their
source paths and checksums are recorded so the provenance of every imported number is
traceable. Imported runs are marked with backend ``manual`` in every report.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from ..errors import ExecutionError
from ..util import sha256_file, utc_now, write_json
from .base import finalize_outputs


def _metrics_from_file(path: Path) -> tuple[dict[str, Any], int | None]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if "metrics" in data:
            return data["metrics"], data.get("n_samples")
        return data, None
    if path.suffix.lower() == ".csv":
        # two columns: metric,value  (one row per metric)
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows or not {"metric", "value"} <= set(rows[0]):
            raise ExecutionError("CSV metrics must have columns 'metric,value'")
        out = {}
        for r in rows:
            try:
                out[r["metric"]] = float(r["value"])
            except ValueError:
                out[r["metric"]] = r["value"]
        return out, None
    raise ExecutionError(f"unsupported metrics file type: {path.suffix}")


def import_run(project, rec: dict[str, Any], metrics_file: Path, attachments: list[Path],
               measured_by: str, note: str = "") -> dict[str, Any]:
    raw = project.runs_raw / rec["run_id"]
    metrics, n = _metrics_from_file(metrics_file)
    sources = []
    for f in [metrics_file, *attachments]:
        if not f.is_file():
            raise ExecutionError(f"attachment {f} does not exist")
        dest = raw / "imported" / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        sources.append({"original_path": str(f), "sha256": sha256_file(f),
                        "stored_as": dest.relative_to(raw).as_posix()})
    write_json(raw / "metrics.json", {"metrics": metrics, "n_samples": n,
                                      "imported": True, "measured_by": measured_by})
    write_json(raw / "import_provenance.json", {"imported_at": utc_now(),
                                                "measured_by": measured_by, "note": note,
                                                "sources": sources})
    return finalize_outputs(project, rec, "IMPORTED", started_at=utc_now(),
                            finished_at=utc_now(), runtime_seconds=None,
                            notes=rec.get("notes", []) + [f"manual import by {measured_by}: {note}".strip()])
