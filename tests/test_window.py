import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from aerocommand.backend import DisabledBackend, FakeBackend, FakeScenario
from aerocommand.controller import Controller, ThreadRunner
from aerocommand.profiles import Binding
from aerocommand.side_view import build_binding_menu
from aerocommand.virtual_keyboard import VirtualKeyboardDialog
from aerocommand.window import MainWindow, UiDispatcher


def build(qtbot, store, backend, demo=True, runner=None):
    c = Controller(store, backend, runner)
    w = MainWindow(c, demo=demo)
    qtbot.addWidget(w)
    c.start()
    return c, w


def test_demo_banner_and_grid(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    assert not w.demo_banner.isHidden()
    assert "Nothing is written" in w.demo_banner.text()
    assert w.thumb_buttons[3].accessibleName() == "Thumb 3, top row, first column"
    assert w.thumb_buttons[1].text() == "1\n1"
    assert w.apply_btn.isEnabled()


def test_ordinary_start_cannot_apply(qtbot, store):
    c, w = build(qtbot, store, DisabledBackend(), demo=False)
    assert w.demo_banner.isHidden()
    assert not w.apply_btn.isEnabled()
    assert "not enabled" in w.device_status.text()


def test_select_and_edit_binding(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    qtbot.mouseClick(w.thumb_buttons[5], Qt.LeftButton)
    assert c.selected_label == 5
    assert w.panel_title.text() == "Button 5"
    assert w.current_mapping.text() == "5"
    menu = build_binding_menu(w, 5, c.draft.binding(5), c.backend.supports, w._set)
    back = next(a for sub in menu.actions() if sub.menu() and sub.text() == "Mouse button"
                for a in sub.menu().actions() if a.text() == "Back")
    back.trigger()
    assert c.draft.binding(5) == Binding.mouse("BTN_BACK")
    assert w.current_mapping.text() == "Back"
    assert "Unsaved changes" in w.draft_status.text()
    assert w.thumb_buttons[5].changed and not w.thumb_buttons[4].changed
    qtbot.mouseClick(w.reset_btn, Qt.LeftButton)
    assert c.draft.binding(5) == Binding.default()


def test_menu_checks_current_mapping(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    menu = build_binding_menu(w, 2, Binding.key("KEY_F6"), c.backend.supports, w._set)
    checked = [a.text() for sub in menu.actions() if sub.menu()
               for a in sub.menu().actions() if a.isChecked()]
    assert checked == ["F6"]
    assert menu.actions()[0].text() == "Button 2: Key F6"


def test_virtual_keyboard_sticky_modifiers(qtbot, store, monkeypatch):
    c, w = build(qtbot, store, FakeBackend())
    c.select_button(9)

    def fake_exec(dlg):
        assert dlg.preview.text() == "Pick a key"
        qtbot.mouseClick(dlg.modifier_buttons["MOD_LCTRL"], Qt.LeftButton)
        qtbot.mouseClick(dlg.modifier_buttons["MOD_LSHIFT"], Qt.LeftButton)
        assert dlg.preview.text() == "Ctrl + Shift + …"
        qtbot.mouseClick(dlg.modifier_buttons["MOD_LALT"], Qt.LeftButton)   # third: refused
        assert not dlg.modifier_buttons["MOD_LALT"].isChecked()
        assert not dlg.warning.isHidden()
        qtbot.mouseClick(dlg.key_buttons["KEY_F6"], Qt.LeftButton)
        return dlg.result()

    monkeypatch.setattr(VirtualKeyboardDialog, "exec", fake_exec)
    qtbot.mouseClick(w.keyboard_btn, Qt.LeftButton)
    assert c.draft.binding(9) == Binding.shortcut(["MOD_LCTRL", "MOD_LSHIFT"], "KEY_F6")
    assert w.current_mapping.text() == "Ctrl+Shift+F6"


def test_virtual_keyboard_single_key_and_current_shown(qtbot, store):
    dlg = VirtualKeyboardDialog(2, Binding.shortcut(["MOD_LALT"], "KEY_Q"))
    qtbot.addWidget(dlg)
    assert dlg.modifier_buttons["MOD_LALT"].isChecked()
    assert dlg.key_buttons["KEY_Q"].font().bold()
    qtbot.mouseClick(dlg.modifier_buttons["MOD_LALT"], Qt.LeftButton)       # release
    qtbot.mouseClick(dlg.key_buttons["KEY_A"], Qt.LeftButton)
    assert dlg.binding == Binding.key("KEY_A")


def test_undo_redo_and_revert(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    c.select_button(4)
    w._set(Binding.key("KEY_A"))
    w._set(Binding.key("KEY_B"))
    assert w.undo_btn.isEnabled() and not w.redo_btn.isEnabled()
    qtbot.mouseClick(w.undo_btn, Qt.LeftButton)
    assert c.draft.binding(4) == Binding.key("KEY_A")
    qtbot.mouseClick(w.redo_btn, Qt.LeftButton)
    assert c.draft.binding(4) == Binding.key("KEY_B")
    c.select_button(1)
    w._set(Binding.key("KEY_C"))
    c.select_button(4)
    qtbot.mouseClick(w.revert_btn, Qt.LeftButton)       # only button 4 goes back
    assert c.draft.binding(4) == c.profile.layout.binding(4)
    assert c.draft.binding(1) == Binding.key("KEY_C")
    qtbot.mouseClick(w.undo_btn, Qt.LeftButton)         # revert is undoable too
    assert c.draft.binding(4) == Binding.key("KEY_B")
    assert c.selected_label == 4


def test_side_view_geometry(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    w.resize(1180, 640)
    w.show()
    k = w.thumb_buttons
    cx = {n: k[n].geometry().center().x() for n in k}
    cy = {n: k[n].geometry().center().y() for n in k}
    assert cx[1] < cx[4] < cx[7] < cx[10]     # column 1 toward the front
    assert cy[3] < cy[2] < cy[1]              # 3 on top, 1 at the bottom
    # Masks follow the traced key faces, so clickable areas never overlap.
    for a in k.values():
        for b in k.values():
            if a is not b:
                ra = a.mask().translated(a.pos())
                rb = b.mask().translated(b.pos())
                assert ra.intersected(rb).isEmpty(), (a.label, b.label)


def test_click_hits_the_traced_key(qtbot, store):
    from PySide6.QtCore import QPoint
    c, w = build(qtbot, store, FakeBackend())
    w.resize(1180, 640)
    w.show()
    key = w.thumb_buttons[8]
    centre = key.mask().boundingRect().center()
    qtbot.mouseClick(key, Qt.LeftButton, pos=centre)
    assert c.selected_label == 8
    assert not key.hitButton(QPoint(0, 0))     # bounding-box corner is outside the face


def test_double_click_apply_writes_once(qtbot, store, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    gate = threading.Event()
    backend = FakeBackend(gate=gate)
    runner = ThreadRunner(UiDispatcher())
    c, w = build(qtbot, store, backend, runner=runner)
    qtbot.mouseClick(w.apply_btn, Qt.LeftButton)
    assert c.writing and not w.apply_btn.isEnabled()
    qtbot.mouseClick(w.apply_btn, Qt.LeftButton)
    gate.set()
    qtbot.waitUntil(lambda: not c.writing, timeout=5000)
    runner.shutdown()
    assert backend.apply_calls == 1
    assert "Write completed. Device settings were not read back." in w.apply_status.text()


def test_declining_warning_writes_nothing(qtbot, store, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    backend = FakeBackend()
    c, w = build(qtbot, store, backend)
    qtbot.mouseClick(w.apply_btn, Qt.LeftButton)
    assert backend.apply_calls == 0


def test_interrupted_write_message(qtbot, store, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    c, w = build(qtbot, store, FakeBackend(FakeScenario.INTERRUPT))
    qtbot.mouseClick(w.apply_btn, Qt.LeftButton)
    assert "Device state unknown" in w.apply_status.text()
    assert w.apply_btn.isEnabled()


def test_close_issues_no_write(qtbot, store):
    backend = FakeBackend()
    c, w = build(qtbot, store, backend)
    w.close()
    assert backend.apply_calls == 0


def test_traced_geometry_is_consistent():
    from aerocommand.side_view import (BODY_PATH, PERFORATION_PATH, PANEL_PATH, SIDE_COVER_PATH,
                                       key_polygon)
    for n in range(1, 13):
        poly = key_polygon(n)
        assert all(PANEL_PATH.contains(poly.at(i)) for i in range(poly.count())), n
    assert all(SIDE_COVER_PATH.contains(PANEL_PATH.pointAtPercent(t / 50)) for t in range(51))
    edge = [SIDE_COVER_PATH.pointAtPercent(t / 100) for t in range(101)]
    assert all(BODY_PATH.contains(pt) for pt in edge if pt.y() < 718)
    assert not PERFORATION_PATH.intersects(SIDE_COVER_PATH)


def test_top_view_tab_and_left_click_guard(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    w.resize(1180, 700)
    w.show()
    w.view_tabs.setCurrentIndex(1)
    assert w.view_stack.currentWidget() is w.top_view
    key = w.top_buttons[18]
    qtbot.mouseClick(key, Qt.LeftButton, pos=key.mask().boundingRect().center())
    assert c.selected_label == 18
    assert w.panel_title.text() == "CPI button"
    assert w.factory_value.text() == "CPI cycle"
    c.select_button(13)
    w._set(Binding.key("KEY_A"))
    assert not w.apply_btn.isEnabled()
    assert "Left click" in c.apply_blocker()
    c.select_button(14)
    w._set(Binding.mouse("BTN_LEFT"))       # left click moved to the right button
    assert c.apply_blocker() is None


def test_top_view_hotspots_do_not_overlap(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    w.resize(1180, 700)
    w.show()
    w.view_tabs.setCurrentIndex(1)
    k = list(w.top_buttons.values())
    for a in k:
        for b in k:
            if a is not b:
                assert a.mask().translated(a.pos()).intersected(
                    b.mask().translated(b.pos())).isEmpty(), (a.label, b.label)


def test_cpi_tab_edits_presets_and_polling(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    w.view_tabs.setCurrentIndex(2)
    assert w.page_stack.currentWidget() is w.cpi_page
    page = w.cpi_page
    assert [r.spin.value() for r in page.rows] == [400, 800, 1200, 2400, 3200]
    assert not page.add_btn.isEnabled()                    # already 5
    page.rows[1].spin.setValue(1600)
    assert c.draft.settings.cpi_presets == (400, 1600, 1200, 2400, 3200)
    qtbot.mouseClick(page.rows[4].remove, Qt.LeftButton)
    assert len(c.draft.settings.cpi_presets) == 4 and page.add_btn.isEnabled()
    qtbot.mouseClick(page.rate_buttons[500], Qt.LeftButton)
    assert c.draft.settings.polling_hz == 500
    assert c.dirty
    c.undo()
    assert c.draft.settings.polling_hz == 1000


def test_lighting_tab_zone_colour_stops_rainbow(qtbot, store):
    c, w = build(qtbot, store, FakeBackend())
    w.view_tabs.setCurrentIndex(3)
    page = w.lighting_page
    assert page.preview.rainbow
    page.zone_buttons[1].on_pick("#123456")
    s = c.draft.settings
    assert s.zone_colors == ("#ff0000", "#123456", "#0000ff")
    assert s.startup_effect == "off" and not page.preview.rainbow
    page.reactive_on.setChecked(True)
    assert c.draft.settings.reactive_color == "#ffffff"
    page.dim.setValue(0)
    assert c.draft.settings.dim_timer_s == 0 and page.dim.text() == "Never"


def test_unread_settings_are_marked_and_left_alone(qtbot, store):
    backend = FakeBackend()
    backend.readable = True
    c, w = build(qtbot, store, backend)
    assert c.draft.settings.is_empty()          # nothing read for CPI/lighting
    w.view_tabs.setCurrentIndex(2)
    assert not w.cpi_page.cpi_unset.isHidden()
    w.cpi_page.rows[0].spin.setValue(500)
    assert w.cpi_page.cpi_unset.isHidden()
    assert c.draft.settings.polling_hz is None   # untouched stays unset


def test_zone_colour_notice_can_be_dismissed_for_good(qtbot, store):
    from aerocommand.settings import DeviceSettings
    backend = FakeBackend()
    backend.readable = True
    c, w = build(qtbot, store, backend)
    c.set_settings(startup_effect="rainbow")          # some lighting known, zones not
    page = w.lighting_page
    assert not page.zones_unset.isHidden()
    page.zones_hide.setChecked(True)
    assert page.zones_unset.isHidden()
    c2, w2 = build(qtbot, store, backend)              # a fresh window remembers it
    c2.set_settings(startup_effect="rainbow")
    assert w2.lighting_page.zones_unset.isHidden()
    assert (store.dir / "ui.ini").exists()


def test_close_to_tray_reopens_same_draft(qtbot, store, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    backend = FakeBackend()
    c, w = build(qtbot, store, backend)
    w.show()
    c.set_binding(Binding.key("KEY_F8"), 12)
    assert not w.close()
    assert w.isHidden() and w.tray.isVisible()
    w.tray.contextMenu().actions()[0].trigger()
    assert w.isVisible() and c.dirty
    assert c.draft.binding(12) == Binding.key("KEY_F8")
    assert backend.apply_calls == 0


def test_close_without_tray_accepts_close(qtbot, store, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    _, w = build(qtbot, store, FakeBackend())
    w.show()
    assert w.close() and w.isHidden()


def test_desktop_layout_selection(monkeypatch):
    from aerocommand.window import desktop_layout

    for value, expected in (("ubuntu:GNOME", "gnome"), ("KDE", "kde"),
                            ("Xfce", "kde"), ("", "kde")):
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", value)
        assert desktop_layout() == expected
    assert desktop_layout("gnome") == "gnome"


def test_gnome_layout_keeps_navigation_and_edit_actions(qtbot, store, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    c, w = build(qtbot, store, FakeBackend())
    w.show()
    assert w.refresh_btn.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert w.refresh_btn.accessibleName() == "Refresh"
    w.view_tabs.setCurrentIndex(3)
    assert w.page_stack.currentWidget() is w.lighting_page
    c.set_binding(Binding.key("KEY_F8"), 12)
    w.undo_btn.click()
    assert not c.dirty


def test_single_button_footer_position_and_visibility(qtbot, store):
    _, w = build(qtbot, store, FakeBackend())
    w.show()
    for index in (0, 1, 2, 3, 0):
        w.view_tabs.setCurrentIndex(index)
        assert w.single_btn.isVisible() == (index < 2)
        if index < 2:
            assert w.single_btn.parentWidget() is w.apply_btn.parentWidget()
            assert w.single_btn.y() == w.apply_btn.y()
            assert w.single_btn.x() + w.single_btn.width() <= w.apply_btn.x()


def test_single_apply_tracks_selected_device_mapping(qtbot, store):
    backend = FakeBackend(readable=True)
    c, w = build(qtbot, store, backend)
    c.select_button(12)
    assert not w.single_btn.isEnabled()
    c.set_settings(polling_hz=125)
    c.set_binding(Binding.key("KEY_F1"), 3)
    assert not w.single_btn.isEnabled()
    c.set_binding(Binding.key("KEY_F8"))
    assert w.single_btn.isEnabled()
    c.undo()
    assert not w.single_btn.isEnabled()
    c.redo()
    assert w.single_btn.isEnabled()
    w.single_btn.click()
    assert not w.single_btn.isEnabled()
    c.select_button(3)
    assert w.single_btn.isEnabled()


def test_enabled_checkbox_restores_binding_and_protects_left_click(qtbot, store):
    backend = FakeBackend(readable=True)
    c, w = build(qtbot, store, backend)
    c.select_button(3)
    mapping = c.draft.binding(3)
    assert w.enabled_check.isChecked()
    w.enabled_check.click()
    assert c.draft.binding(3) == Binding.disabled()
    assert not w.enabled_check.isChecked()
    w.enabled_check.click()
    assert c.draft.binding(3) == mapping
    c.select_button(13)
    assert w.enabled_check.isChecked() and not w.enabled_check.isEnabled()
    c.set_binding(Binding.mouse("BTN_LEFT"), 3)
    assert w.enabled_check.isEnabled()
    w.enabled_check.click()
    assert not w.single_btn.isEnabled() and w.apply_btn.isEnabled()
    assert backend.apply_calls == 0
    c.select_button(3)
    w.single_btn.click()
    c.select_button(13)
    assert w.single_btn.isEnabled()
    w.single_btn.click()
    assert backend.device_layout.binding(13) == Binding.disabled()
    assert backend.device_layout.binding(3) == Binding.mouse("BTN_LEFT")
