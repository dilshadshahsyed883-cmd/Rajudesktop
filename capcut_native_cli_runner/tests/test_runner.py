import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner

DOC = {'id': 'timeline', 'duration': 1_000_000, 'fps': 30, 'canvas_config': {'width': 1920, 'height': 1080}}
PROBE = {'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2', 'duration': '1.0'},
         'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080},
                     {'codec_type': 'audio', 'sample_rate': '48000', 'channels': 2}]}


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.original = self.root / 'original'
        self.duplicate = self.root / 'duplicate'
        for path, identity in [(self.original, 'original-id'), (self.duplicate, 'duplicate-id')]:
            path.mkdir()
            (path / 'draft_meta_info.json').write_text(json.dumps({'draft_id': identity}))
        (self.duplicate / 'Timelines/timeline').mkdir(parents=True)
        (self.duplicate / 'Timelines/project.json').write_text(json.dumps({'timelines': [{'id': 'timeline'}]}))
        (self.duplicate / 'Timelines/timeline/draft_content.json').write_text(json.dumps(DOC))

    def tearDown(self):
        self.tmp.cleanup()

    def pair(self):
        return runner.project_pair(self.original, self.duplicate, 'timeline')

    def test_distinct_duplicate_allowed(self):
        self.assertEqual(self.pair()[2], DOC)

    def test_same_project_refused(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            runner.project_pair(self.original, self.original, 'timeline')

    def test_nested_project_refused(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            runner.project_pair(self.original, self.original / 'copy', 'timeline')

    def test_raw_copy_identity_refused(self):
        (self.duplicate / 'draft_meta_info.json').write_text(json.dumps({'draft_id': 'original-id'}))
        with self.assertRaisesRegex(ValueError, 'distinct project ID'):
            self.pair()

    def test_embedded_original_path_refused(self):
        (self.duplicate / 'references.json').write_text(json.dumps({'media': str(self.original / 'video.mp4')}))
        with self.assertRaisesRegex(ValueError, 'references original'):
            self.pair()

    def test_unknown_timeline_refused(self):
        with self.assertRaisesRegex(ValueError, 'timeline ID'):
            runner.project_pair(self.original, self.duplicate, 'absent')

    def test_symbolic_link_refused(self):
        try:
            (self.duplicate / 'linked').symlink_to(self.original, target_is_directory=True)
        except OSError:
            self.skipTest('Windows runner lacks symlink privilege')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.pair()

    def test_snapshot_detects_changed_added_removed_files(self):
        before = runner.snapshot(self.original)
        (self.original / 'new.txt').write_text('new')
        self.assertNotEqual(before, runner.snapshot(self.original))
        (self.original / 'new.txt').unlink()
        self.assertEqual(before, runner.snapshot(self.original))
        (self.original / 'draft_meta_info.json').unlink()
        self.assertNotEqual(before, runner.snapshot(self.original))

    def test_missing_capcut_before_version_read(self):
        with patch.object(runner, 'file_version') as version:
            with self.assertRaisesRegex(ValueError, 'missing'):
                runner.check_build(self.root)
            version.assert_not_called()

    def test_unsupported_version_before_worker_import_or_attach(self):
        (self.root / 'CapCut.exe').write_bytes(b'fake')
        with patch.object(runner, 'file_version', return_value='9.6.0.4097'):
            with self.assertRaisesRegex(ValueError, 'Unsupported CapCut 9.6.0.4097'):
                runner.check_build(self.root)

    def test_pinned_version_wrong_module_refused(self):
        (self.root / 'CapCut.exe').write_bytes(b'fake')
        with patch.object(runner, 'file_version', return_value=runner.SUPPORTED):
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                runner.check_build(self.root)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows version resource test')
    def test_real_windows_version_resource(self):
        actual = runner.file_version(Path(sys.executable))
        self.assertEqual(len(actual.split('.')), 4)
        self.assertTrue(actual.startswith(str(sys.version_info.major) + '.' + str(sys.version_info.minor) + '.'))

    def test_vendored_sources_unchanged(self):
        runner.verify_sources()

    def test_source_tampering_rejected(self):
        with patch.object(runner, 'digest', return_value='wrong'):
            with self.assertRaisesRegex(ValueError, 'integrity'):
                runner.verify_sources()

    def test_export_unsupported_does_not_call_adapter(self):
        with patch.object(runner, 'select_build', side_effect=ValueError('Unsupported')), patch.object(runner, 'adapter') as adapter:
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                runner.export({})
            adapter.assert_not_called()


class ProbeValidation(unittest.TestCase):
    def test_valid_audio_video(self):
        self.assertEqual(runner.verify_probe(PROBE, DOC, True)['audioStreams'], 1)

    def test_missing_audio_fails(self):
        p = copy.deepcopy(PROBE); p['streams'] = p['streams'][:1]
        with self.assertRaisesRegex(ValueError, 'audio stream required'):
            runner.verify_probe(p, DOC, True)

    def test_explicit_silent_project(self):
        p = copy.deepcopy(PROBE); p['streams'] = p['streams'][:1]
        self.assertEqual(runner.verify_probe(p, DOC, False)['audioStreams'], 0)

    def test_resolution_fails(self):
        p = copy.deepcopy(PROBE); p['streams'][0]['width'] = 1280
        with self.assertRaisesRegex(ValueError, 'resolution'):
            runner.verify_probe(p, DOC, True)

    def test_duration_and_nan_fail(self):
        for duration in ['2', 'NaN', 'Infinity']:
            p = copy.deepcopy(PROBE); p['format']['duration'] = duration
            with self.assertRaisesRegex(ValueError, 'duration'):
                runner.verify_probe(p, DOC, True)

    def test_wrong_codec_container_and_no_video(self):
        for mutation in ['codec', 'container', 'missing']:
            p = copy.deepcopy(PROBE)
            if mutation == 'codec': p['streams'][0]['codec_name'] = 'mpeg4'
            if mutation == 'container': p['format']['format_name'] = 'matroska'
            if mutation == 'missing': p['streams'] = p['streams'][1:]
            with self.assertRaisesRegex(ValueError, 'H.264 MP4'):
                runner.verify_probe(p, DOC, True)

    def test_invalid_audio_metadata(self):
        p = copy.deepcopy(PROBE); p['streams'][1]['channels'] = 0
        with self.assertRaisesRegex(ValueError, 'audio metadata'):
            runner.verify_probe(p, DOC, True)


class Publication(unittest.TestCase):
    setUp = Guards.setUp
    tearDown = Guards.tearDown
    def run_export(self, mode='valid'):
        package = self.root / 'package'; package.mkdir()
        tools = package / 'tools/ffmpeg/bin'; tools.mkdir(parents=True)
        for f in ['ffmpeg.exe', 'ffprobe.exe']: (tools / f).touch()
        output = self.root / 'output.mp4'
        config = {'pid': 123, 'original_project': str(self.original), 'duplicate_project': str(self.duplicate),
                  'timeline_id': 'timeline', 'output': str(output)}
        if mode == 'existing': output.write_bytes(b'KEEP')
        def adapter(build, args, logdir, timeout):
            Path(args[-1]).write_bytes(b'fake-test-video')
            if mode == 'changed': (self.original / 'changed.txt').write_text('external mutation')
            return {'result': {'fullDecodeVerified': mode != 'unverified', 'timelineUnchanged': True,
                               'native': {'nativeCompletionVerified': mode != 'nonative'}}}
        p = copy.deepcopy(PROBE)
        if mode == 'noaudio': p['streams'] = p['streams'][:1]
        process = subprocess.CompletedProcess([], 0, json.dumps(p), '')
        with patch.object(runner, 'ROOT', package), patch.object(runner, 'verify_sources'), \
             patch.object(runner, 'select_build', return_value={'directory': str(self.root)}), \
             patch.object(runner, 'adapter', side_effect=adapter) as native, patch.object(runner.subprocess, 'run', return_value=process):
            if mode == 'valid':
                result = runner.export(config)
                self.assertEqual(result['status'], 'PASS'); self.assertTrue(output.exists())
            else:
                with self.assertRaises((ValueError, FileExistsError)):
                    runner.export(config)
                if mode == 'existing':
                    self.assertEqual(output.read_bytes(), b'KEEP'); native.assert_not_called()
                else:
                    self.assertFalse(output.exists())
                    result = runner.read(next((package / 'logs').glob('*/result.json')))
                    self.assertEqual(result['status'], 'FAIL')
        return output

    def test_verified_publication(self): self.run_export()
    def test_no_overwrite(self): self.run_export('existing')
    def test_missing_decode_withholds_output(self): self.run_export('unverified')
    def test_missing_native_completion_withholds_output(self): self.run_export('nonative')
    def test_missing_audio_withholds_output(self): self.run_export('noaudio')
    def test_original_change_withholds_output(self): self.run_export('changed')


if __name__ == '__main__':
    unittest.main()
