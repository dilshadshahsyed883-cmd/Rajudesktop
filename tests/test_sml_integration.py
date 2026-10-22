"""SML V2 Editor API read-only integration, checksum and UI regression tests."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import unittest

from scene_desktop.sml_client import (
    SMLClient, SMLAsset, SMLError, normalize_url, MAX_VIDEO
)
from scene_desktop.library import MediaLibrary
from scene_desktop.media import ffmpeg_path


class Handler(BaseHTTPRequestHandler):
    token="test-token"
    payload=b""
    sha=""
    seen=[]
    wrong_hash=False
    redirect=False
    invalid_auth=False

    def log_message(self, *args):
        return

    def _reply(self,status,kind,payload):
        self.send_response(status)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        type(self).seen.append(("POST",self.path))
        self._reply(405,"text/plain",b"Read-only test")

    def do_GET(self):
        type(self).seen.append(("GET",self.path))
        if self.headers.get("X-SML-Editor-Token")!=self.token:
            self._reply(401,"application/json",b'{"detail":"invalid token"}')
            return
        if self.redirect:
            self.send_response(302)
            self.send_header("Location","http://example.com/steal-token")
            self.end_headers()
            return
        if self.path=="/api/v1/media/inventory":
            self._reply(200,"application/json",json.dumps({"counts":{
                "video":{"approved":0,"total":0},
                "image":{"approved":1,"total":1}
            }}).encode())
        elif self.path.startswith("/api/v1/media/search?"):
            item={
                "id":"IMG-TEST001","type":"image","source_filename":"forest.png",
                "source_id":"SRC-demo","keywords":["forest","trees"],
                "description":"Pine forest","content_url":
                "/api/v1/media/image/IMG-TEST001/content","sha256":self.sha,
                "duration":0
            }
            self._reply(200,"application/json",json.dumps({
                "items":[item],"total":1,"query":"forest"
            }).encode())
        elif self.path=="/api/v1/media/image/IMG-TEST001/content":
            self._reply(200,"image/png",self.payload)
        else:
            self._reply(404,"application/json",b"{}")


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ex=ffmpeg_path()
        t=tempfile.TemporaryDirectory()
        cls.tmp=t
        img=Path(t.name)/"forest.png"
        subprocess.run([ex,"-hide_banner","-loglevel","error","-y",
                        "-f","lavfi","-i","color=c=green:s=160x90",
                        "-frames:v","1",str(img)],check=True,timeout=30)
        Handler.payload=img.read_bytes()
        Handler.sha=hashlib.sha256(Handler.payload).hexdigest()
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.tmp.cleanup()

    def setUp(self):
        Handler.seen=[]
        Handler.redirect=False

    def test_read_only_approved_search_import_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            client=SMLClient(self.base,"test-token")
            inventory=client.inventory()
            self.assertEqual(inventory["image"]["approved"],1)
            assets=client.search("forest","image")
            self.assertEqual(len(assets),1)
            self.assertEqual(assets[0].id,"IMG-TEST001")
            path=client.download(assets[0],Path(folder)/"cache")
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),Handler.sha)
            lib=MediaLibrary(Path(folder)/"library.sqlite3")
            local=lib.ingest(path)
            lib.set_status([local["id"]],"approved")
            lib.set_tags(local["id"],list(assets[0].keywords)+["sml"])
            lib.record_sml_import(client.url,assets[0],local["id"],0)
            self.assertEqual(len(lib.sml_imports(client.url)),1)
            self.assertEqual(lib.list(status="approved")[0]["tags"][:2],["forest","trees"])
            self.assertTrue(all(method=="GET" for method,_ in Handler.seen))
            self.assertTrue(path.is_file())

    def test_reject_credentials_redirects_and_hash_mismatch_without_partial(self):
        for url in ("http://example.com:8147","https://user:secret@host",
                    "https://host/base?token=private","http://10.1.2.3",
                    "http://host.tailscale.com:8147", "https://host/../admin"):
            with self.subTest(url=url), self.assertRaises(SMLError):
                normalize_url(url)
        self.assertEqual(normalize_url("http://100.100.1.1:8147"),
                         "http://100.100.1.1:8147")
        with self.assertRaises(SMLError):
            SMLClient(self.base,"wrong").inventory()
        client=SMLClient(self.base,"test-token")
        asset=client.search()[0]
        Handler.redirect=True
        with self.assertRaises(SMLError):
            client.inventory()
        Handler.redirect=False
        fake=SMLAsset(**{**asset.__dict__,"sha256":"0"*64})
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(SMLError,"SHA-256 mismatch"):
                client.download(fake,folder)
            self.assertEqual(list(Path(folder).iterdir()),[])
        self.assertTrue(all(method=="GET" for method,_ in Handler.seen))

    def test_reject_untrusted_search_content_url_and_unsafe_id(self):
        bad={"id":"IMG-a/../b","type":"image","sha256":"a"*64}
        with self.assertRaises(SMLError):
            SMLAsset.parse(bad)
        bad={"id":"IMG-safe","type":"image","sha256":"a"*64,
             "content_url":"https://bad-site.example/secret"}
        with self.assertRaises(SMLError):
            SMLAsset.parse(bad)


class QtPanelTests(unittest.TestCase):
    def test_sml_tab_session_token_and_import_worker(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QLineEdit
        from scene_desktop.studio_window import StudioWindow,SMLWorker
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            from scene_desktop import studio_window
            with patch.object(studio_window,"app_directory",return_value=Path(folder)):
                window=StudioWindow()
                try:
                    self.assertEqual(window.left.tabText(1),"SML Connection")
                    self.assertEqual(window.sml_token.echoMode(),QLineEdit.EchoMode.Password)
                    self.assertFalse(window.sml_token.text())
                    self.assertEqual(window.sml_list.count(),0)
                finally:
                    if window.thumbnail_thread and window.thumbnail_thread.isRunning():
                        window.thumbnail_thread.wait(10000)
                    window.close()
