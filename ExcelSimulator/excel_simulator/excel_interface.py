"""Excel COM abstraction via xlwings.

All interaction with a live Excel process is routed through this class so the
simulation engine remains testable without Excel present.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

try:
    import xlwings as xw
    _HAS_XW = True
except ImportError:
    _HAS_XW = False


class ExcelNotAvailableError(RuntimeError):
    """Raised when xlwings is not installed or Excel cannot be reached."""


class ExcelInterface:
    """
    Thin wrapper around xlwings that exposes only what the engine needs.

    All colour arguments are (R, G, B) tuples with values in 0–255.
    Cell addresses use standard Excel notation without dollar signs, e.g. "B5".
    """

    def __init__(self) -> None:
        self._app: Optional[Any] = None   # xw.App
        self._wb:  Optional[Any] = None   # xw.Book

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        if not _HAS_XW or self._wb is None:
            return False
        try:
            _ = self._wb.name   # will raise if the workbook was closed
            return True
        except Exception:
            self._wb = None
            return False

    def connect_to_active(self) -> Tuple[bool, str]:
        """
        Attach to whichever workbook is currently active in Excel.
        Returns (success, error_message).
        """
        if not _HAS_XW:
            return False, "xlwings is not installed. Run: pip install xlwings"
        try:
            self._wb = xw.books.active
            self._app = self._wb.app
            self._app.screen_updating = True
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def open_workbook(self, path: str) -> Tuple[bool, str]:
        """Open *path* in a new (or reused) Excel instance."""
        if not _HAS_XW:
            return False, "xlwings is not installed. Run: pip install xlwings"
        try:
            if self._app is None:
                self._app = xw.App(visible=True)
            self._wb = self._app.books.open(path)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def disconnect(self) -> None:
        self._wb = None
        self._app = None

    # ------------------------------------------------------------------
    # Workbook / sheet info
    # ------------------------------------------------------------------

    def workbook_name(self) -> str:
        return self._wb.name if self.is_connected else ""

    def workbook_path(self) -> str:
        try:
            return str(self._wb.fullname) if self.is_connected else ""
        except Exception:
            return ""

    def sheet_names(self) -> List[str]:
        if not self.is_connected:
            return []
        return [s.name for s in self._wb.sheets]

    def active_sheet_name(self) -> str:
        if not self.is_connected:
            return ""
        return self._wb.sheets.active.name

    def selected_cell(self) -> Tuple[str, str]:
        """Return (sheet_name, cell_address) of the current selection, best-effort."""
        if not self.is_connected:
            return "", ""
        try:
            sel = self._app.selection
            addr = sel.address.replace("$", "").split(":")[0]   # top-left of multi-select
            return sel.sheet.name, addr
        except Exception:
            return self.active_sheet_name(), "A1"

    # ------------------------------------------------------------------
    # Cell read / write
    # ------------------------------------------------------------------

    def get_cell_value(self, sheet_name: str, cell_address: str) -> Any:
        if not self.is_connected:
            return None
        return self._wb.sheets[sheet_name].range(cell_address).value

    def set_cell_value(self, sheet_name: str, cell_address: str, value: Any) -> None:
        if not self.is_connected:
            return
        self._wb.sheets[sheet_name].range(cell_address).value = value

    def get_cell_formula(self, sheet_name: str, cell_address: str) -> str:
        if not self.is_connected:
            return ""
        return self._wb.sheets[sheet_name].range(cell_address).formula or ""

    def has_formula(self, sheet_name: str, cell_address: str) -> bool:
        formula = self.get_cell_formula(sheet_name, cell_address)
        return formula.startswith("=")

    # ------------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------------

    def calculate(self) -> None:
        if self.is_connected:
            self._app.calculate()

    # ------------------------------------------------------------------
    # Cell colours (Crystal Ball uses cyan/green to mark cells)
    # ------------------------------------------------------------------

    def set_cell_color(self, sheet_name: str, cell_address: str,
                       rgb: Tuple[int, int, int]) -> None:
        if not self.is_connected:
            return
        self._wb.sheets[sheet_name].range(cell_address).color = rgb

    def clear_cell_color(self, sheet_name: str, cell_address: str) -> None:
        if not self.is_connected:
            return
        self._wb.sheets[sheet_name].range(cell_address).color = None

    # ------------------------------------------------------------------
    # Results export
    # ------------------------------------------------------------------

    def write_results_sheet(self, results: list,
                             sheet_name: str = "CB Results") -> None:
        """
        Write summary statistics for all SimulationResults objects to a
        dedicated sheet in the workbook.
        """
        if not self.is_connected:
            return

        # Remove old sheet if it exists
        for sht in list(self._wb.sheets):
            if sht.name == sheet_name:
                sht.delete()
                break

        rs = self._wb.sheets.add(sheet_name, after=self._wb.sheets[-1])

        row = 1
        for res in results:
            # Forecast header
            rs.range(f"A{row}").value = f"Forecast: {res.forecast_name}"
            rs.range(f"A{row}").font.bold = True
            rs.range(f"A{row}").font.size = 12
            row += 1

            rs.range(f"A{row}").value = f"Cell: {res.cell_key}"
            rs.range(f"A{row}").font.color = (128, 128, 128)
            row += 1

            rs.range(f"A{row}").value  = "Iterations completed"
            rs.range(f"B{row}").value  = res.iterations_completed
            row += 1
            rs.range(f"A{row}").value  = "Elapsed (s)"
            rs.range(f"B{row}").value  = round(res.elapsed_seconds, 2)
            row += 1

            # Stats table header
            rs.range(f"A{row}").value = "Statistic"
            rs.range(f"B{row}").value = "Value"
            rs.range(f"A{row}").font.bold = True
            rs.range(f"B{row}").font.bold = True
            row += 1

            for stat_name, stat_val in res.summary().items():
                rs.range(f"A{row}").value = stat_name
                rs.range(f"B{row}").value = round(stat_val, 6)
                row += 1

            # Raw data header (optional — write first 500 values)
            row += 1
            rs.range(f"A{row}").value = "Sample Values (first 500)"
            rs.range(f"A{row}").font.bold = True
            row += 1
            vals = res.values[:500].tolist()
            rs.range(f"A{row}").value = [[v] for v in vals]
            row += len(vals) + 2   # gap before next forecast

        rs.autofit()
        self._wb.sheets.active = rs
