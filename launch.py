"""Scene Desktop Studio's packaged Windows launcher and read-only diagnostics."""
from __future__ import annotations
import sys


def main():
    if "--check-whisper-runtime" in sys.argv:
        # Import backend/runtime libraries inside the packaged EXE, not merely
        # on the CI Python host. Never downloads any model or handles user media.
        from faster_whisper import WhisperModel
        import ctranslate2
        import av
        import tokenizers
        if not all([WhisperModel,ctranslate2,av,tokenizers]):
            return 3
        return 0
    if "--check-gpu-runtime" in sys.argv:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
        from OpenGL import GL
        from scene_desktop.live_preview import OpenGLTimelineCanvas
        if not all([QOpenGLWidget,GL,OpenGLTimelineCanvas]):
            return 4
        return 0
    if "--offline-sml-server" in sys.argv:
        from scene_desktop.offline_sml_backend.server import main as serve
        i=sys.argv.index("--offline-sml-server")
        return serve(sys.argv[i+1:])
    if "--offline-sml-ai-worker" in sys.argv:
        from pathlib import Path
        from scene_desktop.offline_sml_backend.server import configure_backend
        args=sys.argv[sys.argv.index("--offline-sml-ai-worker")+1:]
        if not args:
            return 6
        data=configure_backend(Path(args[0]))
        from ai_workspace import run_worker
        return run_worker(data)
    from scene_desktop.app import main as start_gui
    return start_gui()


if __name__ == "__main__":
    raise SystemExit(main())
