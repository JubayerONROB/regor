import json

from conftest import git_commit, make_spec, save_spec
from regor import engine, evidence, literature
from regor.analysis.compare import compare, write_summary
from regor.analysis.viz import plot_comparison


def _run_both(proj):
    engine.run_experiment(proj, "EXP-A")
    engine.run_experiment(proj, "EXP-B")


def test_comparison_uses_only_validated_runs_and_lists_exclusions(proj):
    _run_both(proj)
    save_spec(proj, make_spec("EXP-A", parameters={"mode": "fail"}))   # same id, different config
    git_commit(proj.root)
    engine.run_experiment(proj, "EXP-A", seeds=[9])                  # one failed run of EXP-A
    s = compare(proj, "EXP-A", ["EXP-B"], "score", name="ab")
    assert s["reference"]["descriptive"]["n"] == 3
    assert any(e["reason"].startswith("validation INVALID") for e in s["reference"]["excluded"])
    c = s["comparisons"][0]
    assert c["result"]["paired"] is True and c["paired_seeds"] == [0, 1, 2]
    assert c["point_estimate_favours"] == "other"
    j, m = write_summary(proj, s)
    assert "Excluded runs" in (proj.root / m).read_text()
    prov = plot_comparison(s, proj.path("analysis", "visualizations", "ab.png"))
    assert prov["run_ids"]["EXP-A"] and proj.path("analysis", "visualizations", "ab.provenance.json").exists()


def test_claims_verify_from_artifacts(proj):
    _run_both(proj)
    s = compare(proj, "EXP-A", ["EXP-B"], "score", name="ab")
    write_summary(proj, s)
    mean_b = s["comparisons"][0]["other_summary"]["descriptive"]["mean"]
    evidence.add(proj, {"id": "C1", "text": "mean score of B", "type": "quantitative", "research_question": "RQ1",
                        "source": {"kind": "runs_metric", "experiment": "EXP-B", "metric": "score", "statistic": "mean"},
                        "stated_value": mean_b})
    evidence.add(proj, {"id": "C2", "text": "max score of B (wrong value typed)", "type": "quantitative",
                        "source": {"kind": "runs_metric", "experiment": "EXP-B", "metric": "score", "statistic": "max"},
                        "stated_value": mean_b + 0.5})
    evidence.add(proj, {"id": "C3", "text": "B is significantly better than A", "type": "statistical",
                        "source": {"kind": "analysis", "file": "analysis/comparisons/ab.json",
                                   "json_path": "comparisons.0.result.p_adjusted"}})
    evidence.add(proj, {"id": "C4", "text": "no runs", "type": "quantitative",
                        "source": {"kind": "runs_metric", "experiment": "EXP-NOPE", "metric": "score"}})
    evidence.add(proj, {"id": "C5", "text": "prior work did X", "type": "literature",
                        "source": {"kind": "literature", "references": ["ghost2020"]}})
    evidence.add(proj, {"id": "C6", "text": "we are first", "type": "novelty", "source": {"kind": "researcher"}})
    res = {c["id"]: c for c in evidence.verify_all(proj)}
    assert res["C1"]["status"] == "verified" and abs(res["C1"]["verified_value"] - mean_b) < 1e-12
    assert res["C2"]["status"] == "failed" and "stated value" in res["C2"]["verification_notes"]
    sig = s["comparisons"][0]["result"]["significant_after_adjustment"]
    assert res["C3"]["status"] == ("verified" if sig else "needs_review")
    assert res["C4"]["status"] == "failed"
    assert res["C5"]["status"] == "failed" and "unverified" in res["C5"]["verification_notes"]
    assert res["C6"]["status"] == "needs_review"
    idx = (proj.root / "evidence" / "evidence_index.yaml").read_text()
    assert "C1" in idx


def test_contradiction_detected_and_preserved(proj):
    _run_both(proj)
    for cid, v in (("CA", 0.5), ("CB", 0.9)):
        evidence.add(proj, {"id": cid, "text": "x", "type": "quantitative",
                            "source": {"kind": "runs_metric", "experiment": "EXP-B", "metric": "score"},
                            "stated_value": v, "tolerance": 0.01})
    res = {c["id"]: c for c in evidence.verify_all(proj)}
    assert res["CA"]["contradicted_by"] == ["CB"] and res["CB"]["contradicted_by"] == ["CA"]
    assert res["CA"]["status"] != "verified" and res["CB"]["status"] != "verified"
    assert "contradicts CB" in res["CA"]["verification_notes"]


def test_superseded_claim_kept(proj):
    evidence.add(proj, {"id": "CX", "text": "old", "type": "qualitative", "source": {"kind": "researcher"}})
    evidence.mark_superseded(proj, "CX", None, "replaced")
    evidence.verify_all(proj)
    assert evidence.get(proj, "CX")["status"] == "superseded"


def test_small_values_not_rendered_as_zero():
    c = {"verified_value": 1.5e-05, "source": {}, "unit": None}
    assert evidence.format_value(c, 4) != "0.0000"
