"""CapCut 9.6 Windows foreground adapter: window identity before every click.

No credential access, draft writes, config edits, native DLL injection or cloud actions.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import time

from .core import Halt, installed_evidence, export_dialog_match


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    exe: Path
    title: str
    class_name: str
    rect: tuple[int, int, int, int]

    @property
    def width(self):
        return self.rect[2] - self.rect[0]

    @property
    def height(self):
        return self.rect[3] - self.rect[1]


@dataclass(frozen=True)
class Card:
    hwnd: int
    pid: int
    rect: tuple[int, int, int, int]
    rx: float
    ry: float


class Driver:
    def __init__(self):
        try:
            import win32gui
            import win32con
            import win32process
            import psutil
            import pyautogui
        except ImportError as exc:
            raise Halt("Windows dependencies missing. Launch the packaged EXE or install requirements.") from exc
        self.gui, self.con, self.proc, self.psutil, self.mouse = (
            win32gui, win32con, win32process, psutil, pyautogui)
        self.mouse.FAILSAFE = True
        self.mouse.PAUSE = .15

    def _win(self, hwnd):
        if not self.gui.IsWindowVisible(hwnd):
            raise Halt("CapCut window disappeared.")
        _, pid = self.proc.GetWindowThreadProcessId(hwnd)
        try:
            exe = Path(self.psutil.Process(pid).exe())
        except (OSError, self.psutil.Error) as exc:
            raise Halt("Cannot inspect CapCut process identity.") from exc
        if exe.name.casefold() != "capcut.exe":
            raise Halt("Foreground window is not CapCut.exe.")
        return Window(hwnd, pid, exe, self.gui.GetWindowText(hwnd),
                      self.gui.GetClassName(hwnd), tuple(self.gui.GetWindowRect(hwnd)))

    def windows(self):
        results = []
        def each(hwnd, _):
            if not self.gui.IsWindowVisible(hwnd):
                return
            try:
                win = self._win(hwnd)
            except Exception:
                return
            if win.width > 100 and win.height > 100:
                results.append(win)
        self.gui.EnumWindows(each, None)
        return results

    def card_at_cursor(self):
        x, y = self.mouse.position()
        hwnd = self.gui.GetAncestor(self.gui.WindowFromPoint((x, y)), self.con.GA_ROOT)
        win = self._win(hwnd)
        if win.width < 650 or win.height < 450:
            raise Halt("Hover over the center of the intended draft card in CapCut Home.")
        if win.class_name.startswith(("MainWindow_QMLTYPE_", "ExportWindow_QMLTYPE_")):
            raise Halt("Expected CapCut Home grid, not the editor or Export dialog.")
        installed_evidence(win.exe)
        l, t, r, b = win.rect
        if not (l < x < r and t < y < b):
            raise Halt("Cursor is outside CapCut Home.")
        return Card(win.hwnd, win.pid, win.rect, (x-l)/win.width, (y-t)/win.height)

    def editor(self):
        matches = [w for w in self.windows()
                   if w.class_name.startswith("MainWindow_QMLTYPE_")
                   and w.title.strip().casefold() == "capcut"
                   and w.width >= 900 and w.height >= 500]
        if len(matches) != 1:
            raise Halt(f"Expected one visible CapCut editor, found {len(matches)}.")
        installed_evidence(matches[0].exe)
        return matches[0]

    def dialog(self, expected_name):
        editor = self.editor()
        all_dialogs = [w for w in self.windows() if w.class_name.startswith("ExportWindow_QMLTYPE_")]
        if len(all_dialogs) != 1 or all_dialogs[0].pid != editor.pid:
            raise Halt("Cannot uniquely identify the current CapCut export dialog.")
        dialog = all_dialogs[0]
        if not export_dialog_match(dialog.title, expected_name):
            raise Halt(f"Wrong draft export dialog: {dialog.title!r}, expected {expected_name!r}.")
        return dialog

    def focus(self, win):
        # Do not restore/minimize or rearrange the editor unexpectedly.
        if self.gui.IsIconic(win.hwnd):
            raise Halt("CapCut is minimized. Restore it manually.")
        try:
            self.gui.SetForegroundWindow(win.hwnd)
        except Exception as exc:
            raise Halt("Windows blocked focusing CapCut; click the editor manually.") from exc
        time.sleep(.35)
        hwnd = self.gui.GetForegroundWindow()
        _, pid = self.proc.GetWindowThreadProcessId(hwnd)
        if pid != win.pid:
            raise Halt("Another app owns the keyboard/mouse. Refusing blind input.")

    def click(self, win, rx, ry, *, double=False):
        self.focus(win)
        current = self._win(win.hwnd)
        if (current.pid != win.pid or current.rect != win.rect or
            current.title != win.title or current.class_name != win.class_name):
            raise Halt("CapCut window moved or changed. Calibration invalid; no click.")
        if not (.02 <= rx <= .98 and .01 <= ry <= .99):
            raise Halt("Click target is out of the safe window bounds.")
        l, t, r, b = win.rect
        x = round(l + win.width*rx)
        y = round(t + win.height*ry)
        if double:
            self.mouse.doubleClick(x, y, interval=.14)
        else:
            self.mouse.click(x, y)

    def open_card(self, card: Card, stop):
        found = next((w for w in self.windows() if w.hwnd == card.hwnd), None)
        if not found or found.pid != card.pid or found.rect != card.rect:
            raise Halt("CapCut Home position has changed; record the card again.")
        if any(w.class_name.startswith("ExportWindow_QMLTYPE_") for w in self.windows()):
            raise Halt("Another CapCut export dialog is already open.")
        self.click(found, card.rx, card.ry, double=True)
        limit = time.monotonic() + 90
        while time.monotonic() < limit:
            if stop.is_set():
                raise Halt("Stopped before export. No final Export button clicked.")
            try:
                return self.editor()
            except Halt as exc:
                if "Expected one visible CapCut editor, found 0" not in str(exc):
                    raise
            stop.wait(.5)
        raise Halt("CapCut editor failed to open in 90 seconds.")

    def open_export(self, expected_name, stop, *, editor_point=(.920, .023)):
        if any(w.class_name.startswith("ExportWindow_QMLTYPE_") for w in self.windows()):
            return self.dialog(expected_name)
        editor = self.editor()
        self.click(editor, *editor_point)
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if stop.is_set():
                raise Halt("Stopped before final Export click.")
            dlg = [w for w in self.windows() if w.class_name.startswith("ExportWindow_QMLTYPE_")]
            if dlg:
                return self.dialog(expected_name)
            stop.wait(.4)
        raise Halt("Native export dialog did not appear. Check your UI layout.")

    def screenshot_marker(self, win, ratio, path: Path):
        from PIL import ImageDraw
        l, t, _, _ = win.rect
        pic = self.mouse.screenshot(region=(l, t, win.width, win.height))
        pen = ImageDraw.Draw(pic)
        x, y = round(win.width * ratio[0]), round(win.height * ratio[1])
        pen.ellipse((x-16, y-16, x+16, y+16), outline="red", width=5)
        path.parent.mkdir(parents=True, exist_ok=True)
        pic.save(path)

    def start_export(self, expected_name, ratio=(.817, .959)):
        dlg = self.dialog(expected_name)
        self.click(dlg, *ratio)
