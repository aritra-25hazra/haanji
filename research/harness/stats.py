"""Paired significance tests without SciPy.

McNemar's test for paired binary outcomes (a sentence is right or wrong
under two treatments), the paired t-test, and the t and chi-square tail
probabilities they need, implemented from the regularised incomplete beta
function. Enough for the report; checked against known values in the tests.
"""
from __future__ import annotations
import math
from typing import Sequence


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Numerical Recipes)."""
    MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
        c = 1.0 + aa / c; c = c if abs(c) > FPMIN else FPMIN
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
        c = 1.0 + aa / c; c = c if abs(c) > FPMIN else FPMIN
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: float) -> float:
    """Two-sided p-value for Student's t."""
    x = df / (df + t * t)
    return betainc(df / 2.0, 0.5, x)


def chi2_1_sf(x: float) -> float:
    """Survival function of chi-square with one degree of freedom."""
    return math.erfc(math.sqrt(max(x, 0.0) / 2.0))


def mcnemar(b: int, c: int, correction: bool = True) -> dict:
    """b: wrong under A but right under B; c: right under A but wrong under B."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "statistic": 0.0, "p": 1.0, "n_discordant": 0}
    num = (abs(b - c) - (1 if correction else 0)) ** 2
    stat = num / n
    return {"b": b, "c": c, "statistic": round(stat, 3), "p": chi2_1_sf(stat), "n_discordant": n}


def paired_t(diffs: Sequence[float]) -> dict:
    n = len(diffs)
    if n < 2:
        return {"n": n, "mean": diffs[0] if diffs else 0.0, "t": 0.0, "p": 1.0, "df": max(n - 1, 0)}
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return {"n": n, "mean": mean, "t": float("inf") if mean else 0.0, "p": 0.0 if mean else 1.0, "df": n - 1, "sd": 0.0}
    t = mean / (sd / math.sqrt(n))
    return {"n": n, "mean": mean, "sd": sd, "t": round(t, 3), "df": n - 1, "p": t_sf(abs(t), n - 1)}


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Effect size for two independent samples (pooled SD)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    sp = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    return (ma - mb) / sp if sp else 0.0


def fmt_p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"
