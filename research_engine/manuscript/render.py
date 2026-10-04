"""Render manuscript sources into a venue-independent Markdown build.

Markers are resolved from the evidence registry, experiment configs and analysis
artifacts at build time. Anything that cannot be resolved becomes a visible
placeholder -- never a guessed value. The build manifest records every value used.
"""

from __future__ import annotations

from typing import Any

from .. import evidence, literature
from ..analysis.compare import _fmt
from ..experiments import load_spec
from ..errors import ConfigError
from ..util import atomic_write_text, get_path, read_json, sha256_text, utc_now, write_json
from . import markers as M


def summary_table(summary: dict[str, Any]) -> str:
    m = summary["metric_definition"]
    unit = f" [{m['unit']}]" if m.get("unit") else ""
    rows = [(summary["reference"]["experiment"], summary["reference"]["descriptive"], None)] + \
           [(c["other"], c["other_summary"]["descriptive"], c["result"]) for c in summary["comparisons"]]
    L = [f"Table: {summary['metric']}{unit}, validated runs only "
         f"(source: analysis/comparisons/{summary['name']}.json, sha256 {summary['sha256'][:12]}).", "",
         "| Condition | n | Mean | SD | 95% CI | Test vs reference | p (adj.) | Effect size |",
         "|---|---|---|---|---|---|---|---|"]
    for name, d, r in rows:
        ci = f"[{_fmt(d.get('ci_low'))}, {_fmt(d.get('ci_high'))}]"
        if r is None:
            t, p, es = "reference", "", ""
        else:
            e = r.get("effect_size") or {}
            t, p = r.get("test", ""), _fmt(r.get("p_adjusted"))
            es = f"{e.get('name', '')} {_fmt(e.get('value'))}" if e else ""
        L.append(f"| {name} | {d.get('n')} | {_fmt(d.get('mean'))} | {_fmt(d.get('std'))} | {ci} | {t} | {p} | {es} |")
    return "\n".join(L)


def render_text(project, text: str, section: str, manifest: dict[str, Any]) -> str:
    claims = {c["id"]: c for c in evidence.load(project)}
    refs = {r["key"]: r for r in literature.load(project)}
    text = M.COMMENT.sub("", text)

    def claim(m):
        c = claims.get(m.group(1))
        manifest["claims"].setdefault(m.group(1), set()).add(section)
        if not c or c["status"] != "verified" or c.get("verified_value") is None:
            return f"[NEEDS VERIFIED RESULT: {m.group(1)}]"
        manifest["values"][m.group(1)] = c["verified_value"]
        return evidence.format_value(c)

    def claimtext(m):
        c = claims.get(m.group(1))
        manifest["claims"].setdefault(m.group(1), set()).add(section)
        if not c or c["status"] != "verified":
            return f"[INSUFFICIENT EVIDENCE: {m.group(1)}]"
        return c["text"]

    def literal(m):
        manifest["claims"].setdefault(m.group(3), set()).add(section)
        return m.group(1) + (m.group(2) or "")

    def spec(m):
        try:
            val = get_path(load_spec(project, m.group(1)), m.group(2))
        except (KeyError, IndexError, ValueError, ConfigError):
            return f"[NEEDS VERIFIED RESULT: spec {m.group(1)}:{m.group(2)}]"
        manifest["spec_values"][f"{m.group(1)}:{m.group(2)}"] = val
        return str(val)

    def proj(m):
        try:
            return str(get_path(project.cfg, m.group(1)))
        except (KeyError, IndexError, ValueError):
            return f"[RESEARCHER INPUT REQUIRED: project.{m.group(1)}]"

    def dataset(m):
        from ..datasets import find_dataset
        entry = find_dataset(project, m.group(1))
        try:
            return str(get_path(entry, m.group(2))) if entry else f"[NEEDS VERIFIED RESULT: dataset {m.group(1)}]"
        except (KeyError, IndexError, ValueError):
            return f"[NEEDS VERIFIED RESULT: dataset {m.group(1)}:{m.group(2)}]"

    def table(m):
        s = read_json(project.path(m.group(1).strip()))
        if not s or "comparisons" not in s:
            return f"[NEEDS VERIFIED RESULT: table {m.group(1)}]"
        manifest["tables"][m.group(1)] = s.get("sha256")
        return summary_table(s)

    def figure(m):
        path = m.group(1).strip()
        cap = (m.group(2) or "").strip()
        prov = project.path(path).with_suffix(".provenance.json")
        if not project.path(path).exists() or not prov.exists():
            return f"[NEEDS VERIFIED RESULT: figure {path} has no provenance]"
        manifest["figures"][path] = read_json(prov).get("source_summary_sha256")
        return f"![{cap}](../../{path})"

    def cite(m):
        keys = [k.strip().lstrip("@") for k in m.group(1).split(";")]
        out = []
        for k in keys:
            r = refs.get(k)
            if r and r["verification"]["status"] == "verified":
                manifest["citations"].add(k)
                out.append(k)
            else:
                out.append(f"REFERENCE NOT VERIFIED: {k}")
        return "[" + "; ".join(out) + "]"

    text = M.CLAIM.sub(claim, text)
    text = M.CLAIMTEXT.sub(claimtext, text)
    text = M.LITERAL_CLAIM.sub(literal, text)
    text = M.SPEC.sub(spec, text)
    text = M.PROJECT.sub(proj, text)
    text = M.DATASET.sub(dataset, text)
    text = M.TABLE.sub(table, text)
    text = M.FIGURE.sub(figure, text)
    text = M.CITE.sub(cite, text)
    return text


def build(project) -> dict[str, Any]:
    manifest: dict[str, Any] = {"claims": {}, "values": {}, "spec_values": {}, "tables": {},
                                "figures": {}, "citations": set()}
    parts = []
    for p in M.section_files(project):
        parts.append(render_text(project, p.read_text(encoding="utf-8"), M.section_name(p), manifest))
    refs = {r["key"]: r for r in literature.load(project)}
    bib = ["# References", ""]
    for k in sorted(manifest["citations"]):
        r = refs[k]
        authors = ", ".join(r.get("authors") or [])
        ident = f"https://doi.org/{r['doi']}" if r.get("doi") else (r.get("url") or r.get("arxiv") or "")
        bib.append(f"- [{k}] {authors} ({r.get('year')}). {r['title']}. {r.get('venue') or ''}. {ident}")
    body = "\n\n".join(x.strip() for x in parts if x.strip() and not x.strip().startswith("# References"))
    text = body + "\n\n" + "\n".join(bib) + "\n"
    out = project.path("manuscript", "build", "manuscript.md")
    atomic_write_text(out, text)
    # record usage on claims (used_in) without touching their verification
    claims = evidence.load(project)
    for c in claims:
        c["used_in"] = sorted(manifest["claims"].get(c["id"], set()))
    evidence.save(project, claims)
    man = {**manifest, "claims": {k: sorted(v) for k, v in manifest["claims"].items()},
           "citations": sorted(manifest["citations"]), "built_at": utc_now(),
           "sha256": sha256_text(text), "output": project.rel(out)}
    write_json(project.path("manuscript", "build", "build_manifest.json"), man)
    return man
