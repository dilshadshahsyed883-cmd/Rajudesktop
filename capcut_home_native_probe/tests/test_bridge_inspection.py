"""Synthetic PE32+ fixture tests for read-only CapCut Home native bridge inspector."""
import mmap
from pathlib import Path
import struct
import tempfile
import unittest

from capcut_home_native_probe import bridge_inspection as bridge


def synthetic_pe(export_name=b"exportNextTask"):
    raw = bytearray(0x800)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", raw, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0)
    opt = 0x98
    struct.pack_into("<H", raw, opt, 0x20B)
    struct.pack_into("<II", raw, opt+112, 0x1000, 0x200)
    sec = opt+0xF0
    raw[sec:sec+8] = b".rdata\0\0"
    struct.pack_into("<IIII", raw, sec+8, 0x400, 0x1000, 0x400, 0x200)
    # IMAGE_EXPORT_DIRECTORY (40 bytes, PE RVA -> raw offset 0x200)
    struct.pack_into("<IIHHIIIIIII", raw, 0x200,
                     0,0,0,0,0x1070,1,1,1,0x1030,0x1038,0x1040)
    struct.pack_into("<I", raw, 0x230, 0x1180)
    struct.pack_into("<I", raw, 0x238, 0x1050)
    struct.pack_into("<H", raw, 0x240, 0)
    raw[0x250:0x250+len(export_name)+1] = export_name + b"\0"
    return bytes(raw)


class TestBridge(unittest.TestCase):
    def test_pe_export_parser(self):
        raw = synthetic_pe(b"BackEndExportImpl::pushTask")
        self.assertEqual(bridge.pe_exports(raw), ["BackEndExportImpl::pushTask"])

    def test_no_guessing_on_invalid_or_truncated(self):
        with self.assertRaises(bridge.InvalidPE):
            bridge.pe_exports(b"NotPE")
        with self.assertRaises(bridge.InvalidPE):
            bridge.pe_exports(b"MZ"+bytes(260))

    def test_qml_anchor_context_bounded(self):
        raw = b"prefix" + bridge.HOME_ANCHORS["draft_home_model"] + b"suffix"
        result = bridge.qml_anchors(raw)
        self.assertTrue(result["draft_home_model"]["found"])
        self.assertFalse(result["native_push_task"]["found"])
        self.assertTrue(len(result["draft_home_model"]["hits"][0]["context"]) <= 350)

    def test_pe_inspection_no_execution_or_file_write(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/"VECreator.dll"
            file.write_bytes(synthetic_pe(b"BackEndExportImpl::pushTask"))
            before = (file.read_bytes(), file.stat().st_mtime_ns)
            result = bridge.inspect_module(file, include_qml=True)
            self.assertIn("BackEndExportImpl::pushTask", result["target_backend_exports"])
            self.assertEqual(before, (file.read_bytes(), file.stat().st_mtime_ns))

    def test_missing_modules_report_no_native_render_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            report = bridge.inspect_install(temp)
            self.assertEqual(len(report["errors"]), 3)
            self.assertFalse(report["native_export_verified"])
            self.assertFalse(report["home_ui_patch_implemented"])
            self.assertEqual(report["bridge_level"], "INCOMPLETE_STATIC_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
