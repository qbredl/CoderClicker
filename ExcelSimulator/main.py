"""Entry point for the Excel Monte Carlo Simulator."""

import sys


def _check_deps() -> list[str]:
    missing = []
    for pkg, import_name in [
        ("xlwings",    "xlwings"),
        ("numpy",      "numpy"),
        ("scipy",      "scipy"),
        ("matplotlib", "matplotlib"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    return missing


def main() -> None:
    missing = _check_deps()
    if missing:
        print("Missing dependencies. Install them with:")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)

    from excel_simulator.ui.app import SimulatorApp
    app = SimulatorApp()
    app.run()


if __name__ == "__main__":
    main()
