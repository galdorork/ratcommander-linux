"""List the mouse backups and load one into the editor."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from .backups import Backup, list_backups
from .kde_widgets import heading, icon, secondary
from .profiles import button_title


def summary(b: Backup) -> str:
    thumbs = ", ".join(f"{n}: {b.layout.binding(n).short_label()}" for n in range(1, 13))
    s = b.layout.settings
    extra = f" · CPI {', '.join(map(str, s.cpi_presets))}" if s.cpi_presets else ""
    return thumbs + extra


class BackupsDialog(QDialog):
    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mouse backups")
        self.resize(640, 420)
        self.folder = folder
        self.chosen: Backup | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(heading("Backups", 1))
        lay.addWidget(secondary("A backup of everything the app could read from the mouse is "
                                "taken right before each write. Load one into the editor, check "
                                "it, then use Apply Full Profile to put it back. Set zone colours again by hand, "
                                "as the mouse cannot report them for backup."))
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.backups = list_backups(folder) if folder.exists() else []
        for b in self.backups:
            item = QListWidgetItem(icon("document-revert"), b.title)
            item.setToolTip(summary(b))
            item.setData(Qt.UserRole, b)
            self.list.addItem(item)
        if not self.backups:
            self.list.addItem("No backups yet. One is made before the first write.")
            self.list.setEnabled(False)
        else:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self._load())
        lay.addWidget(self.list, 1)
        self.detail = secondary()
        lay.addWidget(self.detail)
        self.list.currentItemChanged.connect(self._show)
        self._show(self.list.currentItem())

        row = QHBoxLayout()
        folder_btn = QPushButton(icon("folder-open"), "Open Folder")
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.folder))))
        folder_btn.setEnabled(folder.exists())
        row.addWidget(folder_btn)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.load_btn = buttons.addButton("Load into Editor", QDialogButtonBox.AcceptRole)
        self.load_btn.setIcon(icon("document-import"))
        self.load_btn.setEnabled(bool(self.backups))
        buttons.accepted.connect(self._load)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        lay.addLayout(row)

    def _show(self, item) -> None:
        b = item.data(Qt.UserRole) if item is not None else None
        self.detail.setText(summary(b) if b else "")

    def _load(self) -> None:
        item = self.list.currentItem()
        b = item.data(Qt.UserRole) if item is not None else None
        if b is not None:
            self.chosen = b
            self.accept()
