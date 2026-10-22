"""Lifecycle and embedded webview for a FULL locally running SML UI.

Only 127.0.0.1 is used. No VPS address/token, Drive or YouTube is required.
The local FastAPI service has an independent SQLite DB in Rajudesktop AppData.
"""
from __future__ import annotations
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QTimer, QUrl, Signal


class OfflineSMLService(QObject):
    ready = Signal(str)
    failed = Signal(str)
    stopped = Signal()

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir=Path(data_dir).expanduser().resolve()
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self._poll=QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._check)
        self._attempts=0

    def start(self):
        if self.process is not None and self.process.poll() is None:
            if self.port is not None:
                self.ready.emit(f'http://127.0.0.1:{self.port}/self-media-library/')
            return
        self.data_dir.mkdir(parents=True,exist_ok=True)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1",0))
            port=probe.getsockname()[1]
        self.port=port
        args=(["--offline-sml-server"] if getattr(sys,"frozen",False)
              else ["-m","scene_desktop.offline_sml_backend.server"])
        args.extend(["--port",str(port),"--data-dir",str(self.data_dir)])
        opts={}
        if os.name=="nt":
            opts["creationflags"]=getattr(subprocess,"CREATE_NO_WINDOW",0)
        env={**os.environ,"SML_OFFLINE_ONLY":"1","SML_DATA_ROOT":str(self.data_dir)}
        try:
            self.process=subprocess.Popen(
                [sys.executable,*args],
                cwd=str(Path(__file__).resolve().parents[1]) if not getattr(sys,"frozen",False) else None,
                env=env,stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**opts
            )
        except OSError as exc:
            self.failed.emit(f"Unable to start local SML server: {exc}")
            return
        self._attempts=0
        self._poll.start()

    def _check(self):
        if self.process is None or self.port is None:
            self._poll.stop()
            return
        if self.process.poll() is not None:
            self._poll.stop()
            self.failed.emit("Local SML process ended; check local dependencies/logs")
            return
        self._attempts+=1
        try:
            with urlopen(
                Request(f"http://127.0.0.1:{self.port}/__sml_desktop_health",
                        headers={"Host":f"127.0.0.1:{self.port}"}),
                timeout=0.18
            ) as response:
                if response.status==200:
                    self._poll.stop()
                    self.ready.emit(
                        f"http://127.0.0.1:{self.port}/self-media-library/"
                    )
                    return
        except (OSError,ValueError):
            pass
        if self._attempts>=60:
            self._poll.stop()
            self.stop()
            self.failed.emit("Offline SML startup timed out; check Python dependencies")

    def stop(self):
        self._poll.stop()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            self.process=None
        self.stopped.emit()


def make_local_webview(port: int, parent=None):
    """Import WebEngine only when the user opens full SML; headless editor stays safe."""
    from PySide6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView

    class RestrictNavigation(QWebEnginePage):
        def acceptNavigationRequest(self, url, kind, is_main_frame):
            return (url.scheme()=="http" and url.host()=="127.0.0.1"
                    and url.port()==port)

    class RestrictRequests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url=info.requestUrl()
            if not (url.scheme()=="http" and url.host()=="127.0.0.1"
                    and url.port()==port):
                info.block(True)

    view=QWebEngineView(parent)
    profile=QWebEngineProfile(view)
    # Chromium HTTP cache, cookies and storage never persist credentials
    # outside the independent local SML context.
    # An unnamed QWebEngineProfile is already off-the-record.
    guard=RestrictRequests(profile)
    profile.setUrlRequestInterceptor(guard)
    page=RestrictNavigation(profile,view)
    view.setPage(page)
    # Keep Python references alive for requests & page lifetime.
    view._sml_guard=guard
    view._sml_profile=profile
    view._sml_page=page
    view.setUrl(QUrl(f"http://127.0.0.1:{port}/self-media-library/"))
    return view
