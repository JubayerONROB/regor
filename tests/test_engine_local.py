import json

import pytest

from conftest import git_commit, make_spec, save_spec
from research_engine import approvals, engine, provenance
from research_engine.errors import ResearchError
from research_engine.experiments import list_runs, load_run, update_run
from research_engine.results import validate_run


def test_dry_run_creates_nothing(proj):
    res = engine.run_experiment(proj, "EXP-A", dry_run=True)
    assert not res["executed"] and res["plan"]["problems"] == []
    assert list_runs(proj) == []


def test_local_run_validated_with_provenance(proj):
    res = engine.run_experiment(proj, "EXP-A")
    runs = res["runs"]
    assert len(runs) == 3
    for r in runs:
        assert r["status"] == "COMPLETED"
        assert r["validation"]["status"] == "VALIDATED", r["validation"]
        assert r["provenance"]["git"]["commit"] not in (None, "unavailable")
        assert "experiments/scripts/score.py" in r["provenance"]["code_checksums"]
        assert r["dataset"]["fingerprint"] and r["outputs"]["metrics.json"]
        assert (proj.runs_raw / r["run_id"] / "execution.log").exists()


def test_never_overwrites_previous_runs(proj):
    a = engine.run_experiment(proj, "EXP-A", seeds=[0])["runs"][0]
    b = engine.run_experiment(proj, "EXP-A", seeds=[0])["runs"][0]
    assert a["run_id"] != b["run_id"]
    assert len(list_runs(proj, "EXP-A")) == 2
    assert a["config_sha256"] == b["config_sha256"]


def test_tampering_with_raw_evidence_is_detected(proj):
    r = engine.run_experiment(proj, "EXP-A", seeds=[0])["runs"][0]
    m = proj.runs_raw / r["run_id"] / "metrics.json"
    data = json.loads(m.read_text())
    data["metrics"]["score"] = 0.0001
    m.write_text(json.dumps(data))
    v = validate_run(proj, r["run_id"])
    assert v["status"] == "INVALID"
    assert any(i["check"] == "raw_integrity" for i in v["issues"])


def test_failure_is_recorded_and_does_not_stop_queue(proj):
    save_spec(proj, make_spec("EXP-F", parameters={"mode": "fail"}))
    git_commit(proj.root)
    runs = engine.run_experiment(proj, "EXP-F")["runs"]
    assert [r["status"] for r in runs] == ["FAILED"] * 3
    assert all(r["validation"]["status"] == "INVALID" for r in runs)
    assert all(r["exit_code"] == 3 for r in runs)


@pytest.mark.parametrize("mode,expected,check", [
    ("missing", "INCOMPLETE", "metric_definitions"),
    ("nan", "INVALID", "numerical_validity"),
    ("big", "INVALID", "numerical_validity"),
])
def test_metric_problems(proj, mode, expected, check):
    save_spec(proj, make_spec("EXP-M", parameters={"mode": mode}, seeds=[0]))
    git_commit(proj.root)
    r = engine.run_experiment(proj, "EXP-M")["runs"][0]
    assert r["validation"]["status"] == expected
    assert any(i["check"] == check for i in r["validation"]["issues"])


def test_sample_count_mismatch_invalid(proj):
    save_spec(proj, make_spec("EXP-N", parameters={"n": 7}, seeds=[0]))
    git_commit(proj.root)
    r = engine.run_experiment(proj, "EXP-N")["runs"][0]
    assert r["validation"]["status"] == "INVALID"


def test_seed_ignored_is_flagged(proj):
    save_spec(proj, make_spec("EXP-S", parameters={"ignore_seed": True}, seeds=[0, 1]))
    git_commit(proj.root)
    runs = engine.run_experiment(proj, "EXP-S")["runs"]
    v = validate_run(proj, runs[0]["run_id"])
    assert v["status"] == "PROVISIONAL" and any(i["check"] == "duplicates" for i in v["issues"])


def test_timeout(proj):
    save_spec(proj, make_spec("EXP-T", parameters={"mode": "sleep"}, seeds=[0],
                              compute={"timeout_hours": 0.0005}))
    git_commit(proj.root)
    r = engine.run_experiment(proj, "EXP-T")["runs"][0]
    assert r["status"] == "TIMED_OUT" and r["validation"]["status"] == "INCOMPLETE"


def test_gpu_required_without_gpu_blocked(proj, monkeypatch):
    monkeypatch.setattr(provenance, "gpu_available", lambda: False)
    save_spec(proj, make_spec("EXP-G", compute={"device": "gpu"}))
    res = engine.run_experiment(proj, "EXP-G")
    assert not res["executed"]
    assert any("GPU" in p for p in res["plan"]["problems"])


def test_budget_blocks(proj):
    proj.cfg["stopping"]["compute_budget_hours"] = 0.0
    save_spec(proj, make_spec("EXP-BIG", compute={"estimated_hours": 0.5}))
    res = engine.run_experiment(proj, "EXP-BIG")
    assert any("budget" in p for p in res["plan"]["problems"])


def test_approval_required_single_use_and_bound_to_config(proj):
    save_spec(proj, make_spec("EXP-H", compute={"estimated_hours": 2.0}, seeds=[0]))
    git_commit(proj.root)
    proj.cfg["stopping"]["compute_budget_hours"] = 100
    res = engine.run_experiment(proj, "EXP-H")
    assert not res["executed"] and any("approval" in p for p in res["plan"]["problems"])
    from research_engine.experiments import config_sha256, load_spec
    approvals.grant(proj, "EXP-H", config_sha256(load_spec(proj, "EXP-H")), "local", "Dr Test", max_runs=1)
    assert engine.run_experiment(proj, "EXP-H")["executed"]
    # consumed: a second execution needs a new approval
    assert not engine.run_experiment(proj, "EXP-H")["executed"]
    # changing the configuration invalidates any approval
    approvals.grant(proj, "EXP-H", config_sha256(load_spec(proj, "EXP-H")), "local", "Dr Test")
    save_spec(proj, make_spec("EXP-H", compute={"estimated_hours": 2.0}, seeds=[0], parameters={"base": 3.0}))
    assert not engine.run_experiment(proj, "EXP-H")["executed"]


def test_unvalidated_dataset_blocks_unless_overridden(proj):
    (proj.root / "data" / "validation" / "toy.json").unlink()
    res = engine.run_experiment(proj, "EXP-A")
    assert not res["executed"]
    res = engine.run_experiment(proj, "EXP-A", seeds=[0], allow_unvalidated=True)
    assert res["runs"][0]["validation"]["status"] == "PROVISIONAL"


def test_immutable_fields(proj):
    r = engine.run_experiment(proj, "EXP-A", seeds=[0])["runs"][0]
    with pytest.raises(ResearchError):
        update_run(proj, r, config_snapshot={})
    with pytest.raises(ResearchError):
        update_run(proj, load_run(proj, r["run_id"]), status="RUNNING")


def test_manual_import(proj, tmp_path):
    from research_engine.cli import main
    m = tmp_path / "bench.csv"
    m.write_text("metric,value\nscore,0.42\n", encoding="utf-8")
    att = tmp_path / "scope_capture.txt"
    att.write_text("oscilloscope export", encoding="utf-8")
    spec = make_spec("EXP-I", expected_samples=None, compute={"backend": "manual"},
                     expected_outputs=["metrics.json"])
    del spec["entrypoint"]
    save_spec(proj, spec)
    git_commit(proj.root)
    assert main(["--project", str(proj.root), "import", "EXP-I", "--metrics", str(m),
                 "--attach", str(att), "--by", "Lab Tech", "--seed", "0"]) == 0
    r = list_runs(proj, "EXP-I")[0]
    assert r["status"] == "IMPORTED" and r["metrics"]["score"] == 0.42
    assert (proj.runs_raw / r["run_id"] / "imported" / "scope_capture.txt").exists()
    assert r["validation"]["status"] == "VALIDATED"
