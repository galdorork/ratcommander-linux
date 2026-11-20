"""Main window. Presentation only: all state lives in the controller."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QStackedWidget, QStyle, QSystemTrayIcon, QTabBar, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)

from .backend import ApplyStatus, Transport
from .controller import (FULL_TABLE_WARNING, ApplyRequest, Controller, DeviceState)
from .profiles import (DEVICE_PROFILE_ID, Binding, ProfileError, accessible_name, button_position,
                       button_title, factory_binding)
from .kde_widgets import (Card, Chip, InlineMessage, MessageType, card_layout, heading, icon,
                          secondary, tool_button)
from .backups_dialog import BackupsDialog
from .settings_pages import CpiPage, LightingPage
from .virtual_keyboard import VirtualKeyboardDialog
from .side_view import (MouseSideView, MouseTopView, build_binding_menu, factory_label,
                        short_text)

APP_NAME = "RatCommander"


def desktop_layout(requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    for name in os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":"):
        if name.strip() in ("kde", "gnome"):
            return name.strip()
    return "kde"


class UiDispatcher(QObject):
    """Delivers callables from the worker thread to the UI thread."""

    _call = Signal(object)

    def __init__(self):
        super().__init__()
        self._call.connect(lambda fn: fn(), Qt.QueuedConnection)

    def __call__(self, fn) -> None:
        self._call.emit(fn)


class MainWindow(QMainWindow):
    def __init__(self, controller: Controller, demo: bool, layout: str = "auto"):
        super().__init__()
        self.c = controller
        self.demo = demo
        gnome = desktop_layout(layout) == "gnome"
        self._updating = False
        self.setWindowTitle(f"{APP_NAME} (demo mode)" if demo else APP_NAME)

        self.setWindowIcon(icon("input-mouse", QStyle.SP_ComputerIcon, self))

        # -- toolbar: device and profile actions, like a KDE app header
        bar = QToolBar("Main")
        bar.setObjectName("mainToolBar")
        bar.setMovable(False)
        bar.setIconSize(QSize(22, 22))
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(bar)

        mouse_icon = QLabel()
        mouse_icon.setPixmap(icon("input-mouse").pixmap(QSize(22, 22)))
        mouse_icon.setContentsMargins(4, 0, 4, 0)
        bar.addWidget(mouse_icon)
        self.device_combo = QComboBox()
        self.device_combo.setAccessibleName("Target device")
        self.device_combo.setMinimumWidth(230)
        self.device_combo.currentIndexChanged.connect(self._device_chosen)
        bar.addWidget(self.device_combo)
        self.refresh_btn = tool_button("&Refresh", "view-refresh", QStyle.SP_BrowserReload)
        self.refresh_btn.setToolTip("Find the mouse again and re-read its buttons")
        self.refresh_btn.clicked.connect(self.c.refresh_devices)
        bar.addWidget(self.refresh_btn)
        bar.addSeparator()

        prof_icon = QLabel()
        prof_icon.setPixmap(icon("bookmarks").pixmap(QSize(22, 22)))
        prof_icon.setContentsMargins(4, 0, 4, 0)
        bar.addWidget(prof_icon)
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName("Profile")
        self.profile_combo.setMinimumWidth(230)
        self.profile_combo.activated.connect(self._profile_chosen)
        bar.addWidget(self.profile_combo)
        self.undo_btn = tool_button("Undo", "edit-undo", QStyle.SP_ArrowBack)
        self.undo_btn.setShortcut(QKeySequence.Undo)
        self.undo_btn.setToolTip("Undo the last change (Ctrl+Z)")
        self.undo_btn.clicked.connect(lambda: self._guard(self.c.undo))
        bar.addWidget(self.undo_btn)
        self.redo_btn = tool_button("Redo", "edit-redo", QStyle.SP_ArrowForward)
        self.redo_btn.setShortcut(QKeySequence.Redo)
        self.redo_btn.setToolTip("Redo (Ctrl+Shift+Z)")
        self.redo_btn.clicked.connect(lambda: self._guard(self.c.redo))
        bar.addWidget(self.redo_btn)
        bar.addSeparator()
        self.save_btn = tool_button("&Save", "document-save", QStyle.SP_DialogSaveButton)
        self.save_btn.clicked.connect(self._save)
        bar.addWidget(self.save_btn)
        self.save_as_btn = tool_button("Save &As…", "document-save-as", QStyle.SP_DialogSaveButton)
        self.save_as_btn.clicked.connect(self._save_as)
        bar.addWidget(self.save_as_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)
        more = QMenu(self)
        self.rename_action = more.addAction(icon("edit-rename"), "Re&name Profile…", self._rename)
        self.duplicate_action = more.addAction(icon("edit-copy"), "D&uplicate Profile…",
                                               self._duplicate)
        more.addSeparator()
        self.delete_action = more.addAction(icon("edit-delete"), "&Delete Profile", self._delete)
        more.addSeparator()
        self.backups_action = more.addAction(icon("document-revert"), "&Backups…",
                                             self._backups)
        more.addSeparator()
        quit_action = more.addAction(icon("application-exit"), "&Quit RatCommander",
                                     QApplication.quit)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.addAction(quit_action)

        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(self.windowTitle())
        tray_menu = QMenu(self)
        tray_menu.addAction("Open RatCommander", self._show_from_tray)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.more_btn = tool_button("", "application-menu", QStyle.SP_TitleBarMenuButton)
        self.more_btn.setToolTip("Application menu")
        self.more_btn.setAccessibleName("Application menu")
        self.more_btn.setMenu(more)
        self.more_btn.setPopupMode(QToolButton.InstantPopup)
        self.more_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        bar.addWidget(self.more_btn)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(10)
        self.setCentralWidget(root)

        # -- inline messages
        self.demo_banner = InlineMessage(
            "Demo mode: a simulated mouse is used. Nothing is written to hardware.",
            MessageType.INFORMATION)
        self.demo_banner.setVisible(demo)
        outer.addWidget(self.demo_banner)
        self.notice = InlineMessage("", MessageType.INFORMATION)
        outer.addWidget(self.notice)

        # -- tabs: two views of the buttons, then CPI and lighting
        self.view_tabs = QTabBar()
        self.view_tabs.setDocumentMode(True)
        self.view_tabs.setDrawBase(False)
        self.view_tabs.setExpanding(False)
        for name, icon_name, tip in (
                ("Side", "view-left-new", "The 12 thumb buttons (Ctrl+1)"),
                ("Top", "go-top", "Main buttons, wheel and CPI button (Ctrl+2)"),
                ("CPI", "speedometer", "CPI presets and polling rate (Ctrl+3)"),
                ("Lighting", "color-management", "Zone colours and effects (Ctrl+4)")):
            i = self.view_tabs.addTab(icon(icon_name), name)
            self.view_tabs.setTabToolTip(i, tip)
        self.view_tabs.setAccessibleName("Sections")
        if gnome:
            for button in (self.refresh_btn, self.undo_btn, self.redo_btn):
                button.setToolButtonStyle(Qt.ToolButtonIconOnly)
                button.setAccessibleName(button.text().replace("&", ""))
            outer.setContentsMargins(18, 12, 18, 14)
            self.view_tabs.setStyleSheet("""
                QTabBar::tab {
                    background: palette(button);
                    color: palette(button-text);
                    border-radius: 9px;
                    padding: 6px 14px;
                    margin: 2px;
                }
                QTabBar::tab:selected {
                    background: palette(highlight);
                    color: palette(highlighted-text);
                }
                QTabBar::tab:focus { border: 1px solid palette(window-text); }
            """)
            outer.addWidget(self.view_tabs, alignment=Qt.AlignHCenter)
        else:
            outer.addWidget(self.view_tabs)
        self.page_stack = QStackedWidget()
        outer.addWidget(self.page_stack, 1)

        # -- editor: side view card + per-button card
        editor_page = QWidget()
        editor = QHBoxLayout(editor_page)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(12)
        view_card = Card()
        view_lay = card_layout(view_card)
        view_head = QHBoxLayout()
        self.view_title = heading("Thumb buttons", 2)
        view_head.addWidget(self.view_title)
        view_head.addStretch(1)
        self.device_chip = Chip()
        view_head.addWidget(self.device_chip)
        view_lay.addLayout(view_head)
        self.device_status = secondary()
        view_lay.addWidget(self.device_status)
        self.side_view = MouseSideView()
        self.top_view = MouseTopView()
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.side_view)
        self.view_stack.addWidget(self.top_view)
        self.view_tabs.currentChanged.connect(self._tab_changed)
        for i in range(4):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda i=i: self.view_tabs.setCurrentIndex(i))
        view_lay.addWidget(self.view_stack, 1)
        view_lay.addWidget(secondary("Click a button to see its mapping. Right-click it, or "
                                     "press the Menu key, for quick options."))
        self.thumb_buttons = self.side_view.keys
        self.top_buttons = self.top_view.keys
        self.all_buttons = {**self.thumb_buttons, **self.top_buttons}
        for label, key in self.all_buttons.items():
            key.clicked.connect(lambda _=False, n=label: self.c.select_button(n))
            key.menuRequested.connect(self._popup_menu)
        editor.addWidget(view_card, 1)

        bind_card = Card()
        bind_card.setFixedWidth(340)
        bind = card_layout(bind_card, 16)
        self.panel_title = heading("Button", 1)
        bind.addWidget(self.panel_title)
        self.selected_label = secondary()
        bind.addWidget(self.selected_label)
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.clicked.connect(
            lambda checked: self._guard(lambda: self.c.set_selected_enabled(checked)))
        bind.addWidget(self.enabled_check)
        bind.addSpacing(6)
        self.current_mapping = heading("", 1)
        big = self.current_mapping.font()
        big.setPointSizeF(big.pointSizeF() * 1.25)
        self.current_mapping.setFont(big)
        self.current_mapping.setAccessibleName("Mapping in the editor")
        bind.addWidget(self.current_mapping)
        self.changed_note = secondary()
        bind.addWidget(self.changed_note)
        bind.addSpacing(4)

        facts = QFormLayout()
        facts.setLabelAlignment(Qt.AlignRight)
        facts.setHorizontalSpacing(10)
        self.factory_value = QLabel()
        self.on_mouse_value = QLabel()
        self.written_value = QLabel()
        self.written_value.setWordWrap(True)
        facts.addRow(secondary("Factory default:"), self.factory_value)
        facts.addRow(secondary("On the mouse:"), self.on_mouse_value)
        facts.addRow(secondary("Last full write:"), self.written_value)
        bind.addLayout(facts)
        bind.addSpacing(8)

        self.change_btn = QPushButton(icon("document-edit"), "&Change Mapping…")
        self.change_btn.clicked.connect(lambda: self._popup_menu(self.c.selected_label,
                                                                 anchor=self.change_btn))
        bind.addWidget(self.change_btn)
        self.keyboard_btn = QPushButton(icon("input-keyboard-virtual"), "&Virtual Keyboard…")
        self.keyboard_btn.clicked.connect(self._keyboard)
        bind.addWidget(self.keyboard_btn)
        self.revert_btn = QPushButton(icon("document-revert"), "Re&vert Button")
        self.revert_btn.clicked.connect(lambda: self._guard(self.c.revert_button))
        bind.addWidget(self.revert_btn)
        self.reset_btn = QPushButton(icon("edit-reset"), "Reset to &Default")
        self.reset_btn.clicked.connect(lambda: self._set(Binding.default()))
        bind.addWidget(self.reset_btn)
        bind.addStretch(1)
        bind.addWidget(secondary("Keys are physical key positions, shown with US-QWERTY "
                                 "legends. The character typed depends on your keyboard "
                                 "layout."))
        editor.addWidget(bind_card)
        self.page_stack.addWidget(editor_page)
        self.cpi_page = CpiPage(self.c)
        self.page_stack.addWidget(self.cpi_page)
        self.lighting_page = LightingPage(self.c)
        self.page_stack.addWidget(self.lighting_page)

        # -- footer: draft state, write state and the primary action
        footer = QHBoxLayout()
        footer.setSpacing(10)
        status_col = QVBoxLayout()
        status_col.setSpacing(2)
        self.draft_status = QLabel()
        self.apply_status = secondary()
        status_col.addWidget(self.draft_status)
        status_col.addWidget(self.apply_status)
        footer.addLayout(status_col, 1)
        self.single_btn = QPushButton()
        self.single_btn.clicked.connect(lambda: self.c.apply(button=self.c.selected_label))
        self.single_btn.setMinimumHeight(34)
        footer.addWidget(self.single_btn)
        self.apply_btn = QPushButton(icon("dialog-ok-apply", QStyle.SP_DialogApplyButton, self),
                                     "Apply to Mouse")
        self.apply_btn.setAccessibleName("Apply to mouse")
        self.apply_btn.setDefault(True)
        self.apply_btn.setMinimumHeight(34)
        self.apply_btn.clicked.connect(self._apply)
        footer.addWidget(self.apply_btn)
        outer.addLayout(footer)

        self.battery_timer = QTimer(self)
        self.battery_timer.setInterval(30_000)
        self.battery_timer.timeout.connect(self.c.refresh_battery)
        self.c.subscribe(self.render)
        self.render()

    # -- rendering -------------------------------------------------------
    def render(self) -> None:
        self._updating = True
        try:
            self._render()
        finally:
            self._updating = False

    def _render(self) -> None:
        c = self.c
        busy = c.writing

        # device
        self.device_combo.clear()
        receiver = c.device is not None and c.device.transport is Transport.RECEIVER
        if receiver and not self.battery_timer.isActive():
            self.battery_timer.start()
        elif not receiver:
            self.battery_timer.stop()
        devices = c.discovery.devices
        if len(devices) > 1:
            self.device_combo.addItem("Choose a device…", None)
        for d in devices:
            self.device_combo.addItem(f"{d.model} ({d.transport.value})", d.token)
        if c.device is not None:
            self.device_combo.setCurrentIndex(self.device_combo.findData(c.device.token))
        self.device_combo.setEnabled(len(devices) > 1 and not busy)
        self.refresh_btn.setEnabled(not busy and not c.reading)
        lighting_only = self.page_stack.currentWidget() is self.lighting_page
        blocker = c.apply_blocker(lighting_only)
        if c.device is not None:
            status = f"Connected: {c.device.model}, {c.device.transport.value}."
            if receiver:
                status += (f" Battery {c.battery_level}%." if c.battery_level is not None
                           else " Battery unavailable.")
            if c.reading:
                status += " Reading the buttons stored on the mouse…"
            elif c.read_result and c.read_result.layout is not None:
                status += f" Buttons read from the mouse at {c.read_time}."
            elif c.read_result and c.read_result.message:
                status += f" {c.read_result.message}"
            self.device_status.setText(status)
            self.device_chip.setText(c.device.transport.value)
            self.device_chip.setVisible(True)
        else:
            self.device_status.setText(f"Not ready: {blocker}" if blocker else "")
            self.device_chip.setVisible(False)

        # profiles
        self.profile_combo.clear()
        for p in c.store.profiles:
            suffix = " (built in)" if p.builtin and p.id != DEVICE_PROFILE_ID else ""
            self.profile_combo.addItem(p.name + suffix, p.id)
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(c.profile_id))
        builtin = c.profile.builtin
        self.profile_combo.setEnabled(not busy)
        self.save_btn.setEnabled(not busy and not builtin and c.dirty)
        self.save_as_btn.setEnabled(not busy)
        self.rename_action.setEnabled(not busy and not builtin)
        self.duplicate_action.setEnabled(not busy)
        self.delete_action.setEnabled(not busy and not builtin)
        self.more_btn.setEnabled(not busy)
        self.draft_status.setText(
            "● Unsaved changes (not saved to a profile; not on the mouse until you apply)."
            if c.dirty else "No unsaved changes.")

        # side view
        written = c.last_written.layout if c.last_written else None
        for label, key in self.all_buttons.items():
            binding = c.draft.binding(label)
            key.set_mapping(short_text(binding, label), binding != c.profile.layout.binding(label))
            key.setChecked(label == c.selected_label)
            key.setEnabled(not busy)
            key.setToolTip(f"{accessible_name(label)}: {binding.label()}")

        # per-button panel
        n = c.selected_label
        binding = c.draft.binding(n)
        self.enabled_check.setChecked(binding != Binding.disabled())
        can_toggle = c.can_disable_selected()
        self.enabled_check.setEnabled(not busy and can_toggle)
        self.enabled_check.setAccessibleName(f"{button_title(n)} enabled")
        self.enabled_check.setToolTip("Enable or disable this button in the editor." if can_toggle
                                     else "Assign Left click to another button first.")
        self.panel_title.setText(button_title(n))
        self.selected_label.setText(button_position(n))
        self.current_mapping.setText(short_text(binding, n).replace("\n", ""))
        saved = c.profile.layout.binding(n)
        self.changed_note.setText(f"Changed from “{saved.label()}” in “{c.profile.name}”."
                                  if binding != saved else "")
        self.changed_note.setVisible(binding != saved)
        self.factory_value.setText(factory_binding(n).label())
        on_mouse = c.store.device_profile
        self.on_mouse_value.setText(
            f"{on_mouse.layout.binding(n).label()}  (read {c.read_time})" if on_mouse
            else ("Reading…" if c.reading else "Not read"))
        self.written_value.setText(written.binding(n).label() if written is not None
                                   else "Not yet")
        for b in (self.change_btn, self.keyboard_btn):
            b.setEnabled(not busy)
        self.revert_btn.setEnabled(not busy and binding != saved)
        self.revert_btn.setToolTip(f"Back to “{saved.label()}” from “{c.profile.name}”")
        self.reset_btn.setEnabled(not busy and binding != Binding.default())
        self.single_btn.setVisible(self.view_tabs.currentIndex() in (0, 1))
        self.single_btn.setText(f"Apply {button_title(n)} Only")
        single_blocker = c.apply_blocker(button=n)
        self.single_btn.setEnabled(single_blocker is None)
        self.single_btn.setToolTip(single_blocker or "Read the live button table and replace only this mapping.")
        self.undo_btn.setEnabled(c.can_undo)
        self.redo_btn.setEnabled(c.can_redo)

        self.cpi_page.render()
        self.lighting_page.render()

        # apply
        self.apply_btn.setEnabled(blocker is None)
        action = "Apply Lighting Only" if lighting_only else "Apply Full Profile"
        self.apply_btn.setText("Writing…" if busy else action)
        self.apply_btn.setAccessibleName(action)
        self.apply_btn.setToolTip(blocker or action)
        self.apply_status.setText(self._apply_text())
        self.notice.setText(c.notice)
        self.notice.setVisible(bool(c.notice))

    def _apply_text(self) -> str:
        c = self.c
        if c.writing:
            return "Writing to the mouse. Please wait and keep it connected."
        if c.device_state is DeviceState.STATE_UNKNOWN:
            return ("Device state unknown: the last write was interrupted. Your draft is kept. "
                    "Reconnect the mouse, then apply again or apply the factory thumb layout.")
        if c.last_result and c.last_result.status is ApplyStatus.REJECTED:
            return f"Nothing was written: {c.last_result.message}"
        r = c.last_result
        if r and c.last_result_lighting_only:
            return f"Lighting only. {r.message}"
        if r and r.status is ApplyStatus.COMPLETED_VERIFIED:
            return f"{r.message} A backup was taken first."
        if r and r.status is ApplyStatus.COMPLETED_PARTIALLY_VERIFIED:
            return r.message
        if r and r.status is ApplyStatus.VERIFY_MISMATCH:
            return f"Written, but the check found differences. {r.message}"
        if c.device_state is DeviceState.WRITE_COMPLETED:
            same = c.last_written and c.last_written.layout == c.draft.resolved()
            return ("Write completed. Device settings were not read back. "
                    + ("The editor matches the layout last written by this app."
                       if same else "The editor differs from the layout last written by this app."))
        return "Nothing written to the mouse in this session."

    # -- events ----------------------------------------------------------
    def closeEvent(self, event) -> None:
        if self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def _device_chosen(self, index: int) -> None:
        if not self._updating:
            self.c.select_device(self.device_combo.itemData(index))

    def _profile_chosen(self, index: int) -> None:
        pid = self.profile_combo.itemData(index)
        if pid == self.c.profile_id:
            return
        if self.c.dirty and not self._confirm("Discard unsaved changes?",
                                              "Your unsaved changes will be lost."):
            self.render()
            return
        self.c.load_profile(pid)

    def _popup_menu(self, label: int, anchor: QWidget | None = None) -> None:
        if self.c.writing:
            return
        self.c.select_button(label)
        menu = build_binding_menu(self, label, self.c.draft.binding(label),
                                  self.c.backend.supports, self._set, self._keyboard)
        widget = anchor or self.thumb_buttons[label]
        menu.exec(widget.mapToGlobal(widget.rect().bottomLeft()))

    def _backups(self) -> None:
        dlg = BackupsDialog(self.c.store.dir / "backups", self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen is not None:
            self._guard(lambda: self.c.load_layout(dlg.chosen.layout))
            self.c.notice = (f"Loaded the backup from {dlg.chosen.taken_at}. Check it, then use "
                             "Apply Full Profile on the Side or Top tab to restore the full layout.")
            self.render()

    def _tab_changed(self, index: int) -> None:
        if index < 2:
            self.page_stack.setCurrentIndex(0)
            self.view_stack.setCurrentIndex(index)
            self.view_title.setText("Thumb buttons" if index == 0 else "Top buttons and wheel")
        else:
            self.page_stack.setCurrentIndex(index - 1)
        self.render()

    def _keyboard(self) -> None:
        n = self.c.selected_label
        dlg = VirtualKeyboardDialog(n, self.c.draft.binding(n), self)
        if dlg.exec() == QDialog.Accepted and dlg.binding is not None:
            self._set(dlg.binding)

    def _set(self, binding: Binding) -> None:
        try:
            self.c.set_binding(binding)
        except (ProfileError, RuntimeError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def _ask_name(self, title: str, default: str = "") -> str | None:
        name, ok = QInputDialog.getText(self, title, "Profile name:", text=default)
        return name.strip() if ok and name.strip() else None

    def _save(self) -> None:
        self._guard(self.c.save_profile)

    def _save_as(self) -> None:
        name = self._ask_name("Save profile as")
        if name:
            self._guard(lambda: self.c.save_as(name))

    def _rename(self) -> None:
        name = self._ask_name("Rename profile", self.c.profile.name)
        if name:
            self._guard(lambda: self.c.rename_profile(name))

    def _duplicate(self) -> None:
        name = self._ask_name("Duplicate profile", f"{self.c.profile.name} copy")
        if name:
            self._guard(lambda: self.c.duplicate_profile(name))

    def _delete(self) -> None:
        if self._confirm("Delete profile?", f"Delete “{self.c.profile.name}” from this computer? "
                                            "This does not change the mouse."):
            self._guard(self.c.delete_profile)

    def _guard(self, fn) -> None:
        try:
            fn()
        except (ProfileError, RuntimeError, KeyError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    def _apply(self) -> None:
        result = self.c.apply(lighting_only=self.page_stack.currentWidget() is self.lighting_page)
        if result is ApplyRequest.NEEDS_ACKNOWLEDGEMENT:
            if self._confirm("Replace the whole button table?", FULL_TABLE_WARNING):
                self.c.apply(acknowledge_full_table=True)
