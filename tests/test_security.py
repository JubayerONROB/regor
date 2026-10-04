"""Secret scanner. Token-shaped strings are assembled at runtime so no secret-like literal
exists in the repository itself."""

from regor.security import scan_paths, scan_text

GH = "gh" + "p_" + "Z9y8X7w6V5" * 4
AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"


def test_detects_token_patterns_without_echoing_them():
    f = scan_text(f"x = '{GH}'\ny = '{AWS}'\n", "a.py")
    rules = {x.rule for x in f}
    assert {"github_token", "aws_access_key"} <= rules
    assert all(GH not in str(x) and AWS not in str(x) for x in f)


def test_sensitive_filenames_and_allowlist(tmp_path):
    (tmp_path / "pat.txt").write_text("anything")
    (tmp_path / "kaggle_alt.json").write_text("{}")
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / ".env.example").write_text("A=")
    (tmp_path / "ok.py").write_text("print('hello')")
    names = {f.path for f in scan_paths([tmp_path], tmp_path)}
    assert names == {"pat.txt", "kaggle_alt.json", ".env"}


def test_opt_out_marker():
    assert scan_text(f"FIXTURE = '{GH}'  # regor-allow-secret\n") == []


def test_generic_assignment():
    assert scan_text("password = 'correct-horse-battery-staple'\n")[0].rule == "generic_assignment"  # regor-allow-secret (fixture)
