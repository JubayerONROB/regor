"""Section scaffolding and evidence-driven drafting.

Generated text contains only (a) structure, (b) marker references to verified claims,
configs, tables and figures, and (c) explicit placeholders. It never contains a typed
number, an invented citation or an interpretation presented as a finding. Narrative
prose is the researcher's (or an assistant's, under the audit), written around markers.

A section file that the researcher has edited is never overwritten: new drafts go to
``<section>.generated.md`` next to it for manual merging.
"""

from __future__ import annotations

from typing import Any

from .. import datasets, evidence, literature
from ..experiments import list_runs, list_specs
from ..util import atomic_write_text, read_json, read_yaml, sha256_text, write_yaml

RI = "[RESEARCHER INPUT REQUIRED]"

GUIDANCE = {
    "title": "A precise, non-promotional title.",
    "abstract": "Context, objective, method, key verified results as {{claim:ID}}, limitation, conclusion.",
    "keywords": "4-6 keywords, comma separated.",
    "introduction": "Problem, motivation, gap (as documented in literature/research_gap.md), RQs, contributions.",
    "related_work": "Prior work, each statement cited with [@key] to a VERIFIED reference.",
    "research_gap": "Scoped to the documented search; no unqualified 'first' or 'novel'.",
    "contributions": "Distinguish proposed from demonstrated contributions; demonstrated ones cite claims.",
    "methodology": "Must match the implementation: use {{spec:EXP-ID:path}} for configured values.",
    "experimental_setup": "Datasets (with validation status), splits, environment, seeds, statistical plan.",
    "results": "Only verified claims ({{claim:ID}}), generated tables and figures. No bare numbers.",
    "statistical_analysis": "Tests used, why, assumptions, corrections, effect sizes, intervals.",
    "discussion": "Interpretation, clearly labelled; consistent with evidence; conflicting results preserved.",
    "limitations": "All known limitations (data, method, statistics, scope).",
    "threats_to_validity": "Internal, external, construct, conclusion validity.",
    "conclusion": "Only conclusions supported by verified claims.",
    "future_work": "Grounded in unresolved questions and proposals.",
    "declarations": "Funding, conflicts, ethics, data availability, author contributions: researcher-supplied only.",
    "references": "Generated from verified references; do not edit.",
}


def _skeleton(name: str) -> str:
    if name == "references":
        return ("# References\n\n<!-- Generated at build time from the verified references actually "
                "cited. Do not edit. -->\n")
    return (f"# {name.replace('_', ' ').title()}\n\n<!-- Guidance: {GUIDANCE.get(name, '')} -->\n\n{RI}\n")


def _section_path(project, name: str):
    order = project.cfg["manuscript"]["sections"]
    i = order.index(name) if name in order else len(order)
    return project.path("manuscript", "sections", f"{i:02d}_{name}.md")


def _state_path(project):
    return project.path("manuscript", "sections", ".skeleton_hashes.yaml")


def init_sections(project) -> list[str]:
    created = []
    hashes = read_yaml(_state_path(project), {}) or {}
    for name in project.cfg["manuscript"]["sections"]:
        p = _section_path(project, name)
        if p.exists():
            continue
        text = _skeleton(name)
        atomic_write_text(p, text)
        hashes[p.name] = sha256_text(text)
        created.append(project.rel(p))
    write_yaml(_state_path(project), hashes)
    return created


def _write_draft(project, name: str, text: str) -> str:
    p = _section_path(project, name)
    hashes = read_yaml(_state_path(project), {}) or {}
    untouched = (not p.exists()) or sha256_text(p.read_text(encoding="utf-8")) == hashes.get(p.name)
    if untouched:
        atomic_write_text(p, text)
        hashes[p.name] = sha256_text(text)
        write_yaml(_state_path(project), hashes)
        return project.rel(p)
    g = p.with_name(p.stem + ".generated.md")
    atomic_write_text(g, text)
    return project.rel(g)


# ------------------------------------------------------------------ section drafters

def draft_results(project) -> str:
    claims = evidence.load(project)
    L = ["# Results", "",
         "<!-- Generated from evidence/claims.yaml and analysis/. Write narrative AROUND the markers;",
         "     never replace a marker with a typed number. -->", ""]
    for q in project.cfg["research"]["questions"]:
        L += [f"## {q['id']}: {q['text']}", ""]
        cs = [c for c in claims if c.get("research_question") == q["id"]]
        ok = [c for c in cs if c["status"] == "verified"]
        for c in ok:
            if c.get("verified_value") is not None:
                L.append(f"- {c['text']} ({{{{claim:{c['id']}}}}}).")
            else:
                L.append(f"- {{{{claimtext:{c['id']}}}}} <!-- evidence: {c['source']} -->")
        for c in cs:
            if c["status"] != "verified":
                L.append(f"- [INSUFFICIENT EVIDENCE] {c['id']} ({c['status']}): {c['text']}. "
                         f"<!-- {c.get('verification_notes')} -->")
        if not cs:
            L.append(f"- [INSUFFICIENT EVIDENCE] no claims are registered for {q['id']}.")
        L.append("")
    comps = sorted(project.path("analysis", "comparisons").glob("*.json"))
    if comps:
        L += ["## Comparison tables", ""]
        for p in comps:
            L += [f"{{{{table:{project.rel(p)}}}}}", ""]
    figs = sorted(project.path("analysis", "visualizations").glob("*.png"))
    if figs:
        L += ["## Figures", ""]
        for f in figs:
            if f.with_suffix(".provenance.json").exists():
                L += [f"{{{{figure:{project.rel(f)}|{RI}: caption}}}}", ""]
    return "\n".join(L) + "\n"


def draft_methodology(project) -> str:
    L = ["# Methodology", "",
         "<!-- Generated from experiments/configs/*.yaml. Every configured value is a {{spec:...}} marker",
         "     so the text cannot drift from the implementation. -->", ""]
    for s in list_specs(project):
        e = s["id"]
        L += [f"## {{{{spec:{e}:title}}}}", "",
              f"- Type: {{{{spec:{e}:type}}}}. Purpose: {{{{spec:{e}:rationale}}}}"]
        if (s.get("method") or {}).get("name"):
            L.append(f"- Method: {{{{spec:{e}:method.name}}}}."
                     + (f" {{{{spec:{e}:method.description}}}}" if (s.get("method") or {}).get("description") else ""))
        for k in sorted(((s.get("method") or {}).get("params") or {})):
            L.append(f"  - `{k}` = {{{{spec:{e}:method.params.{k}}}}}")
        for k in sorted((s.get("parameters") or {})):
            L.append(f"  - `{k}` = {{{{spec:{e}:parameters.{k}}}}}")
        for i, m in enumerate(s.get("metrics", [])):
            definition = f"{{{{spec:{e}:metrics.{i}.definition}}}}" if m.get("definition") else RI
            L.append(f"- Metric `{m['name']}`: {definition} ({{{{spec:{e}:metrics.{i}.direction}}}} is better).")
        if s.get("seeds"):
            L.append(f"- Seeds: {{{{spec:{e}:seeds}}}}; one run per seed.")
        L.append("")
    L += ["## Statistical procedure", "",
          "The significance level was alpha = {{project:statistics.alpha}} with "
          "{{project:statistics.multiple_comparison}} correction for multiple comparisons. "
          "Test selection rationale and assumption checks are reported per comparison.", ""]
    return "\n".join(L) + "\n"


def draft_setup(project) -> str:
    L = ["# Dataset and experimental setup", ""]
    for d in datasets.load_manifest(project)["datasets"]:
        n = d["name"]
        v = datasets.latest_validation(project, n)
        L += [f"## Dataset: {n} (version {{{{dataset:{n}:version}}}})", "",
              f"- Source: {{{{dataset:{n}:source.kind}}}}. Licence: {{{{dataset:{n}:license.name}}}}.",
              f"- Validation status: {v['status'] if v else 'NOT VALIDATED'} (see the dataset validation report).",
              "- SYNTHETIC: results are demonstrations only." if d.get("synthetic") else
              (f"- Collection: {{{{dataset:{n}:collection_methodology}}}}" if d.get("collection_methodology")
               else f"- Collection: {RI}")]
        for i, _ in enumerate(d.get("known_limitations", [])):
            L.append(f"- Known limitation: {{{{dataset:{n}:known_limitations.{i}}}}}")
        L.append("")
    if list_runs(project):
        L += ["## Computational environment", "",
              "- Platform, package versions, commit and seed of every run are recorded in its run record.", ""]
    return "\n".join(L) + "\n"


def draft_related(project) -> str:
    refs = [r for r in literature.load(project) if r["verification"]["status"] == "verified"]
    L = ["# Related work", "", "<!-- Only verified references appear below. Summaries must be checked",
         "     against the papers themselves. -->", ""]
    for r in refs:
        L.append(f"- {RI}: summarise {r['title']} [@{r['key']}].")
    if not refs:
        L.append("[INSUFFICIENT EVIDENCE] no verified references are registered.")
    return "\n".join(L) + "\n"


def draft_limitations(project) -> str:
    L = ["# Limitations", ""]
    for c in evidence.load(project):
        if c["type"] == "limitation":
            L.append(f"- {{{{claimtext:{c['id']}}}}}")
    for d in datasets.load_manifest(project)["datasets"]:
        for i, _ in enumerate(d.get("known_limitations", [])):
            L.append(f"- Dataset {d['name']}: {{{{dataset:{d['name']}:known_limitations.{i}}}}}")
        if d.get("synthetic"):
            L.append(f"- Dataset {d['name']} is synthetic; no real-world claim follows from it.")
    for p in sorted(project.path("reports", "experiment_reports").glob("*.json")):
        s = read_json(p) or {}
        for n, desc in (s.get("descriptive") or {}).items():
            mr = project.cfg["statistics"]["min_replicates"]
            if desc.get("n", 0) < mr:
                L.append(f"- {s['experiment']}: fewer validated runs for `{n}` than the planned "
                         "minimum (see project.yaml statistics.min_replicates).")
    L.append(f"- {RI}")
    return "\n".join(L) + "\n"


def draft_declarations(project) -> str:
    L = ["# Declarations", "",
         "<!-- These statements cannot be inferred from evidence. Only the researcher may supply them. -->", ""]
    for k, v in project.cfg["manuscript"]["declarations"].items():
        L.append(f"**{k.replace('_', ' ').capitalize()}.** {v if v else RI}")
        L.append("")
    return "\n".join(L) + "\n"


DRAFTERS = {"results": draft_results, "methodology": draft_methodology,
            "experimental_setup": draft_setup, "related_work": draft_related,
            "limitations": draft_limitations, "declarations": draft_declarations}


def draft(project, sections: list[str] | None = None) -> dict[str, str]:
    init_sections(project)
    configured = project.cfg["manuscript"]["sections"]
    targets = sections or [s for s in DRAFTERS if s in configured]
    out = {}
    for name in targets:
        if name not in DRAFTERS:
            out[name] = "no automatic drafter (write it around markers; see GUIDANCE)"
            continue
        out[name] = _write_draft(project, name, DRAFTERS[name](project))
    return out
