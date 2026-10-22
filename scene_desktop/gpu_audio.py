"""Audio-only sliding preview windows for GPU visual playback.

The OpenGL compositor can update immediately without re-rendering video.
Only audio mixing uses FFmpeg; audio is stored in app-owned temporary files,
never alters original narration, music, SFX or video sources.
"""
from __future__ import annotations
from pathlib import Path
import threading

from PySide6.QtCore import QThread, Signal

from .timeline import StudioProject
from .studio_render import _audio_items, _mix_audio

WINDOW_MS = 20000


def has_timeline_audio(project: StudioProject) -> bool:
    return bool(_audio_items(project))


def audio_active_between(project: StudioProject, start_ms: int, end_ms: int) -> bool:
    return any(item.start_ms < end_ms and item.end_ms > start_ms
               for item in _audio_items(project))


def audio_window(project: StudioProject, start_ms: int) -> tuple[int,int]:
    start = max(0, min(start_ms,project.duration_ms-100))
    end = min(project.duration_ms,start+WINDOW_MS)
    return start,end


class GPUAudioMixThread(QThread):
    ready = Signal(str,int,int,int)
    failed = Signal(str)

    def __init__(self,project: StudioProject, start_ms: int,
                 filename: Path, generation: int):
        super().__init__()
        self.snapshot=StudioProject.from_dict(project.to_dict())
        self.start_ms,self.end_ms=audio_window(self.snapshot,start_ms)
        self.filename=filename
        self.generation=generation
        self.stop_event=threading.Event()

    def run(self):
        try:
            self.filename.parent.mkdir(parents=True,exist_ok=True)
            if not has_timeline_audio(self.snapshot):
                return
            result=_mix_audio(self.snapshot,self.filename,self.stop_event,
                              (self.start_ms,self.end_ms))
            if not self.stop_event.is_set() and result and result.is_file():
                self.ready.emit(str(result),self.start_ms,self.end_ms,
                                self.generation)
        except Exception as exc:
            self.failed.emit(str(exc))
