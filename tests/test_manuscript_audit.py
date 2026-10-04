"""The audit must catch deliberately introduced unsupported claims and numerical mismatches."""

import json

import pytest

from conftest import git_commit, make_spec, save_spec
from research_engine import engine, evidence, literature
from research_engine.analysis.compare import compare, write_summary
from research_engine.manuscript import draft, journal
from research_engine.manuscript.audit import run_audit
from research_engine.manuscript.render import build

SECTIONS = ["abstract", "methodology", "results", "declarations", "references"]

CLEAN = {
    "abstract": "# Abstract\n\nThe mean score of condition B was {{claim:C1}}.\n",
    "methodology": "# Methodology\n\nCondition B used base = {{spec:EXP-B:parameters.base}} "
                   "with alpha = {{project:statistics.alpha}}.\n",
    "results": "# Results\n\nCondition B reached {{claim:C1}}; the mean paired difference "
               "to A was {{claim:C3}}.\n\n{{table:analysis/comparisons/ab.json}}\n",
    "declarations": "# Declarations\n\n**Funding.** Supplied by the researcher in project.yaml.\n",
    "references": "# References\n",
}


@pytest.fixture
def ms(proj):
    engine.run_experiment(proj, "EXP-A")
    engine.run_experiment(proj, "EXP-B")
    write_summary(proj, compare(proj, "EXP-A", ["EXP-B"], "score", name="ab"))
    evidence.add(proj, {"id": "C1", "text": "mean score of B", "type": "quantitative", "research_question": "RQ1",
                        "source": {"kind": "runs_metric", "experiment": "EXP-B", "metric": "score", "statistic": "mean"}})
    evidence.add(proj, {"id": "C3", "text": "paired mean difference B-A", "type": "comparative", "research_question": "RQ1",
                        "source": {"kind": "analysis", "file": "analysis/comparisons/ab.json",
                                   "json_path": "comparisons.0.result.mean_difference"}})
    evidence.add(proj, {"id": "CBAD", "text": "wrong number", "type": "quantitative",
                        "source": {"kind": "runs_metric", "experiment": "EXP-B", "metric": "score"},
                        "stated_value": 123.0})
    evidence.verify_all(proj)
    proj.cfg["manuscript"]["sections"] = SECTIONS
    proj.cfg["manuscript"]["results_sections"] = ["abstract", "results"]
    proj.cfg["manuscript"]["declarations"] = {k: "supplied by researcher" for k in
                                             proj.cfg["manuscript"]["declarations"]}
    proj.save()
    for name, text in CLEAN.items():
        draft._section_path(proj, name).write_text(text, encoding="utf-8")
    return proj


def write(proj, name, extra):
    draft._section_path(proj, name).write_text(CLEAN[name] + "\n" + extra + "\n", encoding="utf-8")


def fails(report, category=None):
    return [f for f in report["findings"] if f["status"] == "FAIL" and (category is None or f["category"] == category)]


def test_clean_manuscript_passes(ms):
    r = run_audit(ms)
    assert fails(r) == [], fails(r)
    assert r["overall"] == "PASS" and r["submission_ready"] is True
    assert {t["claim"] for t in r["claim_evidence_table"]} == {"C1", "C3"}
    m = build(ms)
    text = (ms.root / "manuscript" / "build" / "manuscript.md").read_text()
    assert "{{" not in text and "| EXP-B |" in text
    assert "C1" in m["claims"]
    assert evidence.get(ms, "C1")["used_in"] == ["abstract", "results"]


def test_unsupported_number_in_results(ms):
    write(ms, "results", "Condition B averaged 0.37 across seeds.")
    r = run_audit(ms)
    assert any("unsupported number '0.37'" in f["message"] for f in fails(r, "numerical"))
    assert r["submission_ready"] is False


def test_literal_mismatch_detected_and_match_accepted(ms):
    write(ms, "results", "B scored 99.9 [claim:C1].")
    assert any("does not match" in f["message"] for f in fails(run_audit(ms), "numerical"))
    val = evidence.get(ms, "C1")["verified_value"]
    write(ms, "results", f"B scored {val:.3f} [claim:C1].")
    assert fails(run_audit(ms)) == []


def test_unknown_and_failed_claims(ms):
    write(ms, "results", "See {{claim:C999}} and {{claim:CBAD}}.")
    msgs = [f["message"] for f in fails(run_audit(ms), "claim_evidence")]
    assert any("unknown claim C999" in m for m in msgs) and any("CBAD is failed" in m for m in msgs)


def test_citations_nonexistent_and_unverified(ms):
    literature.add(ms, {"key": "fixU", "title": "Unverified fixture"})
    write(ms, "methodology", "Prior work exists [@ghost2021; @fixU].")
    msgs = [f["message"] for f in fails(run_audit(ms), "references")]
    assert any("ghost2021" in m and "not in the reference registry" in m for m in msgs)
    assert any("fixU" in m and "unverified" in m for m in msgs)


def test_comparative_and_overstated_language(ms):
    write(ms, "results", "Our novel method clearly outperforms the baseline. B is significantly lower.")
    r = run_audit(ms)
    cats = {f["category"] for f in fails(r)}
    assert {"comparison", "overstatement", "statistics"} <= cats


def test_prior_work_without_citation_warns(ms):
    write(ms, "methodology", "Previous studies have shown this effect.")
    r = run_audit(ms)
    assert any(f["category"] == "references" and f["status"] == "WARNING" for f in r["findings"])


def test_placeholder_blocks_submission(ms):
    write(ms, "abstract", "[RESEARCHER INPUT REQUIRED]")
    r = run_audit(ms)
    assert fails(r, "placeholder") and not r["submission_ready"]


def test_tampered_table_source(ms):
    p = ms.root / "analysis" / "comparisons" / "ab.json"
    s = json.loads(p.read_text())
    s["reference"]["descriptive"]["mean"] = 0.0
    p.write_text(json.dumps(s))
    assert any("edited after generation" in f["message"] for f in fails(run_audit(ms), "tables"))


def test_spec_drift_after_runs(ms):
    save_spec(ms, make_spec("EXP-B", type="proposed", compare_with=["EXP-A"], parameters={"base": 0.25}))
    git_commit(ms.root)
    msgs = [f["message"] for f in fails(run_audit(ms), "methodology")]
    assert any("differs from what the runs executed" in m for m in msgs)


def test_unfair_comparison_detected(ms):
    save_spec(ms, make_spec("EXP-A", metrics=[{"name": "score", "direction": "higher", "definition": "other"}]))
    msgs = [f["message"] for f in fails(run_audit(ms), "methodology")]
    assert any("defined differently" in m for m in msgs)


def test_missing_section_and_bad_spec_reference(ms):
    draft._section_path(ms, "declarations").unlink()
    write(ms, "methodology", "Value {{spec:EXP-B:parameters.nope}}.")
    cats = [f["message"] for f in fails(run_audit(ms))]
    assert any("'declarations' is missing" in m for m in cats)
    assert any("does not resolve" in m for m in cats)


def test_journal_check_and_export(ms):
    build(ms)
    run_audit(ms)
    journal.init_profile(ms, "Fixture Journal")
    r = journal.check(ms, "fixture-journal")
    items = {i["item"]: i["ok"] for i in r["items"]}
    assert items["Profile verified against official guidelines"] is False
    assert items["Main-text words"] is None and r["all_met"] is False
    out = journal.export(ms, "fixture-journal", "latex")
    tex = (ms.root / "manuscript" / "journal_format" / "fixture-journal" / "manuscript.tex").read_text()
    assert "\\section{Results}" in tex and "\\begin{tabular}" in tex
