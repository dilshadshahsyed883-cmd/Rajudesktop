"""Windows-only native CapCut window discovery and guarded click transport.
Never reads or writes a CapCut draft or changes its timeline.
"""
from __future__ import annotations
from pathlib import Path
import time
import json
import os
import sys
from .core import GuardError, WindowInfo, click_location, ensure_export, ensure_single_editor, ensure_matching_dialog, is_editor, is_export

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

    def _process_info(self, pid: int) -> tuple[bool,str]:
        try:
            p=self.psutil.Process(pid)
            try:
                name=p.name()
            except (self.psutil.AccessDenied,OSError):
                name=""
            if name.casefold()=="capcut.exe":
                return True,name
            try:
                exe=Path(p.exe()).name
            except (self.psutil.AccessDenied,OSError):
                exe=""
            return exe.casefold()=="capcut.exe",name or exe or "unavailable"
        except (self.psutil.NoSuchProcess,self.psutil.AccessDenied,OSError) as exc:
            return False,type(exc).__name__

    def _scan(self) -> tuple[list[WindowInfo],list[dict]]:
        found=[]
        candidates=[]
        cache={}
        def collect(hwnd,_):
            try:
                _,pid=self.proc.GetWindowThreadProcessId(hwnd)
                if pid not in cache:
                    cache[pid]=self._process_info(pid)
                verified,name=cache[pid]
                title=self.gui.GetWindowText(hwnd)
                cls=self.gui.GetClassName(hwnd)
                visible=bool(self.gui.IsWindowVisible(hwnd))
                left,top,right,bottom=self.gui.GetWindowRect(hwnd)
                item=WindowInfo(hwnd,pid,title,cls,left,top,right,bottom)
                if verified or title.strip().casefold().startswith("capcut") or "MainWindow_QMLTYPE_" in cls or "ExportWindow_QMLTYPE_" in cls:
                    candidates.append(dict(hwnd=int(hwnd),pid=int(pid),process=name,
                        verified_process=verified,title=title[:150],class_name=cls,
                        visible=visible,bounds=[left,top,right,bottom],
                        classification=("editor" if verified and visible and is_editor(item) else
                            "export" if verified and visible and is_export(item) else "not accepted")))
                if verified and visible and right>left and bottom>top:
                    found.append(item)
            except Exception as exc:
                candidates.append(dict(hwnd=int(hwnd),error=type(exc).__name__))
        self.gui.EnumWindows(collect,None)
        return found,candidates

    def windows(self) -> list[WindowInfo]:
        return self._scan()[0]

    def diagnostic_report(self,destination: Path) -> tuple[Path,list[dict]]:
        windows,candidates=self._scan()
        data=dict(version="0.2.0",os=os.name,python=sys.version.split()[0],
            capcut_candidates=candidates,trusted_window_count=len(windows),
            editors=sum(is_editor(w) for w in windows),
            export_dialogs=sum(is_export(w) for w in windows))
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
        return destination,candidates

    def editor(self) -> WindowInfo:
        return ensure_single_editor(self.windows())

    def dialog(self,expected: str) -> WindowInfo:
        windows=self.windows()
        editors=[w for w in windows if is_editor(w)]
        if len(editors)>1:
            raise GuardError(f"Multiple CapCut editor windows: {len(editors)}.")
        return ensure_matching_dialog(windows,expected,editors[0] if editors else None)

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
