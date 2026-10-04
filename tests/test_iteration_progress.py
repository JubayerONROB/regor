import pytest

from conftest import git_commit, make_spec, save_spec
from research_engine import engine, evidence, iteration, progress
from research_engine.analysis.compare import compare, write_summary
from research_engine.cli import main
from research_engine.reports import experiment_report


def test_proposals_from_evidence_gaps(proj):
    engine.run_experiment(proj, "EXP-A", seeds=[0])            # below min_replicates
    save_spec(proj, make_spec("EXP-F", parameters={"mode": "fail"}, seeds=[0]))
    save_spec(proj, make_spec("EXP-P", type="proposed"))      # proposed method, no baseline
    git_commit(proj.root)
    engine.run_experiment(proj, "EXP-F")
    new = iteration.generate(proj)
    kinds = {p["kind"] for p in new}
    assert {"replicate", "diagnose_failure", "baseline", "evidence_gap"} <= kinds
    for p in new:
        for field in ("learned", "uncertainty", "hypothesis", "necessity", "variables_changed", "controlled",
                      "possible_outcomes", "influence_on_research", "resources"):
            assert field in p
        assert 0 <= p["ranking"]["score"] <= 1
    rep = next(p for p in new if p["kind"] == "replicate")
    assert rep["draft_spec"]["seeds"] == [1, 2]
    # unchanged evidence -> no duplicate proposals
    assert iteration.generate(proj) == []


def test_inconclusive_comparison_proposes_sample_increase(proj):
    engine.run_experiment(proj, "EXP-A", seeds=[0, 1])
    engine.run_experiment(proj, "EXP-B", seeds=[0, 1])
    write_summary(proj, compare(proj, "EXP-A", ["EXP-B"], "score", name="ab"))
    assert any(p["kind"] == "increase_sample" for p in iteration.generate(proj))


def test_decisions_and_loop_controls(proj):
    proj.cfg["stopping"]["max_iterations"] = 1
    proj.save()
    engine.run_experiment(proj, "EXP-A", seeds=[0])
    p = iteration.generate(proj)[0]
    with pytest.raises(ValueError):
        iteration.start_iteration(proj, "Dr Test")              # nothing approved yet
    iteration.decide(proj, p["id"], True, "Dr Test", "go")
    assert progress.decisions(proj)[-1]["title"].startswith("Approved proposal")
    it = iteration.start_iteration(proj, "Dr Test")
    assert it["n"] == 1
    iteration.close_iteration(proj, "done")
    st = iteration.stopping_status(proj)
    assert st["must_stop"] and st["review_required"] and not st["may_continue"]
    iteration.review(proj, "Dr Test")
    assert not iteration.stopping_status(proj)["review_required"]
    with pytest.raises(ValueError):
        iteration.decide(proj, p["id"], False, "Dr Test")      # already decided


def test_hypothesis_verdict_needs_verified_claims(proj):
    with pytest.raises(ValueError):
        progress.set_hypothesis(proj, "H1", "supported", "Dr Test", [])
    engine.run_experiment(proj, "EXP-B")
    evidence.add(proj, {"id": "C1", "text": "x", "type": "quantitative", "research_question": "RQ1",
                        "source": {"kind": "runs_metric", "experiment": "EXP-B", "metric": "score"}})
    evidence.verify_all(proj)
    progress.set_hypothesis(proj, "H1", "supported", "Dr Test", ["C1"])
    from research_engine.project import Project
    assert Project.load(proj.root).cfg["research"]["hypotheses"][0]["status"] == "supported"


def test_report_has_all_sections_and_lists_failures(proj):
    save_spec(proj, make_spec("EXP-A", parameters={"mode": "fail"}, seeds=[0]))
    git_commit(proj.root)
    engine.run_experiment(proj, "EXP-A")
    r = experiment_report(proj, "EXP-A")
    text = (proj.root / r["markdown"]).read_text()
    for n in range(1, 22):
        assert f"## {n}. " in text, n
    assert "FAILED" in text and "SYNTHETIC DATA" in text
    assert "[INTERPRETATION]" in text and "[MEASURED]" in text
    assert "None. No claim linked to this experiment is verified." in text


def test_status_reconstructed_from_files(proj):
    engine.run_experiment(proj, "EXP-A", seeds=[0])
    st = progress.write_progress(proj)
    assert st["runs_total"] == 1 and st["experiments"]["EXP-A"]["runs"] == 1
    assert (proj.root / "reports" / "progress_reports" / "PROGRESS.md").exists()
    assert (proj.root / "docs" / "experiment_history" / "dependency_graph.md").exists()
    # a brand-new process (no memory) sees the same state
    assert main(["--project", str(proj.root), "status", "--json"]) == 0
