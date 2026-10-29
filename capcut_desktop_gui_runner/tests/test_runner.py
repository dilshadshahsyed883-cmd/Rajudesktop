import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runner', ROOT / 'runner.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        patcher = patch.object(r, 'GLOBAL', self.base / 'global')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.base / 'project'
        self.project.mkdir()
        (self.project / 'draft_content.json').write_text(json.dumps(dict(duration=1000000, canvas_config=dict(width=160,height=90))))
        self.folder = self.base / 'exports'
    def test_pinned_original_bytes(self):
        p = json.loads((ROOT / 'PROVENANCE.json').read_text())
        for f, h in p['files'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'upstream' / f).read_bytes()).hexdigest(), h, f)
    def test_prepare_read_only_and_unique(self):
        before = r.snapshot(self.project)
        job = r.prepare(self.folder, self.project)
        self.assertEqual(before, r.snapshot(self.project))
        self.assertFalse(Path(job['output']).exists())
        with self.assertRaises(ValueError):
            r.prepare(self.folder, self.project)
    def test_one_job_across_batch_folders(self):
        r.prepare(self.folder,self.project)
        with self.assertRaisesRegex(ValueError, 'global'):
            r.prepare(self.base / 'another-folder',self.project)
    def test_no_export_inside_source(self):
        with self.assertRaises(ValueError):
            r.prepare(self.project / 'outputs', self.project)
    def test_ambiguous_or_missing_project(self):
        with self.assertRaises(ValueError):
            r.prepare(self.folder, self.base)
    def test_unaccepted_version_blocks(self):
        with patch.object(r,'version_info',return_value={'running':['9.6.0.4097']}):
            with self.assertRaises(RuntimeError): r.guard(None)
    def test_locked_desktop_blocks(self):
        with patch.object(r,'version_info',return_value={'running':[r.BASELINE]}), patch.object(r,'active_desktop',return_value=False):
            with self.assertRaises(RuntimeError): r.guard(None)
    def test_requires_completion_observation(self):
        with self.assertRaises(ValueError): r.verify(self.folder,Path('ffmpeg'),False)
    def test_source_change_stops_batch(self):
        r.prepare(self.folder,self.project)
        (self.project / 'draft_content.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'): r.verify(self.folder,Path('ffmpeg'),True,0)
    def test_os_lock(self):
        with r.batch_lock(self.folder):
            with self.assertRaises(OSError):
                with r.batch_lock(self.folder): pass
    def test_actual_media_verification_and_no_overwrite(self):
        ff = shutil.which('ffmpeg')
        if not ff: self.skipTest('No ffmpeg on test host; CI smoke is not CapCut export proof')
        job = r.prepare(self.folder,self.project)
        path = Path(job['output'])
        subprocess.run([ff,'-v','error','-f','lavfi','-i','color=size=160x90:rate=30:duration=1','-f','lavfi','-i','sine=frequency=500:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(path)],check=True)
        before = path.read_bytes()
        verified = r.verify(self.folder,Path(ff),True,0)
        self.assertEqual(verified['status'],'VERIFIED')
        with self.assertRaisesRegex(ValueError,'Already verified'): r.verify(self.folder,Path(ff),True,0)
        self.assertEqual(path.read_bytes(),before)
        second = r.prepare(self.folder,self.project)
        self.assertNotEqual(second['output'],job['output'])
        self.assertTrue(path.exists())
        with self.assertRaisesRegex(ValueError,'mismatch'):
            r.inspect_media(path,ff,dict(duration=42,width=160,height=90,codec='h264',audio=True))
        with self.assertRaisesRegex(ValueError,'mismatch'):
            r.inspect_media(path,ff,dict(duration=1,width=1920,height=1080,codec='h264',audio=True))
    def test_missing_audio_rejected(self):
        ff=shutil.which('ffmpeg')
        if not ff: self.skipTest('No ffmpeg')
        path=self.base/'silent.mp4'
        subprocess.run([ff,'-v','error','-f','lavfi','-i','color=size=160x90:rate=30:duration=1','-c:v','libx264',str(path)],check=True)
        with self.assertRaisesRegex(ValueError,'audio'):
            r.inspect_media(path,ff,dict(duration=1,width=160,height=90,codec='h264',audio=True))
    def test_truncated_media_rejected(self):
        path=self.base/'bad.mp4'
        path.write_bytes(b'not a video')
        ff=shutil.which('ffmpeg')
        if not ff: self.skipTest('No ffmpeg')
        with self.assertRaises(ValueError):
            r.inspect_media(path,ff,dict(duration=1,width=160,height=90,codec='h264',audio=True))

if __name__ == '__main__': unittest.main()
