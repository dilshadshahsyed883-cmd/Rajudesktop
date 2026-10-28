"""Fourth main tab: CapCut Controls with independent Transitions and Animations panels.

Both sub-tabs edit native CapCut drafts only after explicit user confirmation.
No invocation of Z Builder Scene Plan or timeline-export logic.
"""
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .transitions_tab import CapcutTransitionsTab
from .animations_tab import CapcutAnimationsTab


class CapcutControlsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        self.sections = QTabWidget(self)
        layout.addWidget(self.sections)
        self.transitions_tab = CapcutTransitionsTab(self)
        self.animations_tab = CapcutAnimationsTab(self)
        self.sections.addTab(self.transitions_tab, "Transitions")
        self.sections.addTab(self.animations_tab, "Animations")
