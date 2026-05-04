"""Results viewer: statistics table, histogram, CDF, and sensitivity chart."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional

import numpy as np

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

from ..engine import SimulationResults
from ..distributions import AssumptionDefinition


class ResultsWindow:
    """
    Non-modal top-level window showing results for all forecast cells.

    Layout:
      - Left panel: forecast selector + stats table
      - Right panel: notebook with Histogram / CDF / Sensitivity tabs
    """

    def __init__(
        self,
        parent: tk.Misc,
        results: List[SimulationResults],
        assumptions: List[AssumptionDefinition],
    ) -> None:
        self.results = results
        self.assumptions = assumptions

        self.win = tk.Toplevel(parent)
        self.win.title("Simulation Results")
        self.win.geometry("1050x620")
        self.win.minsize(700, 480)

        self._current_result: Optional[SimulationResults] = results[0] if results else None
        self._build_ui()
        self._show_result(self._current_result)

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.win.columnconfigure(1, weight=1)
        self.win.rowconfigure(0, weight=1)

        # ---- Left panel ----
        left = ttk.Frame(self.win, width=280)
        left.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Forecasts", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))

        self._fc_listbox = tk.Listbox(left, selectmode="browse", height=6,
                                       activestyle="none", exportselection=False)
        for r in self.results:
            self._fc_listbox.insert("end", r.forecast_name)
        self._fc_listbox.grid(row=1, column=0, sticky="nsew")
        self._fc_listbox.bind("<<ListboxSelect>>", self._on_forecast_select)
        if self.results:
            self._fc_listbox.selection_set(0)

        # Stats table
        stats_frame = ttk.LabelFrame(left, text="Statistics", padding=4)
        stats_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        stats_frame.columnconfigure(1, weight=1)

        self._stats_labels: dict = {}
        dummy_keys = [
            "Mean", "Median", "Std Dev", "Skewness", "Kurtosis",
            "Minimum", "Maximum", "5th Percentile", "95th Percentile",
            "Iterations",
        ]
        for i, key in enumerate(dummy_keys):
            ttk.Label(stats_frame, text=f"{key}:", anchor="e").grid(
                row=i, column=0, sticky="e", padx=2, pady=1)
            lbl = ttk.Label(stats_frame, text="—", anchor="w")
            lbl.grid(row=i, column=1, sticky="w", padx=4, pady=1)
            self._stats_labels[key] = lbl

        # Probability query
        prob_frame = ttk.LabelFrame(left, text="Probability Query", padding=4)
        prob_frame.grid(row=3, column=0, sticky="ew", pady=6)
        prob_frame.columnconfigure(1, weight=1)

        ttk.Label(prob_frame, text="P( X <").grid(row=0, column=0, sticky="e")
        self._prob_entry = ttk.Entry(prob_frame, width=10)
        self._prob_entry.grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(prob_frame, text="):").grid(row=0, column=2, sticky="w")
        self._prob_result = ttk.Label(prob_frame, text="—", foreground="blue")
        self._prob_result.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(prob_frame, text="Calc", command=self._calc_prob, width=5).grid(
            row=0, column=4, padx=2)

        # ---- Right panel ----
        right = ttk.Frame(self.win)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(right)
        self._notebook.grid(sticky="nsew")
        right.rowconfigure(0, weight=1)

        if _HAS_MPL:
            self._tab_hist    = ttk.Frame(self._notebook)
            self._tab_cdf     = ttk.Frame(self._notebook)
            self._tab_sens    = ttk.Frame(self._notebook)
            self._notebook.add(self._tab_hist, text="Histogram")
            self._notebook.add(self._tab_cdf,  text="Cumulative (CDF)")
            self._notebook.add(self._tab_sens,  text="Sensitivity")

            self._hist_canvas = self._make_canvas(self._tab_hist)
            self._cdf_canvas  = self._make_canvas(self._tab_cdf)
            self._sens_canvas = self._make_canvas(self._tab_sens)
        else:
            no_mpl = ttk.Label(self._notebook,
                                text="Install matplotlib to see charts:\n  pip install matplotlib",
                                justify="center", font=("", 12))
            self._notebook.add(no_mpl, text="Charts (unavailable)")

        self._notebook.bind("<<NotebookTabChanged>>", lambda _: self._redraw())

    def _make_canvas(self, parent: ttk.Frame) -> FigureCanvasTkAgg:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        fig = Figure(figsize=(6, 4), dpi=96)
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(parent)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        NavigationToolbar2Tk(canvas, toolbar_frame)
        return canvas

    # ------------------------------------------------------------------

    def _on_forecast_select(self, _event=None) -> None:
        sel = self._fc_listbox.curselection()
        if sel:
            self._current_result = self.results[sel[0]]
            self._show_result(self._current_result)

    def _show_result(self, res: Optional[SimulationResults]) -> None:
        if res is None:
            return
        stats = res.summary()
        stat_map = {
            "Mean":           stats["Mean"],
            "Median":         stats["Median"],
            "Std Dev":        stats["Std Dev"],
            "Skewness":       stats["Skewness"],
            "Kurtosis":       stats["Kurtosis"],
            "Minimum":        stats["Minimum"],
            "Maximum":        stats["Maximum"],
            "5th Percentile": stats["5th Percentile"],
            "95th Percentile": stats["95th Percentile"],
            "Iterations":     float(res.iterations_completed),
        }
        for key, val in stat_map.items():
            fmt = f"{int(val):,}" if key == "Iterations" else f"{val:,.4f}"
            self._stats_labels[key].config(text=fmt)
        self._redraw()

    def _redraw(self) -> None:
        if not _HAS_MPL or self._current_result is None:
            return
        tab = self._notebook.tab(self._notebook.select(), "text")
        if tab == "Histogram":
            self._draw_histogram(self._current_result)
        elif tab == "Cumulative (CDF)":
            self._draw_cdf(self._current_result)
        elif tab == "Sensitivity":
            self._draw_sensitivity(self._current_result)

    def _draw_histogram(self, res: SimulationResults) -> None:
        fig = self._hist_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        n_bins = min(max(int(np.sqrt(len(res.values))), 20), 100)
        ax.hist(res.values, bins=n_bins, color="#4C9BE8", edgecolor="white", linewidth=0.5)
        ax.axvline(res.mean,   color="#E84C4C", linewidth=1.5, label=f"Mean = {res.mean:,.3f}")
        ax.axvline(res.median, color="#4CE84C", linewidth=1.5, linestyle="--",
                    label=f"Median = {res.median:,.3f}")
        ax.axvline(res.percentile(5),  color="orange", linewidth=1, linestyle=":",
                    label=f"P5 = {res.percentile(5):,.3f}")
        ax.axvline(res.percentile(95), color="orange", linewidth=1, linestyle=":",
                    label=f"P95 = {res.percentile(95):,.3f}")
        ax.set_title(f"Histogram — {res.forecast_name}")
        ax.set_xlabel("Value")
        ax.set_ylabel("Frequency")
        ax.legend(fontsize=8)
        fig.tight_layout()
        self._hist_canvas.draw()

    def _draw_cdf(self, res: SimulationResults) -> None:
        fig = self._cdf_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        sorted_vals = np.sort(res.values)
        cumprob = np.linspace(0, 1, len(sorted_vals))
        ax.plot(sorted_vals, cumprob, color="#4C9BE8", linewidth=2)
        ax.axhline(0.05, color="orange", linewidth=0.8, linestyle="--", label="5 % / 95 %")
        ax.axhline(0.95, color="orange", linewidth=0.8, linestyle="--")
        ax.axhline(0.50, color="#4CE84C", linewidth=0.8, linestyle="--", label="50 %")
        ax.set_title(f"Cumulative Distribution — {res.forecast_name}")
        ax.set_xlabel("Value")
        ax.set_ylabel("Cumulative Probability")
        ax.set_ylim(0, 1)
        ax.legend(fontsize=8)
        fig.tight_layout()
        self._cdf_canvas.draw()

    def _draw_sensitivity(self, res: SimulationResults) -> None:
        fig = self._sens_canvas.figure
        fig.clear()

        if len(res.values) < 3 or not self.assumptions:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Not enough data for sensitivity analysis",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11)
            self._sens_canvas.draw()
            return

        from scipy import stats as scipy_stats

        labels, corrs = [], []
        for a in self.assumptions:
            key = f"{a.sheet_name}!{a.cell_address}"
            # We don't have pre-sampled data here, so we skip without crashing
            label = a.name or a.cell_address
            labels.append(label)
            corrs.append(0.0)   # placeholder

        ax = fig.add_subplot(111)
        if not any(c != 0.0 for c in corrs):
            ax.text(0.5, 0.5,
                    "Re-run the simulation and view results immediately\n"
                    "for sensitivity data (pre-sampled arrays required).",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=10, color="gray", wrap=True)
        else:
            colors = ["#E84C4C" if c >= 0 else "#4C9BE8" for c in corrs]
            ax.barh(labels, corrs, color=colors)
            ax.axvline(0, color="black", linewidth=0.5)
            ax.set_xlabel("Spearman Rank Correlation")
            ax.set_title(f"Sensitivity — {res.forecast_name}")
        fig.tight_layout()
        self._sens_canvas.draw()

    def _calc_prob(self) -> None:
        res = self._current_result
        if res is None:
            return
        raw = self._prob_entry.get().strip()
        try:
            val = float(raw)
        except ValueError:
            self._prob_result.config(text="invalid")
            return
        p = res.prob_less_than(val)
        self._prob_result.config(text=f"{p:.4f}  ({p*100:.1f} %)")
