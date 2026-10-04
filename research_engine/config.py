"""Configuration loading and schema validation.

Schemas live in ``research_engine/schemas/*.schema.json`` and are the documented
contract between modules. Validation errors are collected (not first-error-only) so a
researcher sees every problem in one pass.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from .errors import ConfigError

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMAS = ("project", "experiment", "dataset_manifest", "claims", "run_record")


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise ConfigError(f"unknown schema {name!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def schema_errors(data: Any, name: str) -> list[str]:
    """Every schema violation as a 'location: message' string (empty list = valid)."""
    validator = jsonschema.Draft202012Validator(load_schema(name))
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{loc}: {err.message}")
    return errors


def validate(data: Any, name: str, source: str = "") -> None:
    errs = schema_errors(data, name)
    if errs:
        where = f" in {source}" if source else ""
        raise ConfigError(f"{len(errs)} schema error(s){where}:\n  - " + "\n  - ".join(errs))


# --------------------------------------------------------------------------- defaults

DEFAULT_SECTIONS = [
    "title", "abstract", "keywords", "introduction", "related_work", "research_gap",
    "contributions", "methodology", "experimental_setup", "results",
    "statistical_analysis", "discussion", "limitations", "threats_to_validity",
    "conclusion", "future_work", "declarations", "references",
]

DEFAULT_PROJECT: dict[str, Any] = {
    "schema_version": 1,
    "project": {"name": "", "title": "", "domain": "generic", "description": "",
                "authors": [], "created": ""},
    "research": {"questions": [], "hypotheses": [], "objectives": [], "scope": "",
                 "assumptions": [], "constraints": []},
    "statistics": {"alpha": 0.05, "min_replicates": 3, "multiple_comparison": "holm",
                   "default_test": "auto", "bootstrap_resamples": 5000,
                   "confidence_level": 0.95},
    "execution": {
        "default_backend": "local",
        "max_concurrent": 1,
        "default_timeout_hours": None,
        "approval": {"required_for_backends": ["kaggle"],
                     "required_above_estimated_hours": 1.0,
                     "required_for_devices": ["gpu"]},
        "kaggle": {"enabled": False, "credentials_env": "RP_KAGGLE_CREDENTIALS",
                   "accelerator": None, "internet": False, "private": True,
                   "dataset_sources": [], "max_retries": 2, "poll_seconds": 60},
    },
    "stopping": {"max_iterations": 10, "compute_budget_hours": 10.0, "deadline": None,
                 "saturation_window": 3, "require_review_every": 1,
                 "max_concurrent_experiments": 1},
    "manuscript": {
        "sections": list(DEFAULT_SECTIONS),
        "results_sections": ["abstract", "results", "statistical_analysis",
                             "discussion", "conclusion"],
        "declarations": {"funding": None, "conflicts_of_interest": None,
                         "ethics_approval": None, "data_availability": None,
                         "author_contributions": None, "acknowledgments": None,
                         "generative_ai_use": None},
        "target_journal": None,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into a copy of base (override wins)."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def with_defaults(project_cfg: dict[str, Any]) -> dict[str, Any]:
    return deep_merge(DEFAULT_PROJECT, project_cfg)
