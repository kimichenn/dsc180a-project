"""The statistics the main analysis reports. The unit is always a log: repeats are averaged within a log first.

- bootstrap_ci: 95% percentile interval of a mean, resampling whole logs.
- sign_flip_p: two-sided sign-flip test of a mean paired difference. It assumes that with no effect each
  log's difference is symmetric about zero, so its sign is as likely flipped as not.
- holm: Holm-Bonferroni adjusted p-values for a family of tests.
- one_sided_bound: the exact one-sided 95% bound on a share observed at 0 or 1.
"""

from __future__ import annotations

import random

SEED = 180
ALPHA = 0.05
BOOTSTRAP_DRAWS = 10_000
EXACT_MAX_LOGS = 20  # enumerate every sign pattern up to this many nonzero differences (2^20 patterns)
RANDOM_FLIPS = 100_000
_TOLERANCE = 1e-9  # differences are means of a few 0/1 outcomes, so equal sums differ only by float rounding


def bootstrap_ci(values: list[float]) -> tuple[float, float]:
    """95% percentile interval of the mean, resampling whole logs."""
    rng = random.Random(SEED)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(BOOTSTRAP_DRAWS))
    return means[round(0.025 * (BOOTSTRAP_DRAWS - 1))], means[round(0.975 * (BOOTSTRAP_DRAWS - 1))]


def sign_flip_p(values: list[float]) -> float:
    """Two-sided p-value for a mean difference of zero: the share of sign patterns whose mean is at
    least as far from zero as the observed one. A zero difference is the same under either sign, so
    only the nonzero ones flip: every pattern exactly when at most EXACT_MAX_LOGS are nonzero,
    otherwise RANDOM_FLIPS random patterns (counting the observed one)."""
    nonzero = [v for v in values if v != 0]
    observed = abs(sum(nonzero))
    if observed < _TOLERANCE:
        return 1.0
    if len(nonzero) <= EXACT_MAX_LOGS:
        sums = _signed_sums(nonzero)
        return sum(abs(s) >= observed - _TOLERANCE for s in sums) / len(sums)
    rng = random.Random(SEED)
    extreme = sum(abs(sum(v if rng.random() < 0.5 else -v for v in nonzero)) >= observed - _TOLERANCE for _ in range(RANDOM_FLIPS))
    return (extreme + 1) / (RANDOM_FLIPS + 1)


def _signed_sums(values: list[float]) -> list[float]:
    """The sum under each of the 2^len(values) ways to sign the values."""
    sums = [0.0]
    for v in values:
        sums = [s + v for s in sums] + [s - v for s in sums]
    return sums


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values: a test is rejected at familywise ALPHA when its adjusted p is at most ALPHA."""
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def one_sided_bound(observed: int, n: int) -> float:
    """The exact (Clopper-Pearson) one-sided 95% bound on a share observed as 0 of n or n of n: the upper
    bound for 0, which solves (1 - p)^n = ALPHA, and the lower bound for n, which solves p^n = ALPHA."""
    if observed not in (0, n):
        raise ValueError("the closed form holds only for a share observed at 0 or 1")
    return 1 - ALPHA ** (1 / n) if observed == 0 else ALPHA ** (1 / n)
