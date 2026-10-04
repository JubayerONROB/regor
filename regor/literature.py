"""Reference registry, verification, BibTeX export and the literature matrix.

A reference is *verified* only when its metadata has been checked against an external
authority (Crossref for DOIs, arXiv for arXiv IDs) or explicitly attested by a named
researcher with an evidence URL. Unverified references are never exported to the
manuscript bibliography, and the manuscript audit fails on any citation to them.

Nothing in this module creates references. It only stores, checks and exports what a
researcher (or an assistant, on the researcher's behalf) entered.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable

from .errors import ConfigError, ResearchError
from .scaffold import LIT_MATRIX_HEADER
from .util import atomic_write_text, read_yaml, utc_now, write_yaml

Fetcher = Callable[[str], tuple[int, str]]
MATRIX_FIELDS = LIT_MATRIX_HEADER.strip().split(",")


def _path(project):
    return project.path("literature", "references.yaml")


def load(project) -> list[dict[str, Any]]:
    return (read_yaml(_path(project), {}) or {}).get("references", []) or []


def save(project, refs: list[dict[str, Any]]) -> None:
    keys = [r["key"] for r in refs]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise ConfigError(f"duplicate reference keys: {sorted(dup)}")
    write_yaml(_path(project), {"references": refs})


def get(project, key: str) -> dict[str, Any] | None:
    return next((r for r in load(project) if r["key"] == key), None)


def add(project, entry: dict[str, Any]) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_:.-]*", entry.get("key", "")):
        raise ConfigError("reference key must start with a letter and contain only A-Z a-z 0-9 _ : . -")
    if not entry.get("title"):
        raise ConfigError("a reference needs at least a title")
    refs = load(project)
    if any(r["key"] == entry["key"] for r in refs):
        raise ConfigError(f"reference {entry['key']!r} already exists")
    entry = {"type": "article", "authors": [], "year": None, "venue": None, "doi": None,
             "url": None, "arxiv": None, **entry}
    entry["verification"] = {"status": "unverified", "method": None, "checked_at": None,
                             "evidence_url": None, "mismatches": [], "note": "not yet verified"}
    entry.setdefault("matrix", {})
    refs.append(entry)
    save(project, refs)
    return entry


# ------------------------------------------------------------------ BibTeX

_FIELD = re.compile(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|\d+)", re.S)


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    """Minimal BibTeX reader (entries, braced/quoted/numeric fields). Not a full parser."""
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", text, re.S):
        etype, key, body = m.group(1).lower(), m.group(2), m.group(3)
        if etype in ("comment", "string", "preamble"):
            continue
        fields = {}
        for f in _FIELD.finditer(body):
            v = f.group(2).strip()
            if v[0] in "{\"":
                v = v[1:-1]
            fields[f.group(1).lower()] = re.sub(r"\s+", " ", v.replace("{", "").replace("}", "")).strip()
        authors = [a.strip() for a in fields.get("author", "").split(" and ") if a.strip()]
        year = fields.get("year")
        out.append({"key": key, "type": etype, "title": fields.get("title", ""),
                    "authors": authors, "year": int(year) if year and year.isdigit() else None,
                    "venue": fields.get("journal") or fields.get("booktitle"),
                    "doi": fields.get("doi"), "url": fields.get("url"),
                    "arxiv": fields.get("eprint") if "arxiv" in fields.get("archiveprefix", "").lower() else None})
    return out


def import_bibtex(project, text: str) -> list[str]:
    added = []
    existing = {r["key"] for r in load(project)}
    for e in parse_bibtex(text):
        if e["key"] in existing or not e["title"]:
            continue
        add(project, e)
        added.append(e["key"])
    return added


def _bib_escape(s: str) -> str:
    return s.replace("&", r"\&").replace("%", r"\%")


def to_bibtex(ref: dict[str, Any]) -> str:
    fields = [("title", "{" + _bib_escape(ref["title"]) + "}"),
              ("author", " and ".join(ref.get("authors") or []))]
    if ref.get("year"):
        fields.append(("year", str(ref["year"])))
    if ref.get("venue"):
        fields.append(("journal" if ref.get("type") == "article" else "booktitle", _bib_escape(ref["venue"])))
    for k in ("doi", "url"):
        if ref.get(k):
            fields.append((k, ref[k]))
    if ref.get("arxiv"):
        fields += [("eprint", ref["arxiv"]), ("archiveprefix", "arXiv")]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    return f"@{ref.get('type', 'article')}{{{ref['key']},\n{body}\n}}\n"


def export_bibtex(project) -> tuple[int, int]:
    refs = load(project)
    ok = [r for r in refs if r["verification"]["status"] == "verified"]
    text = ("% Generated by `regor lit export`. Verified references only.\n"
            f"% {len(ok)} verified of {len(refs)} registered.\n\n" + "\n".join(to_bibtex(r) for r in ok))
    atomic_write_text(project.path("literature", "references.bib"), text)
    atomic_write_text(project.path("manuscript", "references", "references.bib"), text)
    return len(ok), len(refs)


def write_matrix(project) -> int:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=MATRIX_FIELDS, lineterminator="\n")
    w.writeheader()
    refs = load(project)
    for r in refs:
        m = r.get("matrix", {})
        w.writerow({"key": r["key"], "title": r["title"], "authors": "; ".join(r.get("authors") or []),
                    "year": r.get("year") or "", "venue": r.get("venue") or "", "doi": r.get("doi") or "",
                    "url": r.get("url") or "", "verification_status": r["verification"]["status"],
                    **{k: m.get(k, "") for k in MATRIX_FIELDS[8:]}})
    atomic_write_text(project.path("literature", "literature_matrix.csv"), buf.getvalue())
    return len(refs)


def review_skeleton(project) -> str:
    refs = load(project)
    ver = [r for r in refs if r["verification"]["status"] == "verified"]
    unv = [r for r in refs if r["verification"]["status"] != "verified"]
    lines = ["# Literature review (draft skeleton)", "",
             "> Generated from verified references only. Every statement about prior work must",
             "> cite `[@key]`, and must be checked against the paper itself, not this summary.", ""]
    for r in sorted(ver, key=lambda r: (r.get("year") or 0)):
        m = r.get("matrix", {})
        lines += [f"## {r['title']} [@{r['key']}]", "",
                  f"- Methods: {m.get('methods') or '[RESEARCHER INPUT REQUIRED]'}",
                  f"- Datasets: {m.get('datasets') or '[RESEARCHER INPUT REQUIRED]'}",
                  f"- Results (as reported by the authors): {m.get('results') or '[RESEARCHER INPUT REQUIRED]'}",
                  f"- Limitations: {m.get('limitations') or '[RESEARCHER INPUT REQUIRED]'}",
                  f"- Relevance: {m.get('relevance') or '[RESEARCHER INPUT REQUIRED]'}", ""]
    if unv:
        lines += ["## Excluded: unverified references", ""] + \
                 [f"- {r['key']}: {r['title']} [REFERENCE NOT VERIFIED]" for r in unv]
    text = "\n".join(lines) + "\n"
    atomic_write_text(project.path("literature", "literature_review.md"), text)
    return text


# ------------------------------------------------------------------ verification

def default_fetcher(url: str) -> tuple[int, str]:
    mailto = os.environ.get("REGOR_CROSSREF_MAILTO", "")
    ua = "regor/0.1 (reference verification" + (f"; mailto:{mailto}" if mailto else "") + ")"
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ResearchError(f"network error: {exc}") from exc


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (s or "").lower())).strip()


def _family(name: str) -> str:
    name = name.strip()
    if "," in name:
        return _norm(name.split(",")[0])
    return _norm(name.split()[-1]) if name.split() else ""


def _compare(ref: dict[str, Any], title: str, year: int | None, families: list[str]) -> list[str]:
    mism = []
    sim = difflib.SequenceMatcher(None, _norm(ref["title"]), _norm(title)).ratio()
    if sim < 0.9:
        mism.append(f"title differs (similarity {sim:.2f}); authority: {title!r}")
    if ref.get("year") and year and int(ref["year"]) != int(year):
        mism.append(f"year {ref['year']} != authority {year}")
    if ref.get("authors") and families:
        if _family(ref["authors"][0]) != families[0]:
            mism.append(f"first author {ref['authors'][0]!r} != authority {families[0]!r}")
    return mism


def _crossref(doi: str, fetch: Fetcher) -> dict[str, Any] | None:
    status, text = fetch("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    if status != 200:
        return None
    msg = json.loads(text)["message"]
    year = None
    for k in ("published-print", "published-online", "issued"):
        parts = (msg.get(k) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    return {"title": (msg.get("title") or [""])[0], "year": year,
            "families": [_norm(a.get("family", "")) for a in msg.get("author", [])],
            "venue": (msg.get("container-title") or [None])[0],
            "url": f"https://doi.org/{doi}"}


def _arxiv(aid: str, fetch: Fetcher) -> dict[str, Any] | None:
    status, text = fetch("http://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(aid))
    if status != 200:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = ET.fromstring(text).find("a:entry", ns)
    if entry is None or entry.find("a:title", ns) is None:
        return None
    title = re.sub(r"\s+", " ", entry.find("a:title", ns).text or "").strip()
    if title.lower() == "error":
        return None
    pub = entry.find("a:published", ns)
    names = [n.text or "" for n in entry.findall("a:author/a:name", ns)]
    return {"title": title, "year": int(pub.text[:4]) if pub is not None and pub.text else None,
            "families": [_family(n) for n in names], "venue": "arXiv",
            "url": f"https://arxiv.org/abs/{aid}"}


def verify(project, key: str, fetch: Fetcher | None = None) -> dict[str, Any]:
    refs = load(project)
    ref = next((r for r in refs if r["key"] == key), None)
    if ref is None:
        raise ConfigError(f"reference {key!r} not found")
    fetch = fetch or default_fetcher
    v = {"status": "unverified", "method": None, "checked_at": utc_now(),
         "evidence_url": None, "mismatches": [], "note": ""}
    try:
        auth, method = None, None
        if ref.get("doi"):
            auth, method = _crossref(ref["doi"], fetch), "crossref"
        if auth is None and ref.get("arxiv"):
            auth, method = _arxiv(ref["arxiv"], fetch), "arxiv"
        if auth is None:
            if not (ref.get("doi") or ref.get("arxiv")):
                v["note"] = "no DOI or arXiv id: verify manually (regor lit verify KEY --manual ...)"
            else:
                v["status"] = "failed"
                v["method"] = method
                v["note"] = "identifier not found at the authority: possibly nonexistent or mistyped"
        else:
            mism = _compare(ref, auth["title"], auth["year"], auth["families"])
            v.update(method=method, evidence_url=auth["url"], mismatches=mism,
                     status="verified" if not mism else "failed",
                     note="metadata matches authority" if not mism else "metadata mismatch: correct the entry")
    except ResearchError as exc:
        v["note"] = f"could not reach authority ({exc}); status unchanged: unverified"
    ref["verification"] = v
    save(project, refs)
    return v


def verify_manual(project, key: str, evidence_url: str, by: str, note: str = "") -> dict[str, Any]:
    if not evidence_url or not by:
        raise ConfigError("manual verification needs --evidence-url and --by")
    refs = load(project)
    ref = next((r for r in refs if r["key"] == key), None)
    if ref is None:
        raise ConfigError(f"reference {key!r} not found")
    ref["verification"] = {"status": "verified", "method": f"manual ({by})", "checked_at": utc_now(),
                           "evidence_url": evidence_url, "mismatches": [], "note": note}
    save(project, refs)
    return ref["verification"]


def verified_keys(project) -> set[str]:
    return {r["key"] for r in load(project) if r["verification"]["status"] == "verified"}
