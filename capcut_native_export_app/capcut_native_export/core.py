"""Pure planning and MP4 completion checks for guarded native CapCut exports."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Iterator

EXPORT_RE = re.compile(r"^Export[-–](.+)$", flags=re.IGNORECASE)

class GuardError(RuntimeError):
    """Export halted because a required identity / safety check failed."""

@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    class_name: str
    left: int
    top: int
    right: int
    bottom: int
    @property
    def width(self) -> int:
        return self.right - self.left
    @property
    def height(self) -> int:
        return self.bottom - self.top
    @property
    def rect(self) -> tuple[int,int,int,int]:
        return self.left,self.top,self.right,self.bottom

def export_project(title: str) -> str | None:
    match = EXPORT_RE.match(title.strip())
    return match.group(1).strip() if match else None

def is_editor(w: WindowInfo) -> bool:
    return ((w.title.strip().casefold() == "capcut" or w.title.strip().casefold().startswith("capcut -")) and
            (w.class_name.startswith("MainWindow_QMLTYPE_") or w.class_name == "MainWindow") and
            w.width >= 640 and w.height >= 380)

def is_export(w: WindowInfo) -> bool:
    return (bool(export_project(w.title)) and
            w.class_name.startswith("ExportWindow_QMLTYPE_") and
            w.width >= 450 and w.height >= 400)

def ensure_single_editor(windows: list[WindowInfo]) -> WindowInfo:
    matches = [w for w in windows if is_editor(w)]
    if len(matches) != 1:
        raise GuardError(f"Expected exactly one visible CapCut editor window; found {len(matches)}.")
    return matches[0]

def ensure_export(windows: list[WindowInfo], editor: WindowInfo, expected: str) -> WindowInfo:
    expected = validate_project_name(expected)
    dialogs = [w for w in windows if is_export(w) and w.pid == editor.pid]
    if len(dialogs) != 1:
        raise GuardError(f"Expected exactly one export dialog for editor PID {editor.pid}; found {len(dialogs)}.")
    dialog = dialogs[0]
    actual = export_project(dialog.title)
    if actual is None or actual.casefold() != expected.casefold():
        raise GuardError(f"Export dialog project mismatch: expected {expected!r}, saw {actual!r}.")
    return dialog

def ensure_matching_dialog(windows: list[WindowInfo], expected: str, editor: WindowInfo | None = None) -> WindowInfo:
    """Input windows must already be verified as belonging to CapCut.exe."""
    expected=validate_project_name(expected)
    dialogs=[w for w in windows if is_export(w)]
    if len(dialogs)!=1:
        raise GuardError(f"Expected exactly one native CapCut export dialog; found {len(dialogs)}.")
    dialog=dialogs[0]
    actual=export_project(dialog.title)
    if actual is None or actual.casefold()!=expected.casefold():
        raise GuardError(f"Export dialog project mismatch: expected {expected!r}, saw {actual!r}.")
    if editor is not None and dialog.pid!=editor.pid:
        raise GuardError("CapCut editor and export dialog belong to different processes.")
    return dialog

def validate_project_name(name: str) -> str:
    name = name.strip()
    if not name or name in {".",".."} or len(name)>180 or any(c in name for c in '\\/:*?"<>|'):
        raise GuardError("Enter the exact project/export name (valid Windows file name, max 180 chars).")
    return name

def click_location(w: WindowInfo, x_ratio: float, y_ratio: float) -> tuple[int,int]:
    if not (0 < x_ratio < 1 and 0 < y_ratio < 1):
        raise ValueError("Click ratios must be strictly between 0 and 1.")
    if w.width <= 0 or w.height <= 0:
        raise GuardError("CapCut window has invalid dimensions.")
    return int(w.left+w.width*x_ratio),int(w.top+w.height*y_ratio)

def target_file(folder: str | Path, project: str) -> Path:
    project = validate_project_name(project)
    output_dir = Path(folder).expanduser()
    if not output_dir.is_dir():
        raise GuardError(f"Output folder does not exist: {output_dir}")
    target = output_dir/(project+".mp4")
    if target.exists():
        raise GuardError(f"Output already exists; refusing overwrite/duplicate: {target}")
    return target

def iter_mp4_atoms(path: Path, max_atoms: int=250000) -> Iterator[tuple[bytes,int]]:
    """Inspect ISO BMFF box headers without loading multi-GB video into memory."""
    size=path.stat().st_size
    if size < 16:
        return
    with path.open("rb") as stream:
        offset=0
        count=0
        while offset+8 <= size and count < max_atoms:
            stream.seek(offset)
            header=stream.read(8)
            if len(header)!=8:
                return
            length,atom=struct.unpack(">I4s",header)
            header_len=8
            if length==1:
                extended=stream.read(8)
                if len(extended)!=8:
                    return
                length=struct.unpack(">Q",extended)[0]
                header_len=16
            elif length==0:
                length=size-offset
            if length<header_len or offset+length>size:
                return
            yield atom,length
            offset+=length
            count+=1

def mp4_has_metadata(path: Path) -> bool:
    """Container-finalized proof only; does not establish effects/audio fidelity."""
    try:
        boxes=set(atom for atom,_ in iter_mp4_atoms(path))
        return b"ftyp" in boxes and b"mdat" in boxes and b"moov" in boxes
    except (OSError,ValueError,struct.error):
        return False

@dataclass
class FileObserver:
    path: Path
    min_bytes: int=4096
    stable_checks: int=3
    stable_interval_seconds: float=5.0
    _previous_size: int=-1
    _previous_mtime_ns: int=-1
    _stable: int=0
    def poll(self) -> tuple[bool,str]:
        try:
            stat=self.path.stat()
        except FileNotFoundError:
            self._stable=0
            return False,"Waiting for MP4 to appear"
        except OSError as exc:
            return False,f"Output inaccessible: {exc}"
        if stat.st_size<self.min_bytes:
            self._stable=0
            return False,f"Output incomplete ({stat.st_size:,} bytes)"
        if (stat.st_size,stat.st_mtime_ns)==(self._previous_size,self._previous_mtime_ns):
            self._stable+=1
        else:
            self._stable=0
        self._previous_size,self._previous_mtime_ns=stat.st_size,stat.st_mtime_ns
        if self._stable<self.stable_checks:
            return False,f"Rendering/writing: {stat.st_size / 1048576:.1f} MB; stability {self._stable}/{self.stable_checks}"
        if not mp4_has_metadata(self.path):
            return False,"File stable but MP4 metadata not complete (ftyp/mdat/moov)"
        return True,f"Verified finalized MP4 container: {stat.st_size / 1048576:.1f} MB"

def parse_audit_window_dict(entry: dict) -> WindowInfo | None:
    bounds=entry.get("bounds","")
    found=re.fullmatch(r"\s*(-?\d+),(-?\d+),(\d+),(\d+)\s*",bounds)
    if not found:
        return None
    left,top,width,height=(int(x) for x in found.groups())
    return WindowInfo(hwnd=int(entry["window"]),pid=0,title=entry["name"],class_name=entry["class_name"],
                      left=left,top=top,right=left+width,bottom=top+height)
