"""Kaggle adapter, tested only with MockKaggleClient and a fake CLI. No network, no credentials."""

import json

import pytest

from conftest import git_commit, make_spec, save_spec
from regor import approvals, engine
from regor.errors import ExecutionError, SecretDetected
from regor.executors import kaggle as K
from regor.experiments import config_sha256, list_runs, load_spec


def _approve(proj, exp, runs=1):
    approvals.grant(proj, exp, config_sha256(load_spec(proj, exp)), "kaggle", "Dr Test", max_runs=runs)


def test_kaggle_requires_approval(proj):
    res = engine.run_experiment(proj, "EXP-A", backend="kaggle", seeds=[0], kaggle_client=K.MockKaggleClient())
    assert not res["executed"] and any("approval" in p for p in res["plan"]["problems"])


def test_submit_and_collect_complete_but_mock_is_never_evidence(proj):
    _approve(proj, "EXP-A")
    client = K.MockKaggleClient(metrics={"score": 0.3})
    r = engine.run_experiment(proj, "EXP-A", backend="kaggle", seeds=[0], kaggle_client=client)["runs"][0]
    assert r["status"] == "SUBMITTED" and r["remote"]["slug"].startswith("mockuser/regor-exp-a-")
    kdir = proj.root / "runs" / "remote" / r["run_id"] / "kernel"
    meta = json.loads((kdir / "kernel-metadata.json").read_text())
    assert meta["is_private"] is True and meta["enable_gpu"] is False and meta["kernel_type"] == "script"
    code = (kdir / "regor_kernel.py").read_text()
    assert "BUNDLE" in code and "KAGGLE_KEY" not in code
    out = engine.collect_remote(proj, kaggle_client=client)
    assert out[0]["status"] == "COMPLETED"
    assert out[0]["validation"]["status"] == "INVALID"
    assert any("MOCK" in i["message"] for i in out[0]["validation"]["issues"])


def test_remote_failure_recorded(proj):
    _approve(proj, "EXP-A")
    client = K.MockKaggleClient(outcome="error", exit_code=1)
    engine.run_experiment(proj, "EXP-A", backend="kaggle", seeds=[0], kaggle_client=client)
    r = engine.collect_remote(proj, kaggle_client=client)[0]
    assert r["status"] == "FAILED" and "kaggle status 'error'" in r["error"]
    assert (proj.runs_raw / r["run_id"] / "execution.log").exists()


def test_still_running_stays_submitted(proj):
    _approve(proj, "EXP-A")
    client = K.MockKaggleClient(polls_until_done=3)
    engine.run_experiment(proj, "EXP-A", backend="kaggle", seeds=[0], kaggle_client=client)
    assert engine.collect_remote(proj, kaggle_client=client)[0]["status"] == "SUBMITTED"
    assert engine.collect_remote(proj, kaggle_client=client)[0]["status"] == "SUBMITTED"
    assert engine.collect_remote(proj, kaggle_client=client)[0]["status"] == "COMPLETED"


def test_push_retry_then_success_and_exhaustion(proj):
    proj.cfg["execution"]["kaggle"]["max_retries"] = 2
    _approve(proj, "EXP-A", runs=2)
    c1 = K.MockKaggleClient(fail_pushes=2)
    r = engine.run_experiment(proj, "EXP-A", backend="kaggle", seeds=[0], kaggle_client=c1)["runs"][0]
    assert r["status"] == "SUBMITTED" and r["remote"]["attempts"] == 3
    c2 = K.MockKaggleClient(fail_pushes=5)
    r = engine.run_experiment(proj, "EXP-A", backend="kaggle", seeds=[1], kaggle_client=c2)["runs"][0]
    assert r["status"] == "FAILED" and "after 3 attempt" in r["error"]


def test_secret_in_code_blocks_push(proj):
    token = "gh" + "p_" + "A1b2C3d4E5" * 4          # assembled at runtime: not a literal in the repo
    (proj.root / "experiments" / "scripts" / "leaky.py").write_text(f"TOKEN = '{token}'\n")
    save_spec(proj, make_spec("EXP-L", entrypoint={"command": ["{python}", "experiments/scripts/leaky.py"],
                                                   "code_files": ["experiments/scripts/leaky.py"]}, seeds=[0]))
    git_commit(proj.root)
    _approve(proj, "EXP-L")
    client = K.MockKaggleClient()
    r = engine.run_experiment(proj, "EXP-L", backend="kaggle", seeds=[0], kaggle_client=client)["runs"][0]
    assert r["status"] == "FAILED" and "secret" in r["error"]
    assert client.push_attempts == 0


def test_cli_client_credentials_only_in_child_env(tmp_path, monkeypatch):
    cred = tmp_path / "outside" / "kaggle.json"
    cred.parent.mkdir()
    fake_key = "0123456789abcdef" * 2
    cred.write_text(json.dumps({"username": "someone", "key": fake_key}))
    monkeypatch.setenv("REGOR_TEST_KAGGLE", str(cred))
    c = K.CliKaggleClient("REGOR_TEST_KAGGLE", executable="kaggle-not-installed")
    env = c._env()
    assert env["KAGGLE_USERNAME"] == "someone" and env["KAGGLE_KEY"] == fake_key
    import os
    assert os.environ.get("KAGGLE_KEY") != fake_key          # parent process env untouched
    assert "[REDACTED]" in K._redact(f"error for key {fake_key}")


def test_cli_client_missing_executable():
    c = K.CliKaggleClient(executable=None)
    c.exe = None
    with pytest.raises(ExecutionError, match="not installed"):
        c.status("a/b")
