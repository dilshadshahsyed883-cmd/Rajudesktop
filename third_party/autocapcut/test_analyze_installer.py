"""Self-contained synthetic tests; third-party binaries are NOT needed."""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from analyze_installer import inspect


class StaticAuditTests(unittest.TestCase):
    def test_pe32_nsis_marker_and_checksum(self):
        blob = bytearray(8192)
        blob[:2] = b"MZ"
        struct.pack_into("<I", blob, 0x3C, 0x80)
        blob[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HHIIIHH", blob, 0x84, 0x14C, 1, 0, 0, 0, 224, 0)
        struct.pack_into("<H", blob, 0x98, 0x10B)
        struct.pack_into("<H", blob, 0x98 + 68, 2)
        section = 0x98 + 224
        struct.pack_into("<8sIIIIIIHHI", blob, section, b".text", 256, 4096, 256, 512, 0, 0, 0, 0, 0)
        blob[3000:3013] = b"Nullsoft NSIS"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.exe"
            p.write_bytes(blob)
            report = inspect(p)
            self.assertEqual(report["sha256"], hashlib.sha256(blob).hexdigest())
            self.assertEqual(report["possible_installer"], "NSIS")
            self.assertEqual(report["sections"], [".text"])
            self.assertFalse(report["signature_verified"])
            self.assertEqual(report["possible_appended_payload_bytes"], len(blob) - 768)

    def test_non_pe_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "text.exe"
            p.write_bytes(b"Not an executable" * 20)
            with self.assertRaises(ValueError):
                inspect(p)

    def test_truncated_pe_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "short.exe"
            b = bytearray(128)
            b[:2] = b"MZ"
            struct.pack_into("<I", b, 0x3C, 120)
            p.write_bytes(b)
            with self.assertRaises(ValueError):
                inspect(p)


if __name__ == "__main__":
    unittest.main()
