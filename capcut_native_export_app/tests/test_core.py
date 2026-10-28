import tempfile
import unittest
from pathlib import Path
from capcut_native_export.core import (
    WindowInfo,GuardError,FileObserver,click_location,ensure_export,
    ensure_single_editor,export_project,is_editor,is_export,
    mp4_has_metadata,parse_audit_window_dict,target_file,
)

class NativeControlTests(unittest.TestCase):
    def editor(self):
        return WindowInfo(132706,10996,"CapCut","MainWindow_QMLTYPE_544",0,0,1920,1040)
    def dialog(self):
        return WindowInfo(198506,10996,"Export-1028","ExportWindow_QMLTYPE_1594",600,189,1320,852)
    def test_audit_window_identity(self):
        editor,dialog=self.editor(),self.dialog()
        self.assertTrue(is_editor(editor))
        self.assertTrue(is_export(dialog))
        self.assertEqual(export_project(dialog.title),"1028")
        self.assertEqual(ensure_single_editor([editor,dialog]),editor)
        self.assertEqual(ensure_export([editor,dialog],editor,"1028"),dialog)
    def test_project_and_pid_guards(self):
        editor,dialog=self.editor(),self.dialog()
        with self.assertRaisesRegex(GuardError,"mismatch"):
            ensure_export([editor,dialog],editor,"WRONG")
        foreign=WindowInfo(dialog.hwnd,99,dialog.title,dialog.class_name,*dialog.rect)
        with self.assertRaisesRegex(GuardError,"found 0"):
            ensure_export([editor,foreign],editor,"1028")
        with self.assertRaises(GuardError):
            ensure_single_editor([editor,editor])
    def test_relative_point_and_audit_row(self):
        self.assertEqual(click_location(self.dialog(),.817,.959),(1188,824))
        row={"window":198506,"name":"Export-1028","class_name":"ExportWindow_QMLTYPE_1594","bounds":"600,189,720,663"}
        self.assertEqual(parse_audit_window_dict(row).rect,self.dialog().rect)
        with self.assertRaises(ValueError):
            click_location(self.dialog(),1.1,.5)
    def test_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=target_file(tmp,"1028")
            target.write_bytes(b"already exported")
            with self.assertRaises(GuardError):
                target_file(tmp,"1028")
            with self.assertRaises(GuardError):
                target_file(tmp,"../invalid")
    def test_mp4_metadata_and_stability(self):
        def box(code,payload):
            return (8+len(payload)).to_bytes(4,"big")+code+payload
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"1028.mp4"
            obs=FileObserver(path,min_bytes=16,stable_checks=2)
            self.assertFalse(obs.poll()[0])
            path.write_bytes(box(b"ftyp",b"isom0000")+box(b"mdat",b"frame")+box(b"moov",b"metadata"))
            self.assertTrue(mp4_has_metadata(path))
            self.assertFalse(obs.poll()[0])
            self.assertFalse(obs.poll()[0])
            self.assertTrue(obs.poll()[0])
            path.write_bytes(box(b"ftyp",b"isom0000")+box(b"mdat",b"frame"))
            self.assertFalse(mp4_has_metadata(path))
            self.assertFalse(obs.poll()[0])

if __name__=="__main__":
    unittest.main()
