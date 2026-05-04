"""Dialog for defining a forecast cell."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from ..engine import ForecastDefinition


class ForecastDialog:
    """
    Minimal modal dialog: pick the sheet/cell to track and give it an
    optional display name.
    """

    def __init__(
        self,
        parent: tk.Misc,
        xl,
        engine,
        existing: Optional[ForecastDefinition] = None,
    ) -> None:
        self.xl = xl
        self.engine = engine
        self.result: Optional[ForecastDefinition] = None

        self.top = tk.Toplevel(parent)
        self.top.title("Define Forecast" if existing is None else "Edit Forecast")
        self.top.resizable(False, False)
        self.top.grab_set()

        if existing:
            init_sheet = existing.sheet_name
            init_cell  = existing.cell_address
            init_name  = existing.name
        else:
            sheet, cell = xl.selected_cell()
            init_sheet = sheet
            init_cell  = cell
            init_name  = ""

        self._build_ui(init_sheet, init_cell, init_name)
        self.top.wait_window()

    def _build_ui(self, init_sheet: str, init_cell: str, init_name: str) -> None:
        pad = {"padx": 8, "pady": 4}
        f = ttk.Frame(self.top, padding=14)
        f.grid(sticky="nsew")

        row = 0

        ttk.Label(f, text="Sheet:").grid(row=row, column=0, sticky="e", **pad)
        self._sheet_var = tk.StringVar(value=init_sheet)
        sheets = self.xl.sheet_names() or [init_sheet]
        ttk.Combobox(f, textvariable=self._sheet_var, values=sheets, width=22).grid(
            row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(f, text="Cell:").grid(row=row, column=0, sticky="e", **pad)
        self._cell_var = tk.StringVar(value=init_cell)
        ttk.Entry(f, textvariable=self._cell_var, width=12).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(f, text="Name (optional):").grid(row=row, column=0, sticky="e", **pad)
        self._name_var = tk.StringVar(value=init_name)
        ttk.Entry(f, textvariable=self._name_var, width=32).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # Hint about formula requirement
        hint = ttk.Label(f, text="Tip: forecast cells should contain formulas that\n"
                                   "depend (directly or indirectly) on assumption cells.",
                          foreground="gray", justify="left")
        hint.grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))
        row += 1

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=6)
        ttk.Button(btn_frame, text="OK",     width=10, command=self._ok).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", width=10, command=self.top.destroy).pack(side="left", padx=6)

    def _ok(self) -> None:
        cell  = self._cell_var.get().strip().upper()
        sheet = self._sheet_var.get().strip()
        name  = self._name_var.get().strip()

        if not cell or not sheet:
            messagebox.showerror("Validation", "Sheet and Cell are required.", parent=self.top)
            return

        fc = ForecastDefinition(cell_address=cell, sheet_name=sheet, name=name)
        self.engine.upsert_forecast(fc)
        self.result = fc
        self.top.destroy()
