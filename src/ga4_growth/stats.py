"""
Statistical helpers for the analysis notebooks.

Conversion differences between segments are compared with two proportion z
tests, Wilson intervals are used for the rates themselves because the counts in
the tail of the funnel are small, and Holm correction is applied whenever more
than two segments are compared at once.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import (
    proportion_confint,
    proportion_effectsize,
    proportions_ztest,
)


@dataclass
class ProportionTest:
    label: str
    rate_a: float
    rate_b: float
    absolute_diff: float
    relative_lift: float
    z_stat: float
    p_value: float
    ci_low: float
    ci_high: float

    def as_dict(self) -> dict:
        return self.__dict__


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    low, high = proportion_confint(successes, n, alpha=alpha, method="wilson")
    return float(low), float(high)


def two_proportion_test(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    label: str = "",
    alpha: float = 0.05,
) -> ProportionTest:
    """Test whether segment B converts differently from baseline segment A."""
    rate_a = successes_a / n_a if n_a else np.nan
    rate_b = successes_b / n_b if n_b else np.nan
    z_stat, p_value = proportions_ztest([successes_b, successes_a], [n_b, n_a])

    diff = rate_b - rate_a
    se = np.sqrt(rate_a * (1 - rate_a) / n_a + rate_b * (1 - rate_b) / n_b)
    z_crit = sps.norm.ppf(1 - alpha / 2)
    return ProportionTest(
        label=label,
        rate_a=rate_a,
        rate_b=rate_b,
        absolute_diff=diff,
        relative_lift=diff / rate_a if rate_a else np.nan,
        z_stat=float(z_stat),
        p_value=float(p_value),
        ci_low=diff - z_crit * se,
        ci_high=diff + z_crit * se,
    )


def compare_segments(
    df: pd.DataFrame,
    label_col: str,
    success_col: str,
    total_col: str,
    baseline: str | None = None,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Every segment against a baseline, with Holm adjusted p values.

    The baseline defaults to the largest segment, which is usually the one a
    product team treats as "normal".
    """
    data = df[[label_col, success_col, total_col]].dropna()
    if baseline is None:
        baseline = data.sort_values(total_col, ascending=False).iloc[0][label_col]
    base = data[data[label_col] == baseline].iloc[0]

    rows = []
    for _, row in data.iterrows():
        if row[label_col] == baseline:
            continue
        test = two_proportion_test(
            int(base[success_col]), int(base[total_col]),
            int(row[success_col]), int(row[total_col]),
            label=str(row[label_col]), alpha=alpha,
        )
        rows.append(test.as_dict())

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["p_adjusted"] = multipletests(out["p_value"], alpha=alpha, method="holm")[1]
    out["significant"] = out["p_adjusted"] < alpha
    out.insert(1, "baseline", baseline)
    return out.sort_values("absolute_diff").reset_index(drop=True)


def chi_square(table: pd.DataFrame) -> dict:
    """Chi square test of independence plus Cramer's V for effect size."""
    chi2, p, dof, expected = sps.chi2_contingency(table.to_numpy())
    n = table.to_numpy().sum()
    min_dim = min(table.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * min_dim)) if min_dim else np.nan
    return {"chi2": chi2, "p_value": p, "dof": dof, "cramers_v": cramers_v, "n": int(n)}


def bootstrap_mean_ci(values: np.ndarray, n_boot: int = 5000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float, float]:
    """Percentile bootstrap for a skewed mean such as order value."""
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    means = values[idx].mean(axis=1)
    return float(values.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def mann_whitney(a: np.ndarray, b: np.ndarray) -> dict:
    """Rank based comparison, used for order value where the tail is long."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    stat, p = sps.mannwhitneyu(a, b, alternative="two-sided")
    # Rank biserial correlation as the effect size.
    effect = 1 - (2 * stat) / (len(a) * len(b))
    return {"u_stat": float(stat), "p_value": float(p), "rank_biserial": float(effect),
            "median_a": float(np.median(a)), "median_b": float(np.median(b))}


def sample_size_per_arm(baseline_rate: float, relative_mde: float, power: float = 0.8, alpha: float = 0.05) -> int:
    """Sessions or users needed per arm to detect a relative lift."""
    treatment_rate = baseline_rate * (1 + relative_mde)
    if treatment_rate >= 1:
        raise ValueError(
            f"a {relative_mde:.0%} lift on a {baseline_rate:.1%} baseline goes past 100%"
        )
    effect = proportion_effectsize(treatment_rate, baseline_rate)
    n = NormalIndPower().solve_power(effect_size=effect, power=power, alpha=alpha, ratio=1.0)
    return int(np.ceil(n))


def detectable_lift(baseline_rate: float, n_per_arm: int, power: float = 0.8, alpha: float = 0.05) -> float:
    """Smallest relative lift a test of this size can pick up."""
    effect = NormalIndPower().solve_power(nobs1=n_per_arm, power=power, alpha=alpha, ratio=1.0)
    # Invert the arcsine transform used by proportion_effectsize.
    treatment_rate = np.sin(effect / 2 + np.arcsin(np.sqrt(baseline_rate))) ** 2
    return float(treatment_rate / baseline_rate - 1)


def experiment_plan(
    name: str,
    baseline_rate: float,
    daily_units_per_arm: float,
    relative_mde: float,
    power: float = 0.8,
    alpha: float = 0.05,
) -> dict:
    n = sample_size_per_arm(baseline_rate, relative_mde, power, alpha)
    return {
        "experiment": name,
        "baseline_rate": round(baseline_rate, 4),
        "relative_mde": relative_mde,
        "n_per_arm": n,
        "days_needed": int(np.ceil(n / daily_units_per_arm)) if daily_units_per_arm else np.nan,
        "power": power,
        "alpha": alpha,
    }
