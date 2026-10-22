"""Pure statistics for the analytics depth endpoints.

No I/O and no framework imports, for the same reason
:mod:`app.services.analytics_rules` is pure: a number that decides whether a
setup is ranked must be testable without a database.

The confidence interval is the normal approximation of the mean — the
sample standard deviation divided by :math:`\\sqrt{n}`, scaled by the 95%
z-score. With the configured minimum sample (20 by default) that is the
standard, defensible reading of "the average with its error bars"; a setup
below the minimum is marked insufficient rather than ranked on noise.
"""

from __future__ import annotations

import math
import os

# Two-sided 95% normal interval.
CONFIDENCE_LEVEL = 0.95
CONFIDENCE_Z = 1.959963984540054

DEFAULT_MIN_SAMPLE = 20


def min_sample_size() -> int:
    """The configured minimum decided trades before a setup is ranked.

    ``MIN_SAMPLE_SIZE`` is read per call so a test (or a settings reload)
    can change it without re-importing the module. A malformed value falls
    back to the default instead of crashing an analytics request.
    """
    raw = os.getenv("MIN_SAMPLE_SIZE", "").strip()
    if not raw:
        return DEFAULT_MIN_SAMPLE
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MIN_SAMPLE


def mean_confidence(values: list[float]) -> dict:
    """Mean, sample standard deviation and the 95% interval of the mean.

    Returns ``None`` for every derived field when there is nothing to
    measure. One observation has a mean but no interval — there is no way
    to estimate dispersion from a single point.
    """
    n = len(values)
    if n == 0:
        return {
            "sample_size": 0,
            "mean": None,
            "std_dev": None,
            "standard_error": None,
            "ci_low": None,
            "ci_high": None,
            "ci_level": CONFIDENCE_LEVEL,
        }

    mean = sum(values) / n
    if n < 2:
        return {
            "sample_size": n,
            "mean": round(mean, 2),
            "std_dev": None,
            "standard_error": None,
            "ci_low": None,
            "ci_high": None,
            "ci_level": CONFIDENCE_LEVEL,
        }

    variance = sum((value - mean) ** 2 for value in values) / (n - 1)
    std_dev = math.sqrt(variance)
    standard_error = std_dev / math.sqrt(n)
    margin = CONFIDENCE_Z * standard_error
    return {
        "sample_size": n,
        "mean": round(mean, 2),
        "std_dev": round(std_dev, 2),
        "standard_error": round(standard_error, 2),
        "ci_low": round(mean - margin, 2),
        "ci_high": round(mean + margin, 2),
        "ci_level": CONFIDENCE_LEVEL,
    }


def drawdown_curve(nets: list[float]) -> dict:
    """Peak-to-trough drawdown of a cumulative series that starts at zero.

    ``max_drawdown`` is the worst ``equity - peak`` (a negative number, or
    zero when the series never went underwater), the same sign convention as
    the equity chart's ``drawdown`` points. ``peak`` is the highest
    cumulative result reached, and ``current_drawdown`` is where the series
    sits relative to that peak at the end.
    """
    equity = peak = 0.0
    max_drawdown = 0.0
    for net in nets:
        equity += net
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "net_pnl": round(equity, 2),
        "peak": round(peak, 2),
        "max_drawdown": round(max_drawdown, 2),
        "current_drawdown": round(equity - peak, 2),
    }


def ruin_probability(
    win_rate_pct: float,
    payoff_ratio: float | None,
    risk_units: float | None,
) -> float | None:
    """Probability of losing the account, by the diffusion approximation.

    Each trade is a step of ``+b`` risk units on a win and ``-1`` on a loss,
    with ``p`` the win rate and ``b`` the payoff ratio (average win / average
    loss). The step mean is ``mu = p*b - q`` and its variance is
    ``p*b^2 + q - mu^2``. For a random walk with drift ``mu`` and variance
    ``sigma^2``, the probability of ever falling ``N`` units (the account
    size measured in risk units) is ``exp(-2*mu*N/sigma^2)`` when ``mu > 0``.

    A book with no edge ruins almost surely, so ``mu <= 0`` returns ``1.0``.
    ``None`` means the inputs cannot size the bet (no risk figure), which is
    different from a zero probability.
    """
    if risk_units is None or risk_units <= 0:
        return None

    p = max(0.0, min(1.0, win_rate_pct / 100.0))
    q = 1.0 - p
    if p <= 0.0:
        return 1.0
    if q <= 0.0:
        return 0.0
    if payoff_ratio is None or payoff_ratio <= 0:
        return 1.0

    mean = p * payoff_ratio - q
    variance = p * payoff_ratio**2 + q - mean**2
    if variance <= 0:
        return 0.0 if mean > 0 else 1.0
    if mean <= 0:
        return 1.0
    return min(1.0, math.exp(-2.0 * mean * risk_units / variance))
