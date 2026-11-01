"""Version 9.7 evidence tests; never run native project exports."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from capcut_native_render_queue.core import (
    VERSION, SUPPORTED_DLLS, CAPCUT_97_ARCHIVE_SHA256,
    NativeIPC, NativeUnavailable, locate_capcut,
)


class CapCut97Tests(unittest.TestCase):
    def test_real_archived_fingerprint(self):
        self.assertEqual(VERSION, "9.7.0.4153")
        self.assertEqual(
            SUPPORTED_DLLS[VERSION],
            "8177f813b8c3ee1b58f36a2339c83691f0c7c53bac3d114cd4b66757e7f0879f",
        )
        self.assertEqual(
            CAPCUT_97_ARCHIVE_SHA256,
            "a17790e03bf7ed2ffbaa2c32bab7a1ac96a5b8b75520904e7bd42e882bc9fff4",
        )
        self.assertIn("9.6.0.4097", SUPPORTED_DLLS)

    def test_version_97_validates_only_matching_dll(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / VERSION
            folder.mkdir()
            for name in ("CapCut.exe", "lyra_cli_client.dll", "bun.exe"):
                (folder / name).write_bytes(b"fixture")
            script = folder / "Resources/common_agent/resources/lyra-cli-ipc/lyraCliIpcClient.mjs"
            script.parent.mkdir(parents=True)
            script.write_text("fixture", encoding="utf-8")
            client = NativeIPC(folder / "CapCut.exe")
            with patch("capcut_native_render_queue.core.sha256", return_value=SUPPORTED_DLLS[VERSION]):
                self.assertTrue(client.validate())
            with patch("capcut_native_render_queue.core.sha256", return_value="0" * 64):
                with self.assertRaisesRegex(NativeUnavailable, "fingerprint"):
                    client.validate()

    def test_host_project_adapter_failure_explicitly_blocks_render(self):
        with tempfile.TemporaryDirectory() as root:
            client = NativeIPC(Path(root) / VERSION / "CapCut.exe")
            raw = '{"err_category":"internal","err_msg":"unknown error: host project adapter is unavailable"}'
            result = SimpleNamespace(returncode=1, stderr="", stdout=raw)
            with patch.object(client, "validate", return_value=True), patch(
                "capcut_native_render_queue.core.subprocess.run", return_value=result
            ):
                with self.assertRaisesRegex(NativeUnavailable, "NOT registered") as caught:
                    client.list()
                self.assertIn("no ref guessing", str(caught.exception))
                self.assertIn("CapCut " + VERSION, str(caught.exception))

    def test_no_capcut_fallback_to_unsupported_version(self):
        with tempfile.TemporaryDirectory() as root:
            bad = Path(root) / "9.8.0.0"
            bad.mkdir()
            for name in ("CapCut.exe", "lyra_cli_client.dll", "bun.exe"):
                (bad / name).write_bytes(b"fixture")
            client = NativeIPC(bad / "CapCut.exe")
            with self.assertRaisesRegex(NativeUnavailable, "supported"):
                client.validate()


if __name__ == "__main__":
    unittest.main()
