"""Run-simulation dialog with configuration and live progress bar."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional

from ..engine import SimulationConfig, SimulationEngine, SimulationResults


class RunDialog:
    """
    Modal dialog that:
      - lets the user configure the simulation (iterations, seed, LHS toggle)
      - shows a progress bar while the simulation runs on a background thread
      - surfaces any exception back to the user
    """

    def __init__(self, parent: tk.Misc, engine: SimulationEngine) -> None:
        self.engine = engine
        self.results: Optional[List[SimulationResults]] = None
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[str] = None

        self.top = tk.Toplevel(parent)
        self.top.title("Run Simulation")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.top.wait_window()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        f = ttk.Frame(self.top, padding=14)
        f.grid(sticky="nsew")

        row = 0

        # Summary info
        n_asmp = len(self.engine.assumptions)
        n_fc   = len(self.engine.forecasts)
        info = ttk.Label(f, text=f"{n_asmp} assumption(s)   ·   {n_fc} forecast(s)",
                          foreground="gray")
        info.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        ttk.Separator(f).grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        row += 1

        # Iterations
        ttk.Label(f, text="Iterations:").grid(row=row, column=0, sticky="e", **pad)
        self._iter_var = tk.StringVar(value="1000")
        ttk.Entry(f, textvariable=self._iter_var, width=12).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # Random seed
        ttk.Label(f, text="Random seed (blank = random):").grid(row=row, column=0, sticky="e", **pad)
        self._seed_var = tk.StringVar(value="")
        ttk.Entry(f, textvariable=self._seed_var, width=12).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # Latin hypercube
        self._lhs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Use Latin Hypercube Sampling (better distribution coverage)",
                         variable=self._lhs_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        row += 1

        ttk.Separator(f).grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        row += 1

        # Progress
        self._progress_label = ttk.Label(f, text="Ready")
        self._progress_label.grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1

        self._progress_bar = ttk.Progressbar(f, length=360, mode="determinate")
        self._progress_bar.grid(row=row, column=0, columnspan=2, padx=10, pady=4)
        row += 1

        self._iter_label = ttk.Label(f, text="", foreground="gray")
        self._iter_label.grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1

        # Buttons
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=10)
        self._run_btn   = ttk.Button(btn_frame, text="▶  Run",  width=10, command=self._start_run)
        self._run_btn.pack(side="left", padx=6)
        self._stop_btn  = ttk.Button(btn_frame, text="■  Stop", width=10,
                                      command=self._stop, state="disabled")
        self._stop_btn.pack(side="left", padx=6)
        self._close_btn = ttk.Button(btn_frame, text="Close",   width=10, command=self.top.destroy)
        self._close_btn.pack(side="left", padx=6)

    # ------------------------------------------------------------------

    def _parse_config(self) -> Optional[SimulationConfig]:
        try:
            n = int(self._iter_var.get().strip())
            if n < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation", "Iterations must be a positive integer.",
                                  parent=self.top)
            return None

        seed_raw = self._seed_var.get().strip()
        seed: Optional[int] = None
        if seed_raw:
            try:
                seed = int(seed_raw)
            except ValueError:
                messagebox.showerror("Validation", "Seed must be an integer or blank.",
                                      parent=self.top)
                return None

        return SimulationConfig(
            iterations=n,
            seed=seed,
            use_latin_hypercube=self._lhs_var.get(),
        )

    def _start_run(self) -> None:
        config = self._parse_config()
        if config is None:
            return

        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._close_btn.config(state="disabled")
        self._progress_bar["value"] = 0
        self._progress_bar["maximum"] = config.iterations
        self._progress_label.config(text="Running…")
        self._error = None
        self.results = None

        self._thread = threading.Thread(
            target=self._worker, args=(config,), daemon=True)
        self._thread.start()
        self._poll()

    def _worker(self, config: SimulationConfig) -> None:
        try:
            self.results = self.engine.run(config, progress_cb=self._progress_cb)
        except Exception as exc:
            self._error = str(exc)

    def _progress_cb(self, completed: int, total: int) -> None:
        # Called from the worker thread — just store; _poll reads it
        self._cb_completed = completed
        self._cb_total = total

    def _poll(self) -> None:
        if self._thread and self._thread.is_alive():
            completed = getattr(self, "_cb_completed", 0)
            total     = getattr(self, "_cb_total", 1)
            self._progress_bar["value"] = completed
            pct = int(100 * completed / max(total, 1))
            self._iter_label.config(text=f"{completed:,} / {total:,}  ({pct} %)")
            self.top.after(150, self._poll)
        else:
            self._finish()

    def _finish(self) -> None:
        self._run_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._close_btn.config(state="normal")

        if self._error:
            self._progress_label.config(text="Error — see message", foreground="red")
            messagebox.showerror("Simulation Error", self._error, parent=self.top)
        elif self.results is not None:
            n_done = self.results[0].iterations_completed if self.results else 0
            elapsed = self.results[0].elapsed_seconds if self.results else 0.0
            self._progress_label.config(
                text=f"Done — {n_done:,} iterations in {elapsed:.1f}s",
                foreground="green")
            self._progress_bar["value"] = self._progress_bar["maximum"]
        else:
            self._progress_label.config(text="Stopped", foreground="orange")

    def _stop(self) -> None:
        self.engine.request_stop()
        self._stop_btn.config(state="disabled")
        self._progress_label.config(text="Stopping…")

    def _on_close(self) -> None:
        if self._thread and self._thread.is_alive():
            self.engine.request_stop()
        self.top.destroy()
