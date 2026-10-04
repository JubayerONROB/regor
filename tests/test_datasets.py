import pytest

from conftest import write_csv
from regor import datasets
from regor.errors import ConfigError, DatasetNotValidated


def _reg(proj, name, files, **extra):
    entry = {"name": name, "version": "1", "source": {"kind": "local", "access_verified": True},
             "license": {"name": "CC0-1.0"}, "files": files, **extra}
    datasets.register(proj, entry)
    return datasets.validate_dataset(proj, name)


def checks(result, level):
    return {i["check"] for i in result["items"] if i["level"] == level}


def test_fixture_dataset_passes(proj):
    r = datasets.latest_validation(proj, "toy")
    assert r["status"] == "PASS"
    assert (proj.root / "data" / "validation" / "toy.md").exists()


def test_split_leakage_detected(proj):
    write_csv(proj.root / "d2" / "train.csv", ["a", "y"], [[1, 0], [2, 1], [3, 0]])
    write_csv(proj.root / "d2" / "test.csv", ["a", "y"], [[3, 0], [4, 1]])
    r = _reg(proj, "leaky", [{"path": "d2/train.csv", "split": "train"},
                             {"path": "d2/test.csv", "split": "test"}], target="y")
    assert r["status"] == "FAIL" and "split_integrity" in checks(r, "FAIL")


def test_group_leakage_detected(proj):
    write_csv(proj.root / "d3" / "train.csv", ["subject", "v", "y"], [["s1", 1, 0], ["s2", 2, 1]])
    write_csv(proj.root / "d3" / "test.csv", ["subject", "v", "y"], [["s2", 9, 0], ["s3", 3, 1]])
    r = _reg(proj, "grp", [{"path": "d3/train.csv", "split": "train"},
                           {"path": "d3/test.csv", "split": "test"}], target="y", group_column="subject")
    assert "leakage" in checks(r, "FAIL")


def test_ranges_units_missing_and_target_leak(proj):
    write_csv(proj.root / "d4" / "m.csv", ["v_volts", "copy", "y"],
              [[1.0, 0, 0], [500, 1, 1], ["", 0, 0], ["abc", 1, 1]])
    r = _reg(proj, "meas", [{"path": "d4/m.csv"}], target="y",
             column_checks=[{"column": "v_volts", "unit": "V", "min": 0, "max": 400, "max_missing_fraction": 0.0},
                            {"column": "absent_col"}],
             metadata_requirements=["instrument"])
    f = checks(r, "FAIL")
    assert {"column_ranges", "units", "missing_observations", "leakage", "instrument_metadata"} <= f


def test_unknown_license_and_unverified_access_warn(proj):
    write_csv(proj.root / "d5" / "a.csv", ["x"], [[1], [2]])
    datasets.register(proj, {"name": "lic", "version": "1", "source": {"kind": "url"},
                             "license": {"name": "unknown"}, "files": [{"path": "d5/a.csv"}]})
    r = datasets.validate_dataset(proj, "lic")
    assert {"license", "access"} <= checks(r, "WARN")


def test_missing_file_fails_and_gate_blocks(proj):
    datasets.register(proj, {"name": "ghost", "version": "1", "source": {"kind": "local"},
                             "license": {"name": "x"}, "files": [{"path": "nope.csv"}]})
    r = datasets.validate_dataset(proj, "ghost")
    assert "files_exist" in checks(r, "FAIL")
    with pytest.raises(DatasetNotValidated):
        datasets.require_valid(proj, "ghost")


def test_changed_data_requires_revalidation(proj):
    datasets.require_valid(proj, "toy")
    p = proj.root / "data" / "toy" / "test.csv"
    p.write_text(p.read_text(encoding="utf-8") + "99,1.0,1\n", encoding="utf-8")
    with pytest.raises(DatasetNotValidated, match="changed"):
        datasets.require_valid(proj, "toy")


def test_duplicate_registration_refused(proj):
    with pytest.raises(ConfigError):
        datasets.register(proj, {"name": "toy", "version": "2", "source": {"kind": "local"},
                                 "license": {"name": "x"}, "files": [{"path": "data/toy/train.csv"}]})


def test_custom_check_and_broken_custom_check(proj):
    (proj.root / "mychecks.py").write_text(
        "def ok(project, entry):\n    return [{'level': 'WARN', 'check': 'custom', 'message': 'hello'}]\n"
        "def broken(project, entry):\n    raise RuntimeError('boom')\n", encoding="utf-8")
    write_csv(proj.root / "d6" / "a.csv", ["x"], [[1], [2]])
    r = _reg(proj, "cust", [{"path": "d6/a.csv"}], custom_checks=["mychecks:ok", "mychecks:broken"])
    assert "custom" in checks(r, "WARN") and "custom_check" in checks(r, "FAIL")


def test_time_continuity(proj):
    write_csv(proj.root / "d7" / "ts.csv", ["t", "v"], [[0.0, 1], [0.1, 2], [0.5, 3], [0.4, 4]])
    r = _reg(proj, "ts", [{"path": "d7/ts.csv"}], time_column="t", expected_interval=0.1)
    assert "timestamp_continuity" in checks(r, "FAIL")
