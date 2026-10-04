"""Research project: locating, loading, validating and initialising.

A project is any directory containing ``project.yaml``. All engine state lives under it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config as cfgmod
from . import domains
from .errors import ConfigError, ProjectNotFound
from .scaffold import render_scaffold
from .util import read_yaml, utc_now, write_yaml

PROJECT_FILE = "project.yaml"

# Directories every project gets regardless of domain.
BASE_DIRS = [
    "research", "literature", "data", "experiments/plans", "experiments/configs",
    "experiments/scripts", "experiments/notebooks", "runs/raw", "runs/processed",
    "runs/logs", "runs/checkpoints", "runs/metadata", "runs/remote",
    "analysis/statistical", "analysis/visualizations", "analysis/comparisons",
    "reports/experiment_reports", "reports/progress_reports",
    "reports/technical_reports", "evidence", "manuscript/sections",
    "manuscript/figures", "manuscript/tables", "manuscript/references",
    "manuscript/audit", "manuscript/journal_format", "manuscript/build",
    "docs/decisions", "docs/experiment_history", "docs/changelog", "tests", "approvals",
]


@dataclass
class Project:
    root: Path
    cfg: dict[str, Any]

    # ------------------------------------------------------------------ discovery
    @classmethod
    def find(cls, start: str | Path | None = None) -> "Project":
        cur = Path(start or Path.cwd()).resolve()
        for d in [cur, *cur.parents]:
            if (d / PROJECT_FILE).exists():
                return cls.load(d)
        raise ProjectNotFound(
            f"no {PROJECT_FILE} in {cur} or any parent. Run `research init <name>` "
            "or pass --project <dir>.")

    @classmethod
    def load(cls, root: str | Path) -> "Project":
        root = Path(root).resolve()
        raw = read_yaml(root / PROJECT_FILE)
        if not isinstance(raw, dict):
            raise ConfigError(f"{root / PROJECT_FILE} is empty or not a mapping")
        cfg = cfgmod.with_defaults(raw)
        cfgmod.validate(cfg, "project", str(root / PROJECT_FILE))
        return cls(root=root, cfg=cfg)

    def save(self) -> None:
        cfgmod.validate(self.cfg, "project", PROJECT_FILE)
        write_yaml(self.root / PROJECT_FILE, self.cfg)

    # ------------------------------------------------------------------ accessors
    @property
    def name(self) -> str:
        return self.cfg["project"]["name"]

    @property
    def domain(self) -> domains.DomainProfile:
        return domains.get_profile(self.cfg["project"]["domain"], self.root)

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    @property
    def runs_meta(self) -> Path:
        return self.path("runs", "metadata")

    @property
    def runs_raw(self) -> Path:
        return self.path("runs", "raw")

    def rel(self, p: Path) -> str:
        try:
            return Path(p).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def question_ids(self) -> list[str]:
        return [q["id"] for q in self.cfg["research"].get("questions", [])]

    def hypothesis_ids(self) -> list[str]:
        return [h["id"] for h in self.cfg["research"].get("hypotheses", [])]


def init_project(target: str | Path, name: str | None = None,
                 domain: str = "generic", force: bool = False) -> Project:
    """Create a new project directory with the standard layout.

    Refuses to touch a directory that already contains project.yaml unless force=True,
    and even then never overwrites an existing file -- it only fills in missing ones.
    """
    root = Path(target).resolve()
    profile = domains.get_profile(domain)
    name = name or root.name
    if (root / PROJECT_FILE).exists() and not force:
        raise ConfigError(f"{root} already contains {PROJECT_FILE}; refusing to re-initialise")

    root.mkdir(parents=True, exist_ok=True)
    for d in BASE_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    for d in profile.src_dirs or ["methods", "evaluation", "analysis"]:
        (root / "src" / d).mkdir(parents=True, exist_ok=True)

    cfg = cfgmod.with_defaults({
        "project": {"name": name, "title": "", "domain": profile.name,
                    "description": "", "authors": [], "created": utc_now()},
        "research": {
            "questions": [{"id": "RQ1", "text": "[RESEARCHER INPUT REQUIRED]"}],
            "hypotheses": [{"id": "H1", "rq": "RQ1",
                            "statement": "[RESEARCHER INPUT REQUIRED]",
                            "falsification": "[RESEARCHER INPUT REQUIRED]",
                            "status": "proposed"}],
        },
    })
    if profile.resource_hints.get("device") == "gpu":
        cfg["execution"]["approval"]["required_for_devices"] = ["gpu"]

    for rel, text in render_scaffold(name, profile).items():
        p = root / rel
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    # Claude Code slash commands for the research workflow (never overwrite local edits).
    cmd_src = Path(__file__).resolve().parent / "claude_commands"
    cmd_dst = root / ".claude" / "commands"
    for f in sorted(cmd_src.glob("*.md")):
        target = cmd_dst / f.name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    if not (root / PROJECT_FILE).exists():
        write_yaml(root / PROJECT_FILE, cfg)
    return Project.load(root)
