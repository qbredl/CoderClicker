"""Main application window — Crystal Ball-style control panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Optional

from ..engine import SimulationEngine, SimulationResults
from ..excel_interface import ExcelInterface


class SimulatorApp:
    """
    Top-level window that mirrors Crystal Ball's workflow:
      Connect → Define Assumptions → Define Forecasts → Run → View Results
    """

    def __init__(self) -> None:
        self.xl     = ExcelInterface()
        self.engine = SimulationEngine(self.xl)
        self.results: List[SimulationResults] = []

        self.root = tk.Tk()
        self.root.title("Excel Monte Carlo Simulator")
        self.root.geometry("740x560")
        self.root.minsize(600, 400)

        self._setup_style()
        self._setup_menu()
        self._setup_ui()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        available = style.theme_names()
        for preferred in ("vista", "xpnative", "clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menu(self) -> None:
        menubar = tk.Menu(self.root)

        # File
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label="Connect to Active Excel Workbook",
                        command=self._connect_active)
        fm.add_command(label="Open Workbook…",
                        command=self._open_workbook)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=fm)

        # Define
        dm = tk.Menu(menubar, tearoff=0)
        dm.add_command(label="Define Assumption…",   command=self._define_assumption)
        dm.add_command(label="Define Forecast…",     command=self._define_forecast)
        dm.add_separator()
        dm.add_command(label="Clear All Definitions", command=self._clear_all)
        menubar.add_cascade(label="Define", menu=dm)

        # Run
        rm = tk.Menu(menubar, tearoff=0)
        rm.add_command(label="Run Simulation…", command=self._run_simulation)
        menubar.add_cascade(label="Run", menu=rm)

        # Results
        rsm = tk.Menu(menubar, tearoff=0)
        rsm.add_command(label="View Results",          command=self._view_results)
        rsm.add_command(label="Export to Excel Sheet", command=self._export_to_excel)
        menubar.add_cascade(label="Results", menu=rsm)

        # Help
        hm = tk.Menu(menubar, tearoff=0)
        hm.add_command(label="Quick Start", command=self._show_help)
        hm.add_command(label="About",       command=self._show_about)
        menubar.add_cascade(label="Help", menu=hm)

        self.root.config(menu=menubar)

    # ------------------------------------------------------------------
    # Main UI layout
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # ---- Connection bar ----
        conn = ttk.LabelFrame(self.root, text="Excel Connection", padding=6)
        conn.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        conn.columnconfigure(1, weight=1)

        self._status_dot  = ttk.Label(conn, text="●", foreground="red", font=("", 12))
        self._status_dot.grid(row=0, column=0, padx=(0, 4))
        self._status_lbl  = ttk.Label(conn, text="Not connected")
        self._status_lbl.grid(row=0, column=1, sticky="w")
        self._wb_lbl      = ttk.Label(conn, text="", foreground="gray")
        self._wb_lbl.grid(row=0, column=2, sticky="e", padx=8)
        ttk.Button(conn, text="Connect", command=self._connect_active).grid(
            row=0, column=3, padx=4)
        ttk.Button(conn, text="Open File…", command=self._open_workbook).grid(
            row=0, column=4)

        # ---- Toolbar ----
        toolbar = ttk.Frame(self.root)
        toolbar.grid(row=1, column=0, sticky="new", padx=8, pady=4)

        btn_defs = [
            ("＋ Assumption",  self._define_assumption),
            ("＋ Forecast",    self._define_forecast),
            ("|",              None),
            ("▶ Run",          self._run_simulation),
            ("|",              None),
            ("📊 Results",     self._view_results),
            ("📤 Export",      self._export_to_excel),
        ]
        for text, cmd in btn_defs:
            if text == "|":
                ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=4)
            else:
                ttk.Button(toolbar, text=text, command=cmd).pack(side="left", padx=2)

        # ---- Main body (assumptions + forecasts) ----
        body = ttk.Frame(self.root)
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.root.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)

        # Assumptions table
        asmp_frame = ttk.LabelFrame(body, text="Assumption Cells", padding=4)
        asmp_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        asmp_frame.columnconfigure(0, weight=1)
        asmp_frame.rowconfigure(0, weight=1)

        cols = ("cell", "sheet", "name", "distribution", "params")
        self._asmp_tree = ttk.Treeview(asmp_frame, columns=cols, show="headings", height=7)
        for col, heading, width in [
            ("cell",         "Cell",         70),
            ("sheet",        "Sheet",        110),
            ("name",         "Name",         130),
            ("distribution", "Distribution", 160),
            ("params",       "Parameters",   260),
        ]:
            self._asmp_tree.heading(col, text=heading)
            self._asmp_tree.column(col, width=width, minwidth=50)

        asmp_sb = ttk.Scrollbar(asmp_frame, orient="vertical",
                                  command=self._asmp_tree.yview)
        self._asmp_tree.configure(yscrollcommand=asmp_sb.set)
        self._asmp_tree.grid(row=0, column=0, sticky="nsew")
        asmp_sb.grid(row=0, column=1, sticky="ns")
        self._asmp_tree.bind("<Double-Button-1>", lambda _: self._edit_assumption())

        asmp_btns = ttk.Frame(asmp_frame)
        asmp_btns.grid(row=1, column=0, sticky="w", pady=2)
        ttk.Button(asmp_btns, text="Add",    command=self._define_assumption).pack(side="left", padx=2)
        ttk.Button(asmp_btns, text="Edit",   command=self._edit_assumption).pack(side="left", padx=2)
        ttk.Button(asmp_btns, text="Remove", command=self._remove_assumption).pack(side="left", padx=2)

        # Forecasts table
        fc_frame = ttk.LabelFrame(body, text="Forecast Cells", padding=4)
        fc_frame.grid(row=1, column=0, sticky="nsew")
        fc_frame.columnconfigure(0, weight=1)
        fc_frame.rowconfigure(0, weight=1)

        fc_cols = ("cell", "sheet", "name")
        self._fc_tree = ttk.Treeview(fc_frame, columns=fc_cols, show="headings", height=4)
        for col, heading, width in [
            ("cell",  "Cell",  80),
            ("sheet", "Sheet", 130),
            ("name",  "Name",  400),
        ]:
            self._fc_tree.heading(col, text=heading)
            self._fc_tree.column(col, width=width, minwidth=50)

        fc_sb = ttk.Scrollbar(fc_frame, orient="vertical", command=self._fc_tree.yview)
        self._fc_tree.configure(yscrollcommand=fc_sb.set)
        self._fc_tree.grid(row=0, column=0, sticky="nsew")
        fc_sb.grid(row=0, column=1, sticky="ns")

        fc_btns = ttk.Frame(fc_frame)
        fc_btns.grid(row=1, column=0, sticky="w", pady=2)
        ttk.Button(fc_btns, text="Add",    command=self._define_forecast).pack(side="left", padx=2)
        ttk.Button(fc_btns, text="Remove", command=self._remove_forecast).pack(side="left", padx=2)

        # ---- Status bar ----
        self._statusbar = ttk.Label(self.root, text="Ready", anchor="w",
                                     relief="sunken", padding=(4, 1))
        self._statusbar.grid(row=3, column=0, sticky="ew")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect_active(self) -> None:
        ok, err = self.xl.connect_to_active()
        if ok:
            self._on_connected()
        else:
            messagebox.showerror("Connection Failed",
                                  f"Could not connect to Excel.\n\n{err}\n\n"
                                  "Make sure Excel is running with at least one open workbook.")

    def _open_workbook(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Excel Workbook",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xlsb *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        ok, err = self.xl.open_workbook(path)
        if ok:
            self._on_connected()
        else:
            messagebox.showerror("Error", f"Could not open workbook:\n{err}")

    def _on_connected(self) -> None:
        name = self.xl.workbook_name()
        self._status_dot.config(foreground="green")
        self._status_lbl.config(text="Connected")
        self._wb_lbl.config(text=name)
        self._set_status(f"Connected to '{name}'")

    # ------------------------------------------------------------------
    # Assumptions
    # ------------------------------------------------------------------

    def _define_assumption(self) -> None:
        if not self._check_connected():
            return
        from .assumption_dialog import AssumptionDialog
        AssumptionDialog(self.root, self.xl, self.engine)
        self._refresh_assumptions()

    def _edit_assumption(self) -> None:
        if not self._check_connected():
            return
        sel = self._asmp_tree.selection()
        if not sel:
            messagebox.showinfo("Select Row", "Please select an assumption to edit.", parent=self.root)
            return
        vals = self._asmp_tree.item(sel[0])["values"]
        cell, sheet = str(vals[0]), str(vals[1])
        existing = next(
            (a for a in self.engine.assumptions
             if a.cell_address == cell and a.sheet_name == sheet), None)
        if existing:
            from .assumption_dialog import AssumptionDialog
            AssumptionDialog(self.root, self.xl, self.engine, existing=existing)
            self._refresh_assumptions()

    def _remove_assumption(self) -> None:
        sel = self._asmp_tree.selection()
        if not sel:
            return
        vals = self._asmp_tree.item(sel[0])["values"]
        cell, sheet = str(vals[0]), str(vals[1])
        self.engine.remove_assumption(sheet, cell)
        self._refresh_assumptions()

    def _refresh_assumptions(self) -> None:
        self._asmp_tree.delete(*self._asmp_tree.get_children())
        for a in self.engine.assumptions:
            self._asmp_tree.insert("", "end", values=(
                a.cell_address, a.sheet_name, a.name,
                a.distribution.value, a.params_summary(),
            ))

    # ------------------------------------------------------------------
    # Forecasts
    # ------------------------------------------------------------------

    def _define_forecast(self) -> None:
        if not self._check_connected():
            return
        from .forecast_dialog import ForecastDialog
        ForecastDialog(self.root, self.xl, self.engine)
        self._refresh_forecasts()

    def _remove_forecast(self) -> None:
        sel = self._fc_tree.selection()
        if not sel:
            return
        vals = self._fc_tree.item(sel[0])["values"]
        cell, sheet = str(vals[0]), str(vals[1])
        self.engine.remove_forecast(sheet, cell)
        self._refresh_forecasts()

    def _refresh_forecasts(self) -> None:
        self._fc_tree.delete(*self._fc_tree.get_children())
        for fc in self.engine.forecasts:
            self._fc_tree.insert("", "end", values=(
                fc.cell_address, fc.sheet_name, fc.name))

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run_simulation(self) -> None:
        if not self._check_connected():
            return
        if not self.engine.assumptions:
            messagebox.showwarning("No Assumptions",
                                    "Define at least one assumption cell before running.")
            return
        if not self.engine.forecasts:
            messagebox.showwarning("No Forecasts",
                                    "Define at least one forecast cell before running.")
            return
        from .run_dialog import RunDialog
        dlg = RunDialog(self.root, self.engine)
        if dlg.results:
            self.results = dlg.results
            n = self.results[0].iterations_completed if self.results else 0
            self._set_status(
                f"Simulation complete — {n:,} iterations, "
                f"{len(self.results)} forecast(s).")

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def _view_results(self) -> None:
        if not self.results:
            messagebox.showinfo("No Results", "Run a simulation first.", parent=self.root)
            return
        from .results_window import ResultsWindow
        ResultsWindow(self.root, self.results, self.engine.assumptions)

    def _export_to_excel(self) -> None:
        if not self.results:
            messagebox.showinfo("No Results", "Run a simulation first.", parent=self.root)
            return
        if not self.xl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to Excel first.", parent=self.root)
            return
        self.xl.write_results_sheet(self.results)
        messagebox.showinfo("Exported",
                             "Results written to the 'CB Results' sheet in the workbook.")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _clear_all(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear all assumptions and forecasts?",
                                    parent=self.root):
            return
        self.engine.clear_all()
        self._refresh_assumptions()
        self._refresh_forecasts()
        self._set_status("All definitions cleared.")

    def _check_connected(self) -> bool:
        if not self.xl.is_connected:
            messagebox.showwarning("Not Connected",
                                    "Connect to an Excel workbook first (File → Connect).",
                                    parent=self.root)
            return False
        return True

    def _set_status(self, msg: str) -> None:
        self._statusbar.config(text=msg)

    def _show_help(self) -> None:
        help_text = (
            "Quick Start\n"
            "───────────\n"
            "1. Open your Excel model, then click  File → Connect to Active Excel Workbook.\n\n"
            "2. Click  Define Assumption  and select a cell that should vary randomly.\n"
            "   Choose a distribution (e.g. Normal) and enter its parameters.\n\n"
            "3. Click  Define Forecast  and select an output cell (one with a formula).\n\n"
            "4. Click  Run → Run Simulation, set the number of iterations, and click ▶ Run.\n\n"
            "5. Click  Results → View Results  to see statistics and charts.\n\n"
            "Tips\n"
            "────\n"
            "• Cyan cells = Assumptions   Green cells = Forecasts\n"
            "• Latin Hypercube Sampling gives better distribution coverage in fewer trials.\n"
            "• Set a seed for reproducible results.\n"
            "• Use File → Export to write summary stats back into Excel.\n"
        )
        win = tk.Toplevel(self.root)
        win.title("Quick Start")
        win.resizable(False, False)
        txt = tk.Text(win, wrap="word", width=64, height=28, padx=12, pady=10,
                       font=("Courier", 10))
        txt.insert("1.0", help_text)
        txt.config(state="disabled")
        txt.pack(padx=6, pady=6)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Excel Monte Carlo Simulator\n"
            "Version 1.0\n\n"
            "A Crystal Ball-compatible simulation tool.\n"
            "Powered by xlwings · NumPy · SciPy · Matplotlib",
            parent=self.root,
        )

    def run(self) -> None:
        self.root.mainloop()
