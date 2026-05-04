"""Probability distributions for Monte Carlo assumptions."""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Type
from scipy import stats as scipy_stats


class DistributionType(Enum):
    NORMAL = "Normal"
    LOGNORMAL = "Lognormal"
    UNIFORM = "Uniform"
    TRIANGULAR = "Triangular"
    PERT = "PERT (BetaPERT)"
    BETA = "Beta"
    GAMMA = "Gamma"
    EXPONENTIAL = "Exponential"
    BINOMIAL = "Binomial"
    POISSON = "Poisson"


@dataclass
class ParamSpec:
    """Metadata for a single distribution parameter."""
    key: str
    label: str
    default: float
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    is_int: bool = False


@dataclass
class AssumptionDefinition:
    cell_address: str
    sheet_name: str
    distribution: DistributionType
    params: Dict[str, float]
    name: str = ""
    truncate_lower: Optional[float] = None
    truncate_upper: Optional[float] = None

    def label(self) -> str:
        return self.name or self.cell_address

    def params_summary(self) -> str:
        return ", ".join(f"{k}={v:g}" for k, v in self.params.items())


# ---------------------------------------------------------------------------
# Distribution implementations
# ---------------------------------------------------------------------------

class _Distribution:
    """Abstract base — each subclass defines param specs and sampling."""

    PARAMS: List[ParamSpec] = []

    @classmethod
    def sample(cls, params: Dict[str, float], n: int, rng: np.random.Generator) -> np.ndarray:
        raise NotImplementedError

    @classmethod
    def validate(cls, params: Dict[str, float]) -> Optional[str]:
        return None

    @classmethod
    def ppf(cls, u: np.ndarray, params: Dict[str, float]) -> Optional[np.ndarray]:
        """Percent-point function for Latin Hypercube. Return None to fall back to MC."""
        return None


class _Normal(_Distribution):
    PARAMS = [
        ParamSpec("mean",    "Mean",       0.0),
        ParamSpec("std_dev", "Std Dev",    1.0, min_val=1e-12),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        return rng.normal(params["mean"], params["std_dev"], n)

    @classmethod
    def validate(cls, params):
        if params.get("std_dev", 0) <= 0:
            return "Standard deviation must be > 0"
        return None

    @classmethod
    def ppf(cls, u, params):
        return scipy_stats.norm.ppf(u, params["mean"], params["std_dev"])


class _Lognormal(_Distribution):
    PARAMS = [
        ParamSpec("mean",    "Mean",    1.0, min_val=1e-12),
        ParamSpec("std_dev", "Std Dev", 0.3, min_val=1e-12),
    ]

    @classmethod
    def _underlying(cls, params):
        mean, sd = params["mean"], params["std_dev"]
        sigma2 = np.log(1.0 + (sd / mean) ** 2)
        mu = np.log(mean) - sigma2 / 2.0
        return mu, np.sqrt(sigma2)

    @classmethod
    def sample(cls, params, n, rng):
        mu, sigma = cls._underlying(params)
        return rng.lognormal(mu, sigma, n)

    @classmethod
    def validate(cls, params):
        if params.get("mean", 0) <= 0:
            return "Mean must be > 0"
        if params.get("std_dev", 0) <= 0:
            return "Std Dev must be > 0"
        return None

    @classmethod
    def ppf(cls, u, params):
        mu, sigma = cls._underlying(params)
        return scipy_stats.lognorm.ppf(u, sigma, scale=np.exp(mu))


class _Uniform(_Distribution):
    PARAMS = [
        ParamSpec("min", "Minimum", 0.0),
        ParamSpec("max", "Maximum", 1.0),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        return rng.uniform(params["min"], params["max"], n)

    @classmethod
    def validate(cls, params):
        if params.get("min", 0) >= params.get("max", 1):
            return "Minimum must be < Maximum"
        return None

    @classmethod
    def ppf(cls, u, params):
        lo, hi = params["min"], params["max"]
        return scipy_stats.uniform.ppf(u, lo, hi - lo)


class _Triangular(_Distribution):
    PARAMS = [
        ParamSpec("min",  "Minimum",     0.0),
        ParamSpec("mode", "Most Likely", 0.5),
        ParamSpec("max",  "Maximum",     1.0),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        lo, c, hi = params["min"], params["mode"], params["max"]
        c_rel = (c - lo) / (hi - lo)
        return scipy_stats.triang.rvs(c_rel, loc=lo, scale=hi - lo, size=n, random_state=rng)

    @classmethod
    def validate(cls, params):
        lo, c, hi = params.get("min", 0), params.get("mode", 0.5), params.get("max", 1)
        if lo >= hi:
            return "Minimum must be < Maximum"
        if not (lo <= c <= hi):
            return "Most Likely must be between Minimum and Maximum"
        return None

    @classmethod
    def ppf(cls, u, params):
        lo, c, hi = params["min"], params["mode"], params["max"]
        c_rel = (c - lo) / (hi - lo)
        return scipy_stats.triang.ppf(u, c_rel, loc=lo, scale=hi - lo)


class _PERT(_Distribution):
    """BetaPERT — preferred in project/risk analysis (smoother tails than Triangular)."""
    PARAMS = [
        ParamSpec("min",  "Minimum",     0.0),
        ParamSpec("mode", "Most Likely", 0.5),
        ParamSpec("max",  "Maximum",     1.0),
        ParamSpec("gamma", "Shape (γ)",  4.0, min_val=0.0),
    ]

    @classmethod
    def _ab(cls, params):
        lo, c, hi = params["min"], params["mode"], params["max"]
        gamma = params.get("gamma", 4.0)
        r = hi - lo
        alpha = 1.0 + gamma * (c - lo) / r
        beta  = 1.0 + gamma * (hi - c) / r
        return alpha, beta, lo, r

    @classmethod
    def sample(cls, params, n, rng):
        alpha, beta, lo, r = cls._ab(params)
        return scipy_stats.beta.rvs(alpha, beta, loc=lo, scale=r, size=n, random_state=rng)

    @classmethod
    def validate(cls, params):
        lo, c, hi = params.get("min", 0), params.get("mode", 0.5), params.get("max", 1)
        if lo >= hi:
            return "Minimum must be < Maximum"
        if not (lo <= c <= hi):
            return "Most Likely must be between Minimum and Maximum"
        if params.get("gamma", 4) < 0:
            return "Shape (γ) must be ≥ 0"
        return None

    @classmethod
    def ppf(cls, u, params):
        alpha, beta, lo, r = cls._ab(params)
        return scipy_stats.beta.ppf(u, alpha, beta, loc=lo, scale=r)


class _Beta(_Distribution):
    PARAMS = [
        ParamSpec("alpha",     "Alpha",     2.0, min_val=1e-12),
        ParamSpec("beta_val",  "Beta",      2.0, min_val=1e-12),
        ParamSpec("scale_min", "Scale Min", 0.0),
        ParamSpec("scale_max", "Scale Max", 1.0),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        lo, hi = params["scale_min"], params["scale_max"]
        return scipy_stats.beta.rvs(
            params["alpha"], params["beta_val"],
            loc=lo, scale=hi - lo, size=n, random_state=rng,
        )

    @classmethod
    def validate(cls, params):
        if params.get("alpha", 0) <= 0 or params.get("beta_val", 0) <= 0:
            return "Alpha and Beta must be > 0"
        if params.get("scale_min", 0) >= params.get("scale_max", 1):
            return "Scale Min must be < Scale Max"
        return None

    @classmethod
    def ppf(cls, u, params):
        lo, hi = params["scale_min"], params["scale_max"]
        return scipy_stats.beta.ppf(u, params["alpha"], params["beta_val"],
                                    loc=lo, scale=hi - lo)


class _Gamma(_Distribution):
    PARAMS = [
        ParamSpec("shape", "Shape (k)", 2.0, min_val=1e-12),
        ParamSpec("scale", "Scale (θ)", 1.0, min_val=1e-12),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        return rng.gamma(params["shape"], params["scale"], n)

    @classmethod
    def validate(cls, params):
        if params.get("shape", 0) <= 0 or params.get("scale", 0) <= 0:
            return "Shape and Scale must be > 0"
        return None

    @classmethod
    def ppf(cls, u, params):
        return scipy_stats.gamma.ppf(u, params["shape"], scale=params["scale"])


class _Exponential(_Distribution):
    PARAMS = [
        ParamSpec("mean", "Mean", 1.0, min_val=1e-12),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        return rng.exponential(params["mean"], n)

    @classmethod
    def validate(cls, params):
        if params.get("mean", 0) <= 0:
            return "Mean must be > 0"
        return None

    @classmethod
    def ppf(cls, u, params):
        return scipy_stats.expon.ppf(u, scale=params["mean"])


class _Binomial(_Distribution):
    PARAMS = [
        ParamSpec("trials", "Trials (n)",        10, min_val=1, is_int=True),
        ParamSpec("prob",   "Probability (p)", 0.5, min_val=0.0, max_val=1.0),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        return rng.binomial(int(params["trials"]), params["prob"], n).astype(float)

    @classmethod
    def validate(cls, params):
        if params.get("trials", 0) < 1:
            return "Trials must be ≥ 1"
        p = params.get("prob", 0.5)
        if not (0.0 <= p <= 1.0):
            return "Probability must be in [0, 1]"
        return None


class _Poisson(_Distribution):
    PARAMS = [
        ParamSpec("lam", "Lambda (λ)", 1.0, min_val=1e-12),
    ]

    @classmethod
    def sample(cls, params, n, rng):
        return rng.poisson(params["lam"], n).astype(float)

    @classmethod
    def validate(cls, params):
        if params.get("lam", 0) <= 0:
            return "Lambda must be > 0"
        return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DISTRIBUTION_REGISTRY: Dict[DistributionType, Type[_Distribution]] = {
    DistributionType.NORMAL:      _Normal,
    DistributionType.LOGNORMAL:   _Lognormal,
    DistributionType.UNIFORM:     _Uniform,
    DistributionType.TRIANGULAR:  _Triangular,
    DistributionType.PERT:        _PERT,
    DistributionType.BETA:        _Beta,
    DistributionType.GAMMA:       _Gamma,
    DistributionType.EXPONENTIAL: _Exponential,
    DistributionType.BINOMIAL:    _Binomial,
    DistributionType.POISSON:     _Poisson,
}


def sample_assumption(assumption: AssumptionDefinition, n: int,
                      rng: np.random.Generator) -> np.ndarray:
    cls = DISTRIBUTION_REGISTRY[assumption.distribution]
    samples = cls.sample(assumption.params, n, rng)

    if assumption.truncate_lower is not None:
        samples = np.maximum(samples, assumption.truncate_lower)
    if assumption.truncate_upper is not None:
        samples = np.minimum(samples, assumption.truncate_upper)

    return samples


def lhs_sample_assumption(assumption: AssumptionDefinition, n: int,
                           rng: np.random.Generator) -> np.ndarray:
    """Latin Hypercube sample — falls back to Monte Carlo when PPF is unavailable."""
    cls = DISTRIBUTION_REGISTRY[assumption.distribution]

    # Generate stratified uniform draws
    cut = np.linspace(0.0, 1.0, n + 1)
    u = rng.uniform(cut[:-1], cut[1:])
    rng.shuffle(u)

    # Clip away exact 0 and 1 to avoid infinite tails
    u = np.clip(u, 1e-9, 1.0 - 1e-9)

    ppf_vals = cls.ppf(u, assumption.params)
    if ppf_vals is None:
        samples = cls.sample(assumption.params, n, rng)
    else:
        samples = ppf_vals

    if assumption.truncate_lower is not None:
        samples = np.maximum(samples, assumption.truncate_lower)
    if assumption.truncate_upper is not None:
        samples = np.minimum(samples, assumption.truncate_upper)

    return samples
