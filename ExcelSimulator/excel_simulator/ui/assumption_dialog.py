"""Dialog for defining an assumption cell with a probability distribution."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional

from ..distributions import (
    DISTRIBUTION_REGISTRY,
    AssumptionDefinition,
    DistributionType,
    ParamSpec,
)


class AssumptionDialog:
    """
    Modal dialog that lets the user:
      1. Choose / confirm the cell address (pre-filled from the current selection)
      2. Pick a distribution type
      3. Fill in distribution parameters
      4. Optionally set truncation bounds

    On OK the engine's upsert_assumption() is called.
    """

    def __init__(
        self,
        parent: tk.Misc,
        xl,
        engine,
        existing: Optional[AssumptionDefinition] = None,
    ) -> None:
        self.xl = xl
        self.engine = engine
        self.result: Optional[AssumptionDefinition] = None

        self.top = tk.Toplevel(parent)
        self.top.title("Define Assumption" if existing is None else "Edit Assumption")
        self.top.resizable(False, False)
        self.top.grab_set()

        self._param_vars: Dict[str, tk.StringVar] = {}
        self._param_entries: Dict[str, ttk.Entry] = {}

        # Pre-fill values from existing definition or Excel selection
        if existing:
            self._init_sheet = existing.sheet_name
            self._init_cell  = existing.cell_address
            self._init_name  = existing.name
            self._init_dist  = existing.distribution
            self._init_params = existing.params.copy()
            self._init_trunc_lo = "" if existing.truncate_lower is None else str(existing.truncate_lower)
            self._init_trunc_hi = "" if existing.truncate_upper is None else str(existing.truncate_upper)
        else:
            sheet, cell = xl.selected_cell()
            self._init_sheet = sheet
            self._init_cell  = cell
            self._init_name  = ""
            self._init_dist  = DistributionType.NORMAL
            self._init_params = {}
            self._init_trunc_lo = ""
            self._init_trunc_hi = ""

        self._build_ui()
        self.top.wait_window()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        f = ttk.Frame(self.top, padding=10)
        f.grid(sticky="nsew")

        row = 0

        # ---- Cell location ----
        ttk.Label(f, text="Sheet:").grid(row=row, column=0, sticky="e", **pad)
        self._sheet_var = tk.StringVar(value=self._init_sheet)
        sheets = self.xl.sheet_names() or [self._init_sheet]
        cb_sheet = ttk.Combobox(f, textvariable=self._sheet_var, values=sheets, width=20)
        cb_sheet.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(f, text="Cell:").grid(row=row, column=0, sticky="e", **pad)
        self._cell_var = tk.StringVar(value=self._init_cell)
        ttk.Entry(f, textvariable=self._cell_var, width=10).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(f, text="Name (optional):").grid(row=row, column=0, sticky="e", **pad)
        self._name_var = tk.StringVar(value=self._init_name)
        ttk.Entry(f, textvariable=self._name_var, width=30).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Separator(f, orient="horizontal").grid(row=row, column=0, columnspan=3,
                                                    sticky="ew", pady=6)
        row += 1

        # ---- Distribution selector ----
        ttk.Label(f, text="Distribution:").grid(row=row, column=0, sticky="e", **pad)
        self._dist_var = tk.StringVar(value=self._init_dist.value)
        dist_names = [d.value for d in DistributionType]
        cb_dist = ttk.Combobox(f, textvariable=self._dist_var, values=dist_names,
                                state="readonly", width=28)
        cb_dist.grid(row=row, column=1, sticky="w", **pad)
        cb_dist.bind("<<ComboboxSelected>>", lambda _: self._refresh_params())
        row += 1

        # ---- Parameter frame (rebuilt dynamically) ----
        self._params_frame = ttk.LabelFrame(f, text="Parameters", padding=6)
        self._params_frame.grid(row=row, column=0, columnspan=2, sticky="ew",
                                 padx=8, pady=4)
        self._params_row = row
        row += 1

        ttk.Separator(f, orient="horizontal").grid(row=row, column=0, columnspan=3,
                                                    sticky="ew", pady=6)
        row += 1

        # ---- Truncation ----
        trunc_frame = ttk.LabelFrame(f, text="Truncation (optional)", padding=6)
        trunc_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        row += 1

        ttk.Label(trunc_frame, text="Lower bound:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        self._trunc_lo = tk.StringVar(value=self._init_trunc_lo)
        ttk.Entry(trunc_frame, textvariable=self._trunc_lo, width=14).grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(trunc_frame, text="Upper bound:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self._trunc_hi = tk.StringVar(value=self._init_trunc_hi)
        ttk.Entry(trunc_frame, textvariable=self._trunc_hi, width=14).grid(row=1, column=1, sticky="w", padx=4)

        # ---- Buttons ----
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text="OK", width=10, command=self._ok).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", width=10, command=self.top.destroy).pack(side="left", padx=6)

        self._refresh_params()

    def _refresh_params(self) -> None:
        """Rebuild the parameter widgets for the selected distribution."""
        for w in self._params_frame.winfo_children():
            w.destroy()
        self._param_vars.clear()
        self._param_entries.clear()

        dist_type = self._current_dist_type()
        cls = DISTRIBUTION_REGISTRY[dist_type]

        for r, spec in enumerate(cls.PARAMS):
            ttk.Label(self._params_frame, text=f"{spec.label}:").grid(
                row=r, column=0, sticky="e", padx=4, pady=2)

            # Use existing param value if available, else default
            default = self._init_params.get(spec.key, spec.default)
            var = tk.StringVar(value=f"{default:g}")
            self._param_vars[spec.key] = var

            entry = ttk.Entry(self._params_frame, textvariable=var, width=16)
            entry.grid(row=r, column=1, sticky="w", padx=4, pady=2)
            self._param_entries[spec.key] = entry

    def _current_dist_type(self) -> DistributionType:
        val = self._dist_var.get()
        for dt in DistributionType:
            if dt.value == val:
                return dt
        return DistributionType.NORMAL

    def _ok(self) -> None:
        cell    = self._cell_var.get().strip().upper()
        sheet   = self._sheet_var.get().strip()
        name    = self._name_var.get().strip()
        dist    = self._current_dist_type()
        cls     = DISTRIBUTION_REGISTRY[dist]

        if not cell or not sheet:
            messagebox.showerror("Validation", "Sheet and Cell are required.", parent=self.top)
            return

        # Parse parameters
        params: Dict[str, float] = {}
        for spec in cls.PARAMS:
            raw = self._param_vars[spec.key].get().strip()
            try:
                val = float(raw)
                if spec.is_int:
                    val = float(int(val))
                params[spec.key] = val
            except ValueError:
                messagebox.showerror("Validation",
                                     f"Invalid value for '{spec.label}': {raw!r}",
                                     parent=self.top)
                return

        error = cls.validate(params)
        if error:
            messagebox.showerror("Validation", error, parent=self.top)
            return

        # Truncation
        trunc_lo: Optional[float] = None
        trunc_hi: Optional[float] = None
        lo_raw = self._trunc_lo.get().strip()
        hi_raw = self._trunc_hi.get().strip()
        try:
            if lo_raw:
                trunc_lo = float(lo_raw)
            if hi_raw:
                trunc_hi = float(hi_raw)
        except ValueError:
            messagebox.showerror("Validation", "Truncation bounds must be numbers.", parent=self.top)
            return
        if trunc_lo is not None and trunc_hi is not None and trunc_lo >= trunc_hi:
            messagebox.showerror("Validation", "Lower truncation must be < upper truncation.", parent=self.top)
            return

        assumption = AssumptionDefinition(
            cell_address=cell,
            sheet_name=sheet,
            distribution=dist,
            params=params,
            name=name,
            truncate_lower=trunc_lo,
            truncate_upper=trunc_hi,
        )
        self.engine.upsert_assumption(assumption)
        self.result = assumption
        self.top.destroy()
