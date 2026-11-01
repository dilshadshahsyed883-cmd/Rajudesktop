"""Synthetic Qt MOC signature tests (never launch/modify CapCut)."""
import struct
import unittest

from capcut_home_native_queue.inspect_original_export_moc import (
    MOCError, parse_original_export_meta,
)


def fixture(*, access=2, kind=0, argc=0, return_type=43,
            class_name=b"ExportCompileBottomViewModel",
            method_name=b"clickBackgroudExport"):
    strings = class_name + b"\x00progressChanged\x00" + method_name + b"\x00"
    ints = [
        10, 0, 0, 0, 2, 14, 0, 28, 0, 0, 0, 0, 0, 1,
        1, 0, 26, 0, 6, 0,
        2, argc, 27, 0, access | kind, 0,
        43, return_type,
    ]
    return strings, struct.pack("<" + "I" * len(ints), *ints)


class OriginalExportMOCContractTests(unittest.TestCase):
    def test_public_void_no_args_still_does_not_prove_live_bridge(self):
        result = parse_original_export_meta(*fixture())
        self.assertEqual(result["model"], "ExportCompileBottomViewModel")
        self.assertEqual(result["method"]["name"], "clickBackgroudExport")
        self.assertEqual(result["method"]["argument_count"], 0)
        self.assertEqual(result["method"]["return_metatype_id"], 43)
        self.assertTrue(result["method"]["is_public"])
        self.assertFalse(result["live_qobject_instance_verified"])
        self.assertFalse(result["home_draft_mapping_verified"])
        self.assertFalse(result["native_queue_admission_verified"])
        self.assertFalse(result["original_engine_automatic_mp4_verified"])

    def test_private_or_protected_methods_rejected(self):
        for access in (0, 1):
            with self.subTest(access=access), self.assertRaisesRegex(
                    MOCError, "not a public"):
                parse_original_export_meta(*fixture(access=access))

    def test_signal_is_not_export_action(self):
        with self.assertRaisesRegex(MOCError, "not a public"):
            parse_original_export_meta(*fixture(kind=4))

    def test_nonzero_argument_rejected(self):
        with self.assertRaisesRegex(MOCError, "not a public"):
            parse_original_export_meta(*fixture(argc=1))

    def test_nonvoid_result_rejected(self):
        with self.assertRaisesRegex(MOCError, "not a public"):
            parse_original_export_meta(*fixture(return_type=1))

    def test_wrong_model_rejected(self):
        with self.assertRaisesRegex(MOCError, "model name absent"):
            parse_original_export_meta(*fixture(class_name=b"ForeignModel"))

    def test_recycle_bin_or_auto_upload_not_export(self):
        for method in (b"openRecycleBinWindow", b"openAutoUploadWindow"):
            with self.subTest(method=method), self.assertRaisesRegex(
                    MOCError, "exactly one"):
                parse_original_export_meta(*fixture(method_name=method))

    def test_truncated_metadata_rejected(self):
        names, metadata = fixture()
        with self.assertRaises(MOCError):
            parse_original_export_meta(names, metadata[:25])

    def test_wrong_qt_revision_rejected(self):
        names, metadata = fixture()
        changed = bytearray(metadata)
        struct.pack_into("<I", changed, 0, 9)
        with self.assertRaisesRegex(MOCError, "structure mismatch"):
            parse_original_export_meta(names, changed)


if __name__ == "__main__":
    unittest.main()
