"""Secret scanning.

Used before packaging a remote kernel, before committing, and on demand
(``regor security scan``). Findings report the file, line number and rule name, and
**never** the matched text, so the scanner itself cannot leak what it finds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import SecretDetected

RULES: dict[str, re.Pattern[str]] = {
    "github_token": re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"),
    "github_fine_grained_pat": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "openai_like_key": re.compile(r"\bsk-(proj-|ant-)?[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "hf_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "kaggle_key_field": re.compile(r"""["']key["']\s*:\s*["'][0-9a-f]{32}["']"""),
    "generic_assignment": re.compile(
        r"""(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*["'][^"'\s]{16,}["']"""),
}

# Filenames that are credentials by convention, whatever their content.
SENSITIVE_NAMES = re.compile(
    r"(?i)(^|/)(pat\.txt|.*\.pat|kaggle(_[^/]*)?\.json|\.env|.*\.env|id_rsa|id_ed25519|"
    r".*\.pem|.*\.key|.*credentials.*\.json|\.netrc|\.pypirc)$")
ALLOWED_NAMES = re.compile(r"(?i)(^|/)\.env\.example$")

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".npz", ".npy",
              ".pt", ".ckpt", ".so", ".dll", ".exe", ".whl", ".ico", ".parquet"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str

    def __str__(self) -> str:
        loc = f":{self.line}" if self.line else ""
        return f"{self.path}{loc}  [{self.rule}]"


def scan_text(text: str, path: str = "<text>") -> list[Finding]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if "regor-allow-secret" in line:          # explicit, reviewable opt-out for test fixtures
            continue
        for name, rx in RULES.items():
            if rx.search(line):
                out.append(Finding(path, lineno, name))
    return out


def iter_files(root: Path) -> Iterable[Path]:
    root = Path(root)
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            yield p


def scan_paths(paths: Iterable[Path], root: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for base in paths:
        base = Path(base)
        for f in iter_files(base):
            rel = (f.relative_to(root) if root and f.is_relative_to(root) else f).as_posix()
            if SENSITIVE_NAMES.search(rel) and not ALLOWED_NAMES.search(rel):
                findings.append(Finding(rel, 0, "sensitive_filename"))
                continue
            if f.suffix.lower() in BINARY_EXT or f.stat().st_size > 5_000_000:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            findings.extend(scan_text(text, rel))
    return findings


def assert_clean(paths: Iterable[Path], root: Path | None = None, context: str = "") -> None:
    findings = scan_paths(paths, root)
    if findings:
        listing = "\n  ".join(str(f) for f in findings)
        raise SecretDetected(
            f"possible secret(s) found{(' in ' + context) if context else ''} "
            f"(contents not shown):\n  {listing}")
