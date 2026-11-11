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


def wide_pe(export_count, export_name=b"BackEndExportImpl::pushTask"):
    """Realistic large PE export-name table with all names within one section."""
    raw = bytearray(synthetic_pe(export_name))
    name_table = 0x238
    string_at = 0x300 + export_count * 4
    total = string_at + len(export_name) + 10
    raw.extend(bytes(max(0, total - len(raw))))
    section = 0x98 + 0xF0
    span = len(raw) - 0x200
    struct.pack_into("<I", raw, section + 8, span)
    struct.pack_into("<I", raw, section + 16, span)
    struct.pack_into("<I", raw, 0x200 + 24, export_count)
    struct.pack_into("<I", raw, 0x200 + 32, 0x1038)
    raw[string_at:string_at + len(export_name)+1] = export_name + b"\0"
    for i in range(export_count):
        struct.pack_into("<I", raw, name_table + 4 * i, 0x1000 + string_at - 0x200)
    return bytes(raw)


class TestBridge(unittest.TestCase):
    def test_pe_export_parser(self):
        raw = synthetic_pe(b"BackEndExportImpl::pushTask")
        self.assertEqual(bridge.pe_exports(raw), ["BackEndExportImpl::pushTask"])

    def test_long_cpp_decorated_exports_do_not_abort(self):
        symbol = b"?" + b"AVeryLongMangledCppName" * 160
        raw = wide_pe(1, symbol)
        details = bridge.pe_export_details(raw)
        self.assertEqual(details["names"], [symbol.decode("ascii")])
        self.assertTrue(details["export_parse_complete"])

    def test_25001_exports_not_rejected_by_old_arbitrary_limit(self):
        raw = wide_pe(25001, b"nativeExportStart")
        details = bridge.pe_export_details(raw)
        self.assertEqual(details["declared_export_names"], 25001)
        self.assertEqual(len(details["names"]), 25001)
        self.assertEqual(details["skipped_export_names"], 0)

    def test_one_bad_name_preserves_good_exports_but_marks_partial(self):
        raw = bytearray(wide_pe(2, b"nativeExportStart"))
        # Second name is outside file-backed PE section.
        struct.pack_into("<I", raw, 0x238 + 4, 0xF0000000)
        details = bridge.pe_export_details(raw)
        self.assertEqual(details["names"], ["nativeExportStart"])
        self.assertEqual(details["skipped_export_names"], 1)
        self.assertFalse(details["export_parse_complete"])

    def test_unbounded_export_count_is_rejected(self):
        raw = bytearray(synthetic_pe())
        struct.pack_into("<I", raw, 0x200 + 24, bridge.MAX_EXPORT_NAMES + 1)
        with self.assertRaisesRegex(bridge.InvalidPE, "declares"):
            bridge.pe_export_details(raw)

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
