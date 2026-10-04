"""Shared fixtures: a tiny, fully local project with a git-pinned toy experiment.

All data here is SYNTHETIC test fixture data. No network, GPU or credentials are used.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_engine import datasets  # noqa: E402
from research_engine.project import Project, init_project  # noqa: E402

SCRIPT = '''
import sys, time
from research_engine.runtime import load_context, write_metrics
ctx = load_context()
p = ctx.params
mode = p.get("mode", "ok")
if mode == "fail":
    sys.exit(3)
if mode == "sleep":
    time.sleep(30)
base = float(p.get("base", 1.0))
noise = ((ctx.seed * 31 + int(base * 100)) % 7) / 100.0
val = base if p.get("ignore_seed") else base + noise
metrics = {"score": val}
if mode == "nan":
    metrics["score"] = float("nan")
if mode == "missing":
    metrics = {}
if mode == "big":
    metrics["score"] = 1e9
write_metrics(ctx, metrics, n_samples=int(p.get("n", 10)))
'''

GIT = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "core.autocrlf=false"]


def git_commit(root: Path, msg: str = "snapshot") -> None:
    if not (root / ".git").exists():
        subprocess.run(GIT + ["init", "-q"], cwd=root, check=True)
    subprocess.run(GIT + ["add", "-A"], cwd=root, check=True)
    subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", msg], cwd=root, check=True)


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)] + [",".join(str(x) for x in r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_spec(exp_id: str, **over) -> dict:
    spec = {
        "id": exp_id, "title": f"toy {exp_id}", "type": "baseline", "status": "approved",
        "research_questions": ["RQ1"], "hypotheses": ["H1"],
        "rationale": "test fixture", "dataset": {"name": "toy", "version": "1.0"},
        "method": {"name": "toy", "params": {"k": 1}},
        "entrypoint": {"command": ["{python}", "experiments/scripts/score.py"],
                       "code_files": ["experiments/scripts/score.py"]},
        "parameters": {"base": 1.0, "n": 10},
        "seeds": [0, 1, 2],
        "metrics": [{"name": "score", "direction": "lower", "unit": "", "definition": "toy score",
                     "valid_range": [0, 1000]}],
        "expected_outputs": ["metrics.json"],
        "expected_samples": 10,
        "compute": {"backend": "local", "device": "cpu", "estimated_hours": 0.0001},
        "statistics": {"test": "auto", "paired_by": "seed"},
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(spec.get(k), dict):
            spec[k] = {**spec[k], **v}
        else:
            spec[k] = v
    return spec


def save_spec(proj: Project, spec: dict) -> None:
    p = proj.path("experiments", "configs", f"{spec['id']}.yaml")
    p.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")


@pytest.fixture
def proj(tmp_path) -> Project:
    root = tmp_path / "toyproj"
    p = init_project(root, "toyproj", "generic")
    p.cfg["research"]["questions"] = [{"id": "RQ1", "text": "Is B lower than A on the toy task?"},
                                      {"id": "RQ2", "text": "Second toy question"}]
    p.cfg["research"]["hypotheses"] = [{"id": "H1", "rq": "RQ1", "statement": "B is lower than A",
                                        "falsification": "no difference", "status": "proposed"}]
    p.cfg["statistics"]["min_replicates"] = 3
    p.save()
    (root / "experiments" / "scripts" / "score.py").write_text(SCRIPT, encoding="utf-8")
    write_csv(root / "data" / "toy" / "train.csv", ["id", "x", "label"],
              [[i, i * 0.5, i % 2] for i in range(0, 40)])
    write_csv(root / "data" / "toy" / "test.csv", ["id", "x", "label"],
              [[i, i * 0.5, i % 2] for i in range(40, 60)])
    datasets.register(p, {"name": "toy", "version": "1.0", "synthetic": True,
                          "source": {"kind": "generated", "access_verified": True},
                          "license": {"name": "CC0-1.0", "redistribution_allowed": True},
                          "files": [{"path": "data/toy/train.csv", "split": "train"},
                                    {"path": "data/toy/test.csv", "split": "test"}],
                          "target": "label", "id_column": "id"})
    datasets.validate_dataset(p, "toy")
    save_spec(p, make_spec("EXP-A"))
    save_spec(p, make_spec("EXP-B", type="proposed", compare_with=["EXP-A"], parameters={"base": 0.5}))
    # data/ is versioned here on purpose so git state is clean for the fixture
    (root / ".gitignore").write_text("runs/raw/\nruns/logs/\nruns/remote/\n", encoding="utf-8")
    git_commit(root)
    return Project.load(root)
