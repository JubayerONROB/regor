import numpy as np
import pytest
from scipy import stats as sps

from research_engine.analysis import stats


def test_describe_matches_scipy():
    x = [1.0, 2.0, 4.0, 7.0]
    d = stats.describe(x)
    assert d["n"] == 4 and d["mean"] == pytest.approx(3.5)
    assert d["std"] == pytest.approx(np.std(x, ddof=1))
    lo, hi = sps.t.interval(0.95, 3, loc=3.5, scale=sps.sem(x))
    assert d["ci_low"] == pytest.approx(lo) and d["ci_high"] == pytest.approx(hi)


def test_describe_n1_no_interval():
    d = stats.describe([5.0])
    assert d["std"] is None and d["ci_low"] is None


def test_welch_matches_scipy():
    a, b = [1.0, 1.2, 0.9, 1.1, 1.05], [1.5, 1.7, 1.4, 1.65, 1.55]
    r = stats.compare_two(a, b, test="welch_t")
    ref = sps.ttest_ind(b, a, equal_var=False)
    assert r["p_value"] == pytest.approx(ref.pvalue) and r["statistic"] == pytest.approx(ref.statistic)
    assert r["effect_size"]["name"] == "hedges_g" and r["effect_size"]["value"] > 0


def test_paired_t_matches_scipy():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [1.3, 2.1, 3.4, 4.2, 5.6]
    r = stats.compare_two(a, b, paired=True, test="paired_t")
    assert r["p_value"] == pytest.approx(sps.ttest_rel(b, a).pvalue)
    lo, hi = r["diff_ci"]
    assert lo < np.mean(np.subtract(b, a)) < hi


def test_auto_selection_records_rationale_and_assumptions():
    rng = np.random.default_rng(0)
    a, b = rng.normal(0, 1, 30), rng.normal(0.5, 1, 30)
    r = stats.compare_two(a, b)
    assert r["test"] in ("welch_t", "mann_whitney") and r["rationale"]
    assert "normality_a" in r["assumptions"] and "levene" in r["assumptions"]
    skew = np.concatenate([np.zeros(20), [50.0, 60.0, 80.0]])
    r2 = stats.compare_two(skew, skew + 1)
    assert r2["test"] == "mann_whitney"


def test_too_few_replicates_no_test():
    r = stats.compare_two([1.0, 2.0], [3.0, 4.0])
    assert r["test"] == "none" and r["p_value"] is None and r["warnings"]


def test_small_wilcoxon_warns():
    r = stats.compare_two([1, 2, 3, 4], [2, 3.5, 3.1, 6], paired=True, test="wilcoxon")
    assert any("cannot reach" in w for w in r["warnings"])


def test_permutation_reasonable():
    a, b = [1, 2, 3, 4, 5, 6], [11, 12, 13, 14, 15, 16]
    r = stats.compare_two(a, b, test="permutation", n_permutations=2000)
    assert r["p_value"] < 0.01


def test_holm_and_bonferroni():
    p = [0.01, 0.04, 0.03, None]
    holm = stats.adjust_pvalues(p, "holm")
    assert holm[0] == pytest.approx(0.03) and holm[2] == pytest.approx(0.06) and holm[1] == pytest.approx(0.06)
    assert holm[3] is None
    assert stats.adjust_pvalues(p, "bonferroni")[1] == pytest.approx(0.12)


def test_bootstrap_deterministic():
    x = [1.0, 2.0, 3.0, 4.0, 10.0]
    assert stats.bootstrap_ci(x, seed=1) == stats.bootstrap_ci(x, seed=1)


def test_invalid_test_name():
    with pytest.raises(ValueError):
        stats.compare_two([1, 2, 3], [1, 2, 3], test="magic")
