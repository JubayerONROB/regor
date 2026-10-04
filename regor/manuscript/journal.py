"""Journal-specific preparation, kept separate from the scientific content.

A journal profile is filled by the researcher *from the journal's official author
guidelines*. The engine never invents limits or policies: every unknown field stays
``null`` and the checklist reports it as unknown. Nothing here predicts acceptance or
suitability.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..util import atomic_write_text, read_json, read_yaml, slugify, utc_now, write_yaml
from . import markers as M

PROFILE_FIELDS = {
    "name": None, "publisher": None, "guidelines_url": None,
    "verified_against_guidelines": False, "verified_by": None, "verified_at": None,
    "article_type": None, "word_limit": None, "word_limit_counts": None,
    "abstract_word_limit": None, "keywords_min": None, "keywords_max": None,
    "max_figures": None, "max_tables": None, "reference_style": None,
    "required_sections": [], "required_statements": [], "anonymised_review": None,
    "supplementary_policy": None, "data_statement_required": None,
    "open_access_options": None, "latex_template_url": None, "notes": "",
}


def profile_dir(project, slug: str) -> Path:
    return project.path("manuscript", "journal_format", slug)


def init_profile(project, name: str) -> Path:
    slug = slugify(name)
    p = profile_dir(project, slug) / "journal_profile.yaml"
    if p.exists():
        return p
    data = dict(PROFILE_FIELDS, name=name)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = ("# Fill every field from the journal's OFFICIAL author guidelines, then set\n"
            "# verified_against_guidelines: true, verified_by and verified_at.\n"
            "# Unknown fields must stay null -- never guess limits or policies.\n")
    import yaml
    atomic_write_text(p, text + yaml.safe_dump(data, sort_keys=False))
    return p


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][\w'-]*", text))


def _sections_from_build(text: str) -> dict[str, str]:
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^#\s+(.*)", line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return out


def check(project, slug: str) -> dict[str, Any]:
    prof = read_yaml(profile_dir(project, slug) / "journal_profile.yaml")
    if not prof:
        raise FileNotFoundError(f"no journal profile for {slug}; run `regor journal init NAME`")
    build = project.path("manuscript", "build", "manuscript.md")
    text = build.read_text(encoding="utf-8") if build.exists() else ""
    secs = _sections_from_build(text)
    body = "\n".join(v for k, v in secs.items() if k != "references")
    abstract = secs.get("abstract", "")
    kw = [k for k in re.split(r"[,;]\s*", secs.get("keywords", "").strip()) if k]
    n_fig = len(re.findall(r"!\[", text))
    n_tab = len(re.findall(r"^Table:", text, re.M))
    audit = read_json(project.path("manuscript", "audit", "audit_report.json")) or {}
    items = []

    def item(ok, what, detail):
        items.append({"ok": ok, "item": what, "detail": detail})

    item(bool(prof.get("verified_against_guidelines")), "Profile verified against official guidelines",
         f"source: {prof.get('guidelines_url') or 'MISSING'}; by {prof.get('verified_by') or '-'}")
    item(bool(text), "Manuscript built", "manuscript/build/manuscript.md" if text else "run `regor manuscript build`")
    item(audit.get("overall") == "PASS", "Manuscript audit PASS", f"audit: {audit.get('overall', 'not run')}")

    def limit(name, value, lim):
        if lim is None:
            item(None, name, f"{value} (limit unknown: fill from guidelines)")
        else:
            item(value <= lim, name, f"{value} / {lim}")
    limit("Main-text words", _words(body), prof.get("word_limit"))
    limit("Abstract words", _words(abstract), prof.get("abstract_word_limit"))
    limit("Figures", n_fig, prof.get("max_figures"))
    limit("Tables", n_tab, prof.get("max_tables"))
    if prof.get("keywords_min") is not None or prof.get("keywords_max") is not None:
        lo, hi = prof.get("keywords_min") or 0, prof.get("keywords_max") or 10 ** 6
        item(lo <= len(kw) <= hi, "Keywords", f"{len(kw)} (allowed {lo}-{hi})")
    else:
        item(None, "Keywords", f"{len(kw)} (range unknown)")
    for s in prof.get("required_sections") or []:
        item(s.lower() in secs, f"Required section: {s}", "present" if s.lower() in secs else "missing")
    decl = project.cfg["manuscript"]["declarations"]
    for s in prof.get("required_statements") or []:
        key = slugify(s).replace("-", "_")
        val = decl.get(key)
        item(bool(val), f"Required statement: {s}", "supplied" if val else "researcher input required")
    ph = len(M.PLACEHOLDER.findall(text))
    item(ph == 0, "No unresolved placeholders in build", f"{ph} found")
    lines = [f"# Submission checklist: {prof.get('name')}", "", f"_Generated {utc_now()}._", "",
             "> This checklist covers formal requirements only. It does not and cannot predict "
             "acceptance or editorial suitability.", ""]
    for it in items:
        box = "x" if it["ok"] else (" " if it["ok"] is False else "?")
        lines.append(f"- [{box}] {it['item']}: {it['detail']}")
    lines += ["", "Legend: [x] met, [ ] not met, [?] unknown (fill the journal profile)."]
    atomic_write_text(profile_dir(project, slug) / "submission_checklist.md", "\n".join(lines) + "\n")
    ready = all(i["ok"] for i in items)
    return {"items": items, "all_met": ready}


# ------------------------------------------------------------------ export

def _md_to_latex(md: str) -> str:
    """Small, conservative Markdown -> LaTeX converter (headings, emphasis, lists,
    pipe tables, images, citations). Complex layouts should go through pandoc."""
    out, in_list, table = [], False, []

    def esc(s):
        s = s.replace("\\", r"\textbackslash{}")
        for a, b in (("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}")):
            s = s.replace(a, b)
        s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
        s = re.sub(r"\*(.+?)\*", r"\\emph{\1}", s)
        s = re.sub(r"\[([A-Za-z][\w:.-]*(?:; [A-Za-z][\w:.-]*)*)\]",
                   lambda m: r"\cite{" + m.group(1).replace("; ", ",").replace(r"\_", "_") + "}"
                   if "REFERENCE NOT VERIFIED" not in m.group(1) else m.group(0), s)
        return s

    def flush_table():
        nonlocal table
        if not table:
            return
        rows = [r for r in table if not re.match(r"^\|\s*-", r)]
        cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
        ncol = max(len(c) for c in cells)
        out.append(r"\begin{table}[ht]\centering\small")
        out.append(r"\begin{tabular}{" + "l" * ncol + "}")
        out.append(r"\hline")
        for i, c in enumerate(cells):
            out.append(" & ".join(esc(x) for x in c) + r" \\")
            if i == 0:
                out.append(r"\hline")
        out.append(r"\hline\end{tabular}\end{table}")
        table = []

    for line in md.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush_table()
        if in_list and not line.startswith("- "):
            out.append(r"\end{itemize}")
            in_list = False
        h = re.match(r"^(#+)\s+(.*)", line)
        img = re.match(r"^!\[(.*?)\]\((.*?)\)", line)
        if h:
            level = len(h.group(1))
            cmd = {1: "section", 2: "subsection"}.get(level, "subsubsection")
            out.append(f"\\{cmd}{{{esc(h.group(2))}}}")
        elif img:
            out.append(r"\begin{figure}[ht]\centering\includegraphics[width=0.8\linewidth]{"
                       + img.group(2) + r"}\caption{" + esc(img.group(1)) + r"}\end{figure}")
        elif line.startswith("- "):
            if not in_list:
                out.append(r"\begin{itemize}")
                in_list = True
            out.append(r"\item " + esc(line[2:]))
        else:
            out.append(esc(line))
    flush_table()
    if in_list:
        out.append(r"\end{itemize}")
    return "\n".join(out)


def export(project, slug: str, fmt: str) -> list[str]:
    build = project.path("manuscript", "build", "manuscript.md")
    if not build.exists():
        raise FileNotFoundError("build the manuscript first: regor manuscript build")
    md = build.read_text(encoding="utf-8")
    d = profile_dir(project, slug)
    d.mkdir(parents=True, exist_ok=True)
    written = []
    if fmt in ("markdown", "all"):
        shutil.copy2(build, d / "manuscript.md")
        written.append(project.rel(d / "manuscript.md"))
    if fmt in ("latex", "all"):
        body = md.split("\n# References", 1)[0]
        tex = ("\\documentclass[11pt]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{graphicx}\n"
               "\\usepackage{hyperref}\n% Generic template: replace with the journal's official class.\n"
               "\\begin{document}\n" + _md_to_latex(body) +
               "\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n")
        atomic_write_text(d / "manuscript.tex", tex)
        bib = project.path("literature", "references.bib")
        if bib.exists():
            shutil.copy2(bib, d / "references.bib")
        written += [project.rel(d / "manuscript.tex"), project.rel(d / "references.bib")]
    if fmt in ("docx", "pdf", "all"):
        pandoc = shutil.which("pandoc")
        for f in (["docx", "pdf"] if fmt == "all" else [fmt]):
            if not pandoc:
                written.append(f"SKIPPED {f}: pandoc not installed")
                continue
            target = d / f"manuscript.{f}"
            r = subprocess.run([pandoc, str(build), "-o", str(target)], capture_output=True, text=True)
            written.append(project.rel(target) if r.returncode == 0 else f"FAILED {f}: {r.stderr[-200:]}")
    cover = d / "cover_letter_draft.md"
    if not cover.exists():
        atomic_write_text(cover, "# Cover letter (draft)\n\nDear Editor,\n\n"
                          "[RESEARCHER INPUT REQUIRED: why this manuscript fits the journal's stated scope, "
                          "in the researcher's own words]\n\nThe main findings, each supported by verified "
                          "evidence, are: [RESEARCHER INPUT REQUIRED]\n\n"
                          "[RESEARCHER INPUT REQUIRED: declarations of originality, prior posting, conflicts]\n\n"
                          "Sincerely,\n[RESEARCHER INPUT REQUIRED]\n")
        written.append(project.rel(cover))
    return written
