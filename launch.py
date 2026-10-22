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
    if "--check-offline-sml-runtime" in sys.argv:
        # Check the bundled local backend independently of Qt WebEngine.
        # The actual loopback server/UI will be exercised by a separate CI step.
        import tempfile
        from pathlib import Path
        from fastapi import FastAPI
        from scene_desktop.offline_sml_backend.server import create_app
        with tempfile.TemporaryDirectory() as data:
            backend=create_app(Path(data)/"offline-sml", 49173)
            if not isinstance(backend, FastAPI):
                return 7
        # Avoid hidden Qt helper/background threads outliving CLI diagnostics.
        import os
        os._exit(0)
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
        from scene_desktop.offline_sml_backend.ai_workspace import run_worker
        return run_worker(data)
    from scene_desktop.app import main as start_gui
    return start_gui()


if __name__ == "__main__":
    raise SystemExit(main())
