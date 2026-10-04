"""Domain-free statistics with explicit assumption checks.

No test is applied silently. ``compare_two`` returns the test it used, *why* it chose
it, every assumption check it ran (with its own caveats), the sample sizes, and
warnings -- and refuses to test at all below a minimum sample size rather than
produce a meaningless p-value.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np
from scipy import stats as sps

TESTS = ("auto", "welch_t", "student_t", "paired_t", "mann_whitney", "wilcoxon",
         "permutation", "none")
MIN_N_FOR_TEST = 3


def describe(values: Sequence[float], confidence: float = 0.95) -> dict[str, Any]:
    x = np.asarray(values, dtype=float)
    n = int(x.size)
    out: dict[str, Any] = {"n": n}
    if n == 0:
        return out
    out.update(mean=float(x.mean()), median=float(np.median(x)), min=float(x.min()),
               max=float(x.max()), sum=float(x.sum()))
    if n >= 2:
        sd = float(x.std(ddof=1))
        sem = sd / math.sqrt(n)
        h = float(sps.t.ppf((1 + confidence) / 2, n - 1)) * sem
        out.update(std=sd, sem=sem, ci_low=out["mean"] - h, ci_high=out["mean"] + h,
                   ci_method=f"t-interval ({confidence:.0%}, df={n - 1})",
                   cv=(sd / abs(out["mean"])) if out["mean"] else None)
    else:
        out.update(std=None, sem=None, ci_low=None, ci_high=None,
                   ci_method="not computable with n=1", cv=None)
    return out


def bootstrap_ci(values: Sequence[float], stat: Callable[[np.ndarray], float] = np.mean,
                 n_resamples: int = 5000, confidence: float = 0.95,
                 seed: int = 12345) -> dict[str, Any]:
    x = np.asarray(values, dtype=float)
    if x.size < 2:
        return {"low": None, "high": None, "method": "not computable with n<2"}
    rng = np.random.default_rng(seed)
    boots = np.array([stat(rng.choice(x, size=x.size, replace=True)) for _ in range(n_resamples)])
    a = (1 - confidence) / 2
    return {"low": float(np.quantile(boots, a)), "high": float(np.quantile(boots, 1 - a)),
            "method": f"percentile bootstrap ({n_resamples} resamples, seed {seed})"}


def normality(values: Sequence[float], alpha: float = 0.05) -> dict[str, Any]:
    x = np.asarray(values, dtype=float)
    if x.size < 3:
        return {"test": "shapiro", "p": None, "normal": None, "note": "n<3: not testable"}
    if np.ptp(x) == 0:
        return {"test": "shapiro", "p": None, "normal": None, "note": "zero variance"}
    p = float(sps.shapiro(x).pvalue)
    note = "low power at small n; non-rejection is not evidence of normality" if x.size < 20 else ""
    return {"test": "shapiro", "p": p, "normal": p > alpha, "note": note}


def hedges_g(a: np.ndarray, b: np.ndarray) -> float | None:
    na, nb = a.size, b.size
    if na < 2 or nb < 2:
        return None
    sp = math.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    if sp == 0:
        return None
    d = (b.mean() - a.mean()) / sp
    return float(d * (1 - 3 / (4 * (na + nb) - 9)))


def cohens_dz(diff: np.ndarray) -> float | None:
    if diff.size < 2 or diff.std(ddof=1) == 0:
        return None
    return float(diff.mean() / diff.std(ddof=1))


def rank_biserial_independent(u: float, na: int, nb: int) -> float:
    return float(1 - 2 * u / (na * nb))


def compare_two(a: Sequence[float], b: Sequence[float], paired: bool = False,
                test: str = "auto", alpha: float = 0.05, confidence: float = 0.95,
                n_permutations: int = 10000, seed: int = 12345) -> dict[str, Any]:
    """Compare group b against reference a. Positive difference = b larger than a."""
    if test not in TESTS:
        raise ValueError(f"unknown test {test!r}; choose from {TESTS}")
    A, B = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    res: dict[str, Any] = {"n_a": int(A.size), "n_b": int(B.size), "paired": paired,
                           "requested_test": test, "assumptions": {}, "warnings": []}
    if paired and A.size != B.size:
        raise ValueError("paired comparison needs equal-length, aligned samples")
    res["mean_difference"] = float(B.mean() - A.mean()) if A.size and B.size else None

    if min(A.size, B.size) < MIN_N_FOR_TEST or test == "none":
        res.update(test="none", p_value=None, statistic=None, effect_size=None,
                   rationale=(f"no test: n_a={A.size}, n_b={B.size} (< {MIN_N_FOR_TEST} replicates)"
                              if test != "none" else "researcher requested no test"))
        if test != "none":
            res["warnings"].append("insufficient replicates for inference; report descriptively only")
        return res

    if paired:
        d = B - A
        res["assumptions"]["normality_of_differences"] = normality(d, alpha)
        chosen = test
        if test == "auto":
            nrm = res["assumptions"]["normality_of_differences"]["normal"]
            chosen = "paired_t" if nrm else "wilcoxon"
            res["rationale"] = ("paired samples; differences not rejected as normal -> paired t-test"
                                if nrm else "paired samples; normality of differences rejected or "
                                "untestable -> Wilcoxon signed-rank")
        else:
            res["rationale"] = f"researcher-specified test: {test}"
        if chosen == "paired_t":
            r = sps.ttest_rel(B, A)
            sem = d.std(ddof=1) / math.sqrt(d.size)
            h = float(sps.t.ppf((1 + confidence) / 2, d.size - 1)) * sem
            res.update(test="paired_t", statistic=float(r.statistic), p_value=float(r.pvalue),
                       effect_size={"name": "cohens_dz", "value": cohens_dz(d)},
                       diff_ci=[float(d.mean() - h), float(d.mean() + h)])
        elif chosen == "wilcoxon":
            if np.all(d == 0):
                res.update(test="wilcoxon", statistic=None, p_value=1.0,
                           effect_size={"name": "matched_pairs_rank_biserial", "value": 0.0})
                res["warnings"].append("all paired differences are zero")
            else:
                r = sps.wilcoxon(B, A)
                nz = d[d != 0]
                ranks = sps.rankdata(np.abs(nz))
                rb = float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum())
                res.update(test="wilcoxon", statistic=float(r.statistic), p_value=float(r.pvalue),
                           effect_size={"name": "matched_pairs_rank_biserial", "value": rb})
            if d.size < 6:
                res["warnings"].append("Wilcoxon with n<6 cannot reach p<0.05 (two-sided)")
            ci = bootstrap_ci(d, confidence=confidence, seed=seed)
            res["diff_ci"] = [ci["low"], ci["high"]]
        elif chosen == "permutation":
            res.update(_perm_paired(d, n_permutations, seed))
            ci = bootstrap_ci(d, confidence=confidence, seed=seed)
            res["diff_ci"] = [ci["low"], ci["high"]]
        else:
            raise ValueError(f"test {chosen!r} is not valid for paired data")
    else:
        na_, nb_ = normality(A, alpha), normality(B, alpha)
        res["assumptions"].update(normality_a=na_, normality_b=nb_)
        if np.ptp(A) > 0 or np.ptp(B) > 0:
            lev = sps.levene(A, B)
            res["assumptions"]["levene"] = {"p": float(lev.pvalue),
                                            "equal_variance": float(lev.pvalue) > alpha}
        chosen = test
        if test == "auto":
            both = bool(na_["normal"]) and bool(nb_["normal"])
            chosen = "welch_t" if both else "mann_whitney"
            res["rationale"] = ("independent samples; neither group rejected as normal -> Welch t-test "
                                "(no equal-variance assumption)" if both else
                                "independent samples; normality rejected or untestable -> Mann-Whitney U")
        else:
            res["rationale"] = f"researcher-specified test: {test}"
        if chosen in ("welch_t", "student_t"):
            r = sps.ttest_ind(B, A, equal_var=(chosen == "student_t"))
            va, vb = A.var(ddof=1) / A.size, B.var(ddof=1) / B.size
            se = math.sqrt(va + vb)
            if chosen == "welch_t":
                df = (va + vb) ** 2 / (va ** 2 / (A.size - 1) + vb ** 2 / (B.size - 1)) if se else A.size + B.size - 2
            else:
                df = A.size + B.size - 2
            h = float(sps.t.ppf((1 + confidence) / 2, df)) * se
            md = float(B.mean() - A.mean())
            res.update(test=chosen, statistic=float(r.statistic), p_value=float(r.pvalue),
                       df=float(df), effect_size={"name": "hedges_g", "value": hedges_g(A, B)},
                       diff_ci=[md - h, md + h])
        elif chosen == "mann_whitney":
            r = sps.mannwhitneyu(B, A, alternative="two-sided")
            res.update(test="mann_whitney", statistic=float(r.statistic), p_value=float(r.pvalue),
                       effect_size={"name": "rank_biserial",
                                    "value": -rank_biserial_independent(float(r.statistic), B.size, A.size)})
            if min(A.size, B.size) < 4:
                res["warnings"].append("Mann-Whitney with n<4 per group cannot reach p<0.05 (two-sided)")
        elif chosen == "permutation":
            res.update(_perm_independent(A, B, n_permutations, seed))
        else:
            raise ValueError(f"test {chosen!r} is not valid for independent data")
    p = res.get("p_value")
    res["significant_at_alpha"] = (p is not None and p < alpha)
    res["alpha"] = alpha
    return res


def _perm_independent(A, B, n, seed):
    rng = np.random.default_rng(seed)
    obs = B.mean() - A.mean()
    pooled = np.concatenate([A, B])
    hits = 0
    for _ in range(n):
        rng.shuffle(pooled)
        if abs(pooled[A.size:].mean() - pooled[:A.size].mean()) >= abs(obs) - 1e-12:
            hits += 1
    return {"test": "permutation", "statistic": float(obs), "p_value": (hits + 1) / (n + 1),
            "effect_size": {"name": "hedges_g", "value": hedges_g(A, B)},
            "permutations": n}


def _perm_paired(d, n, seed):
    rng = np.random.default_rng(seed)
    obs = d.mean()
    hits = 0
    for _ in range(n):
        signs = rng.choice([-1, 1], size=d.size)
        if abs((signs * d).mean()) >= abs(obs) - 1e-12:
            hits += 1
    return {"test": "permutation", "statistic": float(obs), "p_value": (hits + 1) / (n + 1),
            "effect_size": {"name": "cohens_dz", "value": cohens_dz(d)}, "permutations": n}


def adjust_pvalues(pvalues: Sequence[float | None], method: str = "holm") -> list[float | None]:
    """Holm or Bonferroni adjustment. None entries (no test) are passed through."""
    idx = [i for i, p in enumerate(pvalues) if p is not None]
    ps = [float(pvalues[i]) for i in idx]
    m = len(ps)
    adj: list[float] = [0.0] * m
    if method == "none" or m == 0:
        adj = ps
    elif method == "bonferroni":
        adj = [min(1.0, p * m) for p in ps]
    elif method == "holm":
        order = sorted(range(m), key=lambda i: ps[i])
        running = 0.0
        for rank, i in enumerate(order):
            running = max(running, min(1.0, (m - rank) * ps[i]))
            adj[i] = running
    else:
        raise ValueError(f"unknown correction {method!r}")
    out: list[float | None] = [None] * len(pvalues)
    for k, i in enumerate(idx):
        out[i] = adj[k]
    return out
