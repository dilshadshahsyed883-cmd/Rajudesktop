"""Windows-only native CapCut window discovery and guarded click transport.
Never reads or writes a CapCut draft or changes its timeline.
"""
from __future__ import annotations
from pathlib import Path
import time
from .core import GuardError, WindowInfo, click_location, ensure_export, ensure_single_editor, is_export

EDITOR_EXPORT_X=0.920  # Audit editor screenshot 2026-10-28
EDITOR_EXPORT_Y=0.023
DIALOG_EXPORT_X=0.817  # Audit 720x663 dialog screenshot
DIALOG_EXPORT_Y=0.959

class WindowsCapCut:
    def __init__(self) -> None:
        try:
            import win32gui
            import win32process
            import psutil
            import pyautogui
        except ImportError as exc:
            raise GuardError("Windows dependencies unavailable. Run start.bat to install requirements.") from exc
        self.gui=win32gui
        self.proc=win32process
        self.psutil=psutil
        self.mouse=pyautogui
        self.mouse.FAILSAFE=True
        self.mouse.PAUSE=0.12

    def _capcut_process(self,pid: int) -> bool:
        try:
            proc=self.psutil.Process(pid)
            return Path(proc.exe()).name.lower()=="capcut.exe"
        except (self.psutil.NoSuchProcess,self.psutil.AccessDenied,OSError):
            return False

    def windows(self) -> list[WindowInfo]:
        found=[]
        def collect(hwnd,_):
            if not self.gui.IsWindowVisible(hwnd):
                return
            try:
                _,pid=self.proc.GetWindowThreadProcessId(hwnd)
                if not self._capcut_process(pid):
                    return
                left,top,right,bottom=self.gui.GetWindowRect(hwnd)
                found.append(WindowInfo(hwnd=hwnd,pid=pid,title=self.gui.GetWindowText(hwnd),
                                        class_name=self.gui.GetClassName(hwnd),left=left,top=top,
                                        right=right,bottom=bottom))
            except Exception:
                return
        self.gui.EnumWindows(collect,None)
        return found

    def editor(self) -> WindowInfo:
        return ensure_single_editor(self.windows())

    def dialog(self,expected: str) -> WindowInfo:
        editor=self.editor()
        return ensure_export(self.windows(),editor,expected)

    def _focus(self,win: WindowInfo) -> None:
        if self.gui.IsIconic(win.hwnd):
            raise GuardError("Restore CapCut from minimized state and retry.")
        try:
            self.gui.SetForegroundWindow(win.hwnd)
        except Exception as exc:
            raise GuardError("Could not focus CapCut safely. Click its window manually and retry.") from exc
        time.sleep(0.35)
        foreground=self.gui.GetForegroundWindow()
        _,pid=self.proc.GetWindowThreadProcessId(foreground)
        if pid != win.pid:
            raise GuardError("Another app owns the foreground; refusing blind click.")

    def _click(self,win: WindowInfo,x_ratio: float,y_ratio: float) -> tuple[int,int]:
        point=click_location(win,x_ratio,y_ratio)
        self._focus(win)
        active=next((w for w in self.windows() if w.hwnd==win.hwnd),None)
        if not active or active.pid!=win.pid or active.rect!=win.rect or active.title!=win.title:
            raise GuardError("CapCut window changed during preflight; no click performed.")
        self.mouse.click(*point)
        return point

    def open_export(self,expected: str,timeout: int=18) -> WindowInfo:
        try:
            return self.dialog(expected)
        except GuardError:
            pass
        editor=self.editor()
        if any(is_export(w) for w in self.windows()):
            raise GuardError("An export dialog for another project/process is open; close it first.")
        self._click(editor,EDITOR_EXPORT_X,EDITOR_EXPORT_Y)
        limit=time.monotonic()+timeout
        while time.monotonic()<limit:
            time.sleep(0.4)
            try:
                return self.dialog(expected)
            except GuardError:
                if any(is_export(w) for w in self.windows()):
                    raise GuardError("Export dialog opened for a different project. Nothing was exported.")
        raise GuardError("CapCut export dialog did not open. Check layout/DPI or use manual Export button.")

    def press_export(self,expected: str) -> tuple[int,int]:
        dialog=self.dialog(expected)
        return self._click(dialog,DIALOG_EXPORT_X,DIALOG_EXPORT_Y)

    def screenshot(self,win: WindowInfo,destination: Path,marker: tuple[float,float]|None=None) -> Path:
        from PIL import ImageDraw
        image=self.mouse.screenshot(region=(win.left,win.top,win.width,win.height))
        if marker is not None:
            center=(int(win.width*marker[0]),int(win.height*marker[1]))
            pen=ImageDraw.Draw(image)
            r=16
            pen.ellipse((center[0]-r,center[1]-r,center[0]+r,center[1]+r),
                        outline="red",width=4)
        destination.parent.mkdir(parents=True,exist_ok=True)
        image.save(destination)
        return destination
