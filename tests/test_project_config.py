import pytest

from regor import config, domains
from regor.cli import main
from regor.errors import ConfigError
from regor.project import Project, init_project


def test_init_creates_structure(tmp_path):
    p = init_project(tmp_path / "p1", "p1", "computer_vision")
    for d in ["research", "literature", "data", "experiments/configs", "runs/metadata", "evidence",
              "manuscript/sections", "docs/decisions", "src/models"]:
        assert (p.root / d).is_dir(), d
    for f in ["project.yaml", "README.md", ".gitignore", ".env.example", "evidence/claims.yaml",
              "literature/literature_matrix.csv", "experiments/configs/_TEMPLATE.yaml.example"]:
        assert (p.root / f).is_file(), f
    assert p.cfg["project"]["domain"] == "computer_vision"
    assert "gpu" in p.cfg["execution"]["approval"]["required_for_devices"]


def test_init_without_domain_is_generic(tmp_path):
    p = init_project(tmp_path / "g", None)
    assert p.domain.name == "generic"
    assert not any("accuracy" == m.name for m in p.domain.suggested_metrics)


def test_refuses_reinit_and_never_overwrites(tmp_path):
    p = init_project(tmp_path / "p", "p")
    (p.root / "README.md").write_text("mine", encoding="utf-8")
    with pytest.raises(ConfigError):
        init_project(tmp_path / "p", "p")
    init_project(tmp_path / "p", "p", force=True)
    assert (p.root / "README.md").read_text(encoding="utf-8") == "mine"


def test_unknown_domain_rejected(tmp_path):
    with pytest.raises(ConfigError):
        init_project(tmp_path / "x", "x", "astrology")


def test_custom_domain_yaml(tmp_path):
    p = init_project(tmp_path / "c", "c")
    (p.root / "domain.yaml").write_text(
        "name: acoustics\ndescription: room acoustics\nsuggested_metrics:\n"
        "  - {name: rt60_error, direction: lower, unit: s}\n", encoding="utf-8")
    prof = domains.get_profile("acoustics", p.root)
    assert prof.name == "acoustics" and prof.suggested_metrics[0].name == "rt60_error"


def test_schema_errors_collected():
    bad = config.with_defaults({"project": {"name": "", "domain": "generic"},
                                "statistics": {"alpha": 2}})
    errs = config.schema_errors(bad, "project")
    assert any("alpha" in e for e in errs) and any("name" in e for e in errs)


def test_project_find_walks_up(tmp_path):
    p = init_project(tmp_path / "w", "w")
    assert Project.find(p.root / "experiments" / "configs").root == p.root


def test_cli_init_check_status(tmp_path, capsys):
    assert main(["init", "cli_p", "--dir", str(tmp_path / "cli_p"), "--domain", "physics"]) == 0
    assert main(["--project", str(tmp_path / "cli_p"), "check"]) == 0
    assert main(["--project", str(tmp_path / "cli_p"), "status", "--write"]) == 0
    assert (tmp_path / "cli_p" / "reports" / "progress_reports" / "PROGRESS.md").exists()
    assert main(["--project", str(tmp_path / "cli_p"), "exp", "new", "EXP-9", "--title", "t"]) == 0
    out = capsys.readouterr().out
    assert "initialised project" in out


def test_cli_reports_errors_cleanly(tmp_path, capsys):
    assert main(["--project", str(tmp_path), "status"]) == 2
    assert "no project.yaml" in capsys.readouterr().err
