"""Native Scene Desktop Studio GUI application."""
from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication

from .studio_window import StudioWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Scene Desktop Studio")
    app.setOrganizationName("Rajudesktop")
    app.setStyle("Fusion")
    window = StudioWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
