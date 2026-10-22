"""Desktop SML full backend: loopback API, page parity, offline guards and library bridge."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scene_desktop.library import MediaLibrary
from scene_desktop.offline_sml_bridge import sync_approved_media, LOCAL_ORIGIN


class LocalSMLBridgeTests(unittest.TestCase):
    def test_approved_image_links_into_editor_without_remote_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"offline-sml"
            image_dir=root/"images"
            image_dir.mkdir(parents=True)
            from PIL import Image
            picture=image_dir/"IMG-TEST.png"
            Image.new("RGB",(64,64),"green").save(picture)
            sha=hashlib.sha256(picture.read_bytes()).hexdigest()
            connection=sqlite3.connect(root/"library.db")
            connection.executescript("""
                CREATE TABLE clips (
                    id TEXT,filename TEXT,sha256 TEXT,source_id TEXT,
                    status TEXT,deleted_at TEXT,created_at TEXT
                );
                CREATE TABLE clip_keywords (clip_id TEXT,keyword TEXT);
                CREATE TABLE image_assets (
                    id TEXT,stored_name TEXT,sha256 TEXT,status TEXT,
                    deleted_at TEXT,created_at TEXT,keywords_json TEXT
                );
            """)
            connection.execute("INSERT INTO image_assets VALUES (?,?,?,?,?,?,?)",
                               ("IMG-TEST","IMG-TEST.png",sha,"approved",None,
                                "2026-10-22","[\"mountain\",\"forest\"]"))
            connection.commit()
            connection.close()
            library=MediaLibrary(Path(tmp)/"desktop.sqlite3")
            result=sync_approved_media(root,library)
            self.assertEqual(result["added"],1)
            self.assertTrue(picture.exists())
            records=library.list(status="approved")
            self.assertEqual(len(records),1)
            self.assertIn("forest",records[0]["tags"])
            self.assertEqual(len(library.sml_imports(LOCAL_ORIGIN)),1)
            # Repeated sync should leave original and editor catalog stable.
            self.assertEqual(sync_approved_media(root,library)["skipped"],1)

    def test_nonexistent_source_does_not_create_or_rewrite_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"offline-sml"
            library=MediaLibrary(Path(tmp)/"desktop.sqlite3")
            out=sync_approved_media(root,library)
            self.assertEqual(out["added"],0)
            self.assertFalse((root/"library.db").exists())


class OfflineSMLServiceTests(unittest.TestCase):
    def test_complete_vps_sml_tabs_on_loopback_and_network_ops_disabled(self):
        from fastapi.testclient import TestClient
        from scene_desktop.offline_sml_backend.server import create_app
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(Path(tmp)/"offline-sml",41337)
            with TestClient(app,base_url="http://127.0.0.1:41337",client=("127.0.0.1",31337)) as client:
                health=client.get("/__sml_desktop_health")
                self.assertEqual(health.status_code,200)
                self.assertEqual(health.json()["mode"],"offline-local")
                result=client.get("/self-media-library/")
                self.assertEqual(result.status_code,200)
                html=result.text
                for name in ["dashboard","sources","processing","library",
                             "settings","trash"]:
                    self.assertIn('id="page-'+name+'"',html)
                for name in ("app.js","local_library.js","ai_workspace.js",
                             "desktop_offline.js"):
                    url=f"/self-media-library/static/{name}"
                    self.assertEqual(client.get(url).status_code,200)
                self.assertEqual(
                    client.get("/self-media-library/api/health").json()["storage_mode"],
                    "desktop_offline"
                )
                self.assertEqual(
                    client.get("/self-media-library/api/stats").status_code,200
                )
                self.assertEqual(
                    client.get("/self-media-library/api/v1/ai/status").status_code,200
                )
                self.assertEqual(client.post(
                    "/self-media-library/api/v1/media/imports",
                    json={"source":"youtube","value":"https://youtube.com/watch?v=test"}
                ).status_code,409)
                self.assertEqual(client.post(
                    "/self-media-library/api/v1/media/proxy/save",json={}
                ).status_code,409)
                self.assertEqual(client.post(
                    "/self-media-library/api/clips/bulk/status",json={"ids":[],"status":"approved"},
                    headers={"Origin":"https://external.invalid"}
                ).status_code,403)
                self.assertFalse((Path(tmp)/"offline-sml"/"proxy_profiles.json").exists())
