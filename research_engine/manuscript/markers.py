"""Regular expressions for the manuscript marker grammar (single source of truth)."""

from __future__ import annotations

import re
from pathlib import Path

CLAIM = re.compile(r"\{\{claim:([A-Za-z0-9_.-]+)\}\}")
CLAIMTEXT = re.compile(r"\{\{claimtext:([A-Za-z0-9_.-]+)\}\}")
LITERAL_CLAIM = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)(\s?%)?\s*\[claim:([A-Za-z0-9_.-]+)\]")
SPEC = re.compile(r"\{\{spec:([A-Za-z0-9_.-]+):([A-Za-z0-9_.]+)\}\}")
PROJECT = re.compile(r"\{\{project:([A-Za-z0-9_.]+)\}\}")
DATASET = re.compile(r"\{\{dataset:([A-Za-z0-9_.-]+):([A-Za-z0-9_.]+)\}\}")
TABLE = re.compile(r"\{\{table:([^}|]+)\}\}")
FIGURE = re.compile(r"\{\{figure:([^}|]+)(?:\|([^}]*))?\}\}")
CITE = re.compile(r"\[(@[A-Za-z][A-Za-z0-9_:.-]*(?:\s*;\s*@[A-Za-z][A-Za-z0-9_:.-]*)*)\]")
PLACEHOLDER = re.compile(r"\[(RESEARCHER INPUT REQUIRED[^\]]*|NEEDS VERIFIED RESULT[^\]]*|"
                         r"REFERENCE NOT VERIFIED[^\]]*|INSUFFICIENT EVIDENCE[^\]]*)\]")
COMMENT = re.compile(r"<!--.*?-->", re.S)
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
MD_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
MD_LINK_URL = re.compile(r"\]\([^)]*\)")
ANY_MARKER = re.compile(r"\{\{[^}]*\}\}|\[claim:[^\]]*\]|\[@[^\]]*\]")

# Identifiers that contain digits but are not numerical findings.
IDENTIFIER = re.compile(
    r"\b(?:RQ|H|C|P|D|EXP|APR)[-_]?\d[\w.-]*|\b(?:Fig(?:ure)?s?|Tab(?:le)?s?|Sec(?:tion)?s?|Eq(?:uation)?s?|"
    r"Appendix|Step|Phase|Stage|Algorithm)\.?\s+\d+[a-z]?(?:\.\d+)*", re.I)
# (?<![A-Za-z]-) skips hyphenated identifiers such as "window-5" or "k-3".
NUMBER = re.compile(r"(?<![\w.])(?<![A-Za-z]-)[-+]?\d+(?:[.,]\d+)*(?:\s?%)?(?![\w-])")
YEAR = re.compile(r"^(19|20)\d{2}$")
LIST_ENUM = re.compile(r"^\s*\d+[.)]\s", re.M)
HEADING_NUM = re.compile(r"^(#+)\s*\d+(?:\.\d+)*\s", re.M)


def section_files(project) -> list[Path]:
    return sorted(p for p in project.path("manuscript", "sections").glob("*.md")
                  if not p.name.endswith(".generated.md"))


def section_name(path: Path) -> str:
    stem = path.stem
    return stem.split("_", 1)[1] if "_" in stem and stem.split("_", 1)[0].isdigit() else stem


def strip_noncontent(text: str) -> str:
    """Remove comments and code so neither audit nor render sees them as prose."""
    text = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return CODE.sub(lambda m: " " * len(m.group(0)) if "\n" not in m.group(0)
                    else "\n" * m.group(0).count("\n"), text)
