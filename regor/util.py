"""Small shared helpers: hashing, time, YAML/JSON IO and atomic writes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string with seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_stamp() -> str:
    """Compact UTC timestamp for identifiers, e.g. 20261004T101530Z."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON used for hashing (sorted keys, no whitespace variance)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def fingerprint_paths(paths: Iterable[Path], root: Path) -> dict[str, str]:
    """sha256 of every file under the given paths, keyed by POSIX path relative to root."""
    out: dict[str, str] = {}
    for p in paths:
        p = Path(p)
        files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
        for f in files:
            out[f.relative_to(root).as_posix()] = sha256_file(f)
    return out


def short_id(n: int = 6) -> str:
    return secrets.token_hex(n // 2 if n > 1 else 1)


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "item"


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Write via a temp file and rename, so readers never see a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def read_yaml(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return default if data is None else data


def write_yaml(path: str | Path, data: Any) -> Path:
    return atomic_write_text(
        path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))


def read_json(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str | Path, data: Any) -> Path:
    return atomic_write_text(path, json.dumps(data, indent=2, default=str) + "\n")


def write_new_file(path: str | Path, text: str) -> Path:
    """Create a file that must not already exist (raw-evidence safety)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def get_path(obj: Any, dotted: str) -> Any:
    """Resolve 'a.b.0.c' inside nested dicts/lists. Raises KeyError if absent."""
    cur = obj
    for part in dotted.split(".") if dotted else []:
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(dotted)
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur
