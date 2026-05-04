"""Monte Carlo simulation engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
from scipy import stats as scipy_stats

from .distributions import (
    AssumptionDefinition,
    lhs_sample_assumption,
    sample_assumption,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ForecastDefinition:
    cell_address: str
    sheet_name: str
    name: str = ""

    def label(self) -> str:
        return self.name or self.cell_address

    def key(self) -> str:
        return f"{self.sheet_name}!{self.cell_address}"


@dataclass
class SimulationConfig:
    iterations: int = 1000
    seed: Optional[int] = None
    use_latin_hypercube: bool = False


@dataclass
class SimulationResults:
    forecast_name: str
    cell_key: str          # "Sheet!A1"
    values: np.ndarray     # shape (n_completed,)
    assumption_keys: List[str]
    elapsed_seconds: float = 0.0
    iterations_completed: int = 0

    # --- descriptive stats -------------------------------------------------

    @property
    def mean(self) -> float:
        return float(np.mean(self.values))

    @property
    def median(self) -> float:
        return float(np.median(self.values))

    @property
    def std_dev(self) -> float:
        return float(np.std(self.values, ddof=1)) if len(self.values) > 1 else 0.0

    @property
    def variance(self) -> float:
        return float(np.var(self.values, ddof=1)) if len(self.values) > 1 else 0.0

    @property
    def skewness(self) -> float:
        return float(scipy_stats.skew(self.values)) if len(self.values) > 2 else 0.0

    @property
    def kurtosis(self) -> float:
        return float(scipy_stats.kurtosis(self.values)) if len(self.values) > 3 else 0.0

    @property
    def minimum(self) -> float:
        return float(np.min(self.values))

    @property
    def maximum(self) -> float:
        return float(np.max(self.values))

    def percentile(self, p: float) -> float:
        return float(np.percentile(self.values, p))

    def prob_less_than(self, value: float) -> float:
        return float(np.mean(self.values < value))

    def prob_greater_than(self, value: float) -> float:
        return float(np.mean(self.values > value))

    def prob_between(self, lo: float, hi: float) -> float:
        return float(np.mean((self.values >= lo) & (self.values <= hi)))

    def summary(self) -> Dict[str, float]:
        return {
            "Mean":            self.mean,
            "Median":          self.median,
            "Std Dev":         self.std_dev,
            "Variance":        self.variance,
            "Skewness":        self.skewness,
            "Kurtosis":        self.kurtosis,
            "Minimum":         self.minimum,
            "Maximum":         self.maximum,
            "Range":           self.maximum - self.minimum,
            "5th Percentile":  self.percentile(5),
            "10th Percentile": self.percentile(10),
            "25th Percentile": self.percentile(25),
            "75th Percentile": self.percentile(75),
            "90th Percentile": self.percentile(90),
            "95th Percentile": self.percentile(95),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int], None]   # (completed, total)


class SimulationEngine:
    """Drives Monte Carlo iterations against a live Excel workbook."""

    # Crystal Ball highlight colours (RGB tuples for xlwings)
    ASSUMPTION_COLOR = (0, 255, 255)   # cyan
    FORECAST_COLOR   = (0, 255, 0)     # green

    def __init__(self, excel_interface) -> None:
        self.xl = excel_interface
        self.assumptions: List[AssumptionDefinition] = []
        self.forecasts: List[ForecastDefinition] = []
        self._stop_requested: bool = False

    # --- assumption / forecast management ----------------------------------

    def _asmp_key(self, a: AssumptionDefinition) -> str:
        return f"{a.sheet_name}!{a.cell_address}"

    def upsert_assumption(self, assumption: AssumptionDefinition) -> None:
        key = self._asmp_key(assumption)
        self.assumptions = [a for a in self.assumptions if self._asmp_key(a) != key]
        self.assumptions.append(assumption)
        if self.xl.is_connected:
            self.xl.set_cell_color(assumption.sheet_name, assumption.cell_address,
                                   self.ASSUMPTION_COLOR)

    def remove_assumption(self, sheet_name: str, cell_address: str) -> None:
        key = f"{sheet_name}!{cell_address}"
        self.assumptions = [a for a in self.assumptions if self._asmp_key(a) != key]
        if self.xl.is_connected:
            self.xl.clear_cell_color(sheet_name, cell_address)

    def upsert_forecast(self, forecast: ForecastDefinition) -> None:
        key = forecast.key()
        self.forecasts = [f for f in self.forecasts if f.key() != key]
        self.forecasts.append(forecast)
        if self.xl.is_connected:
            self.xl.set_cell_color(forecast.sheet_name, forecast.cell_address,
                                   self.FORECAST_COLOR)

    def remove_forecast(self, sheet_name: str, cell_address: str) -> None:
        key = f"{sheet_name}!{cell_address}"
        self.forecasts = [f for f in self.forecasts if f.key() != key]
        if self.xl.is_connected:
            self.xl.clear_cell_color(sheet_name, cell_address)

    def clear_all(self) -> None:
        for a in self.assumptions:
            if self.xl.is_connected:
                self.xl.clear_cell_color(a.sheet_name, a.cell_address)
        for f in self.forecasts:
            if self.xl.is_connected:
                self.xl.clear_cell_color(f.sheet_name, f.cell_address)
        self.assumptions.clear()
        self.forecasts.clear()

    def request_stop(self) -> None:
        self._stop_requested = True

    # --- simulation --------------------------------------------------------

    def run(
        self,
        config: SimulationConfig,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[SimulationResults]:
        """Execute the simulation and return results for every forecast cell."""

        self._stop_requested = False
        n = config.iterations
        rng = np.random.default_rng(config.seed)
        t0 = time.perf_counter()

        # Pre-generate all samples up front so Excel sees clean sequential writes
        sample_fn = lhs_sample_assumption if config.use_latin_hypercube else sample_assumption
        presampled: Dict[str, np.ndarray] = {
            self._asmp_key(a): sample_fn(a, n, rng)
            for a in self.assumptions
        }

        # Save original cell values so we can restore them after the run
        originals: Dict[str, object] = {
            self._asmp_key(a): self.xl.get_cell_value(a.sheet_name, a.cell_address)
            for a in self.assumptions
        }

        forecast_buckets: Dict[str, list] = {f.key(): [] for f in self.forecasts}
        completed = 0

        try:
            for i in range(n):
                if self._stop_requested:
                    break

                # Write assumption samples into Excel
                for a in self.assumptions:
                    self.xl.set_cell_value(
                        a.sheet_name, a.cell_address,
                        float(presampled[self._asmp_key(a)][i]),
                    )

                # Force full recalculation
                self.xl.calculate()

                # Harvest forecast cells
                for fc in self.forecasts:
                    raw = self.xl.get_cell_value(fc.sheet_name, fc.cell_address)
                    try:
                        forecast_buckets[fc.key()].append(float(raw))
                    except (TypeError, ValueError):
                        forecast_buckets[fc.key()].append(np.nan)

                completed += 1
                if progress_cb:
                    # Fire every ~1 % and always on the last iteration
                    if completed % max(1, n // 100) == 0 or completed == n:
                        progress_cb(completed, n)

        finally:
            # Always restore original values
            for a in self.assumptions:
                self.xl.set_cell_value(a.sheet_name, a.cell_address,
                                       originals[self._asmp_key(a)])
            self.xl.calculate()

        elapsed = time.perf_counter() - t0

        results: List[SimulationResults] = []
        for fc in self.forecasts:
            raw_vals = np.array(forecast_buckets[fc.key()], dtype=float)
            clean = raw_vals[~np.isnan(raw_vals)]
            results.append(SimulationResults(
                forecast_name=fc.label(),
                cell_key=fc.key(),
                values=clean,
                assumption_keys=[self._asmp_key(a) for a in self.assumptions],
                elapsed_seconds=elapsed,
                iterations_completed=completed,
            ))

        return results

    # --- sensitivity analysis ----------------------------------------------

    def sensitivity_analysis(
        self,
        results: List[SimulationResults],
        presampled: Dict[str, np.ndarray],
    ) -> Dict[str, Dict[str, float]]:
        """
        Spearman rank correlations between each assumption and each forecast.
        Returns {forecast_key: {assumption_key: correlation}}.
        """
        sensitivity: Dict[str, Dict[str, float]] = {}
        for res in results:
            n = len(res.values)
            corrs: Dict[str, float] = {}
            for a_key, samples in presampled.items():
                trimmed = samples[:n]
                if len(trimmed) == n and n > 2:
                    corr, _ = scipy_stats.spearmanr(trimmed, res.values)
                    corrs[a_key] = float(corr)
            sensitivity[res.cell_key] = corrs
        return sensitivity
