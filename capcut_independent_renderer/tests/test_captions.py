import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from captions import parse_caption, literal_text, write_ass
from engine import Draft, render, executable, chunk_times, safe_name
from state import save_state, load_state, completed_for, InstanceLock
from engine import run_command, has_audio
import time


def caption_draft(folder, content, duration=3, fps=30):
    path = Path(folder)/'draft_content.json'
    data = {'name':'Caption Test','duration':int(duration*1e6),'fps':fps,
            'canvas_config':{'width':320,'height':180},
            'materials':{'texts':[{'id':'t','content':content}]},
            'tracks':[{'type':'text','segments':[
                {'id':'caption','material_id':'t','target_timerange':{'start':500000,'duration':1000000}}]}]}
    path.write_text(json.dumps(data), encoding='utf-8')
    return Draft(str(path))


class CaptionTests(unittest.TestCase):
    def test_failed_audio_probe_does_not_silently_mute_source(self):
        failure=subprocess.CompletedProcess([],1,stdout='',stderr='unreadable media')
        with patch('engine.subprocess.run',return_value=failure):
            with self.assertRaisesRegex(RuntimeError,'inspect source audio'):
                has_audio('source.mp4','ffprobe',{},threading.Event())

    def test_running_process_is_cancelled(self):
        cancel=threading.Event()
        timer=threading.Timer(.25,cancel.set)
        timer.start()
        began=time.monotonic()
        try:
            with self.assertRaises(InterruptedError):
                run_command([sys.executable,'-c','import time; time.sleep(30)'],None,cancel)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic()-began,5)
    def test_rich_plain_unicode_and_unsafe_text(self):
        rich=json.dumps({'text':'Hello\nاردو {\\p1}','styles':[{
            'size':8,'fill':{'content':{'solid':{'color':[1,0,0]}}},'bold':True}]})
        c,warnings=parse_caption({'content':rich},{},0,1,2)
        self.assertIn('اردو',c.text)
        self.assertEqual(c.color,'&H000000FF')
        self.assertTrue(c.bold)
        self.assertEqual(c.size,8)
        escaped=literal_text(c.text)
        self.assertNotIn('{',escaped)
        self.assertNotIn(r'\p1',escaped)
        self.assertIn(r'\N',escaped)
        c,_=parse_caption({'content':'[INTRO] {literal}'},{},0,1,0)
        self.assertEqual(c.text,'[INTRO] {literal}')
        self.assertEqual(safe_name('CON'),'_CON')

    def test_malformed_text_blocks_export(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'{"broken":')
            self.assertEqual(len(draft.caption_errors),1)
            self.assertEqual(draft.summary()['render_readiness'],'BLOCKED')
            with self.assertRaisesRegex(ValueError,'captions could not be parsed'):
                render(draft,folder,'Original',0,lambda *_:None,threading.Event())

    def test_project_and_export_caption_counts_are_different(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'Later caption')
            count=write_ass(Path(folder)/'test.ass',draft.captions,320,180,.4)
            self.assertEqual(count,0)
            self.assertEqual(draft.summary()['text_segments_parsed'],1)

    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'FFmpeg required')
    def test_burned_caption_present_only_in_its_timerange(self):
        with tempfile.TemporaryDirectory(prefix="Caption O'Brien, [test] ") as folder:
            draft=caption_draft(folder,json.dumps({'text':'CAPTION TEST','styles':[{'size':9}]}))
            original=draft.path.read_bytes()
            out,report=render(draft,str(Path(folder)/'out'),'Original',0,lambda *_:None,threading.Event())
            self.assertEqual(draft.path.read_bytes(),original)
            meta=json.loads(report.read_text())
            self.assertEqual(meta['text_segments_in_export'],1)
            self.assertEqual(meta['mp4_verification']['status'],'metadata_and_decode_pass')
            self.assertEqual(meta['mp4_verification']['audio_streams'],1)
            self.assertTrue(out.with_suffix('.captions.ass').exists())
            self.assertTrue(out.with_suffix('.summary.txt').exists())
            def lit_pixels(at):
                result=subprocess.run([executable('ffmpeg'),'-v','error','-ss',str(at),'-i',str(out),
                    '-frames:v','1','-vf','format=gray','-f','rawvideo','-'],capture_output=True,check=True)
                return sum(value>100 for value in result.stdout)
            self.assertLess(lit_pixels(.2),10)
            self.assertGreater(lit_pixels(.8),100)
            self.assertLess(lit_pixels(2),10)

    def test_frame_grid_does_not_drop_short_intervals(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'Text',duration=61,fps=60)
            chunks=chunk_times(draft,draft.duration)
            self.assertEqual(chunks,[(0,60),(60,61)])
            self.assertAlmostEqual(sum(b-a for a,b in chunks),61)

    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'FFmpeg required')
    def test_caption_survives_media_chunk_boundary_and_fade(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'CROSS BOUNDARY')
            with patch('engine.chunk_times',return_value=[(0,1),(1,2),(2,3)]):
                out,report=render(draft,folder,'Original',0,lambda *_:None,threading.Event(),caption_fade=True)
            data=subprocess.run([executable('ffmpeg'),'-v','error','-ss','1.2','-i',str(out),
                '-frames:v','1','-vf','format=gray','-f','rawvideo','-'],capture_output=True,check=True).stdout
            self.assertGreater(sum(x>100 for x in data),100)
            self.assertTrue(json.loads(report.read_text())['caption_fade_applied'])

    def test_404_captions_are_parsed_without_losing_unsupported_warnings(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'first',duration=1109.867)
            data=draft.raw
            data['materials']['material_animations']=[{'id':f'animation_{i}','animations':[{'name':'unknown'}]} for i in range(404)]
            data['materials']['texts']=[{'id':str(i),'content':json.dumps({'text':f'Caption {i}'})} for i in range(404)]
            data['tracks'][0]['segments']=[{'material_id':str(i),'target_timerange':{'start':i*2500000,'duration':2000000}} for i in range(404)]
            draft.path.write_text(json.dumps(data))
            draft=Draft(str(draft.path))
            summary=draft.summary()
            self.assertEqual(summary['text_segments_parsed'],404)
            self.assertEqual(summary['text_segments_unparsed'],0)
            self.assertTrue(any('material_animations (404)' in w for w in summary['warnings']))
            self.assertFalse(any('Unsupported track type text' in w for w in summary['warnings']))

    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'FFmpeg required')
    def test_cancellation_leaves_no_mp4_or_temporary_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'Cancel me')
            cancel=threading.Event()
            def progress(*_): cancel.set()
            with self.assertRaises(InterruptedError):
                render(draft,folder,'Original',0,progress,cancel)
            self.assertEqual(list(Path(folder).glob('*.mp4')),[])
            self.assertEqual(list(Path(folder).glob('capcut_render_*')),[])

    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'FFmpeg required')
    def test_failure_does_not_publish_mp4(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=caption_draft(folder,'Fail safely')
            with patch('engine.verify_mp4',side_effect=RuntimeError('bad output')):
                with self.assertRaisesRegex(RuntimeError,'bad output'):
                    render(draft,folder,'Original',0,lambda *_:None,threading.Event())
            self.assertEqual(list(Path(folder).glob('*.mp4')),[])
            self.assertEqual(list(Path(folder).glob('capcut_render_*')),[])


class QueueTests(unittest.TestCase):
    def test_windows_locked_byte_read_releases_second_handle(self):
        stream=MagicMock()
        stream.read.side_effect=PermissionError('byte locked by first instance')
        with patch('state.open',return_value=stream,create=True):
            with self.assertRaisesRegex(RuntimeError,'already running'):
                InstanceLock('instance.lock')
        stream.close.assert_called_once()

    def test_atomic_restore_interrupted_and_corrupt(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'queue.json'
            data={'items':[{'path':'draft.json','name':'Project','length':2,'media':'1 video','status':'Rendering'}]}
            save_state(path,data)
            restored,warning=load_state(path)
            self.assertFalse(warning)
            self.assertEqual(restored['items'][0]['status'],'Interrupted - retry')
            self.assertFalse(path.with_suffix('.tmp').exists())
            path.write_text('{invalid')
            restored,warning=load_state(path)
            self.assertEqual(restored,{})
            self.assertTrue(warning)
            self.assertEqual(len(list(Path(folder).glob('queue_corrupt_*.json'))),1)

    def test_full_export_not_skipped_after_short_test(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output.mp4';output.touch()
            source=Path(folder)/'draft.json';source.write_text('{}')
            item={'status':'Verified - limitations','last_output':str(output),'last_settings':{'seconds':60},
                  'path':str(source),'last_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            self.assertTrue(completed_for(item,{'seconds':60}))
            self.assertFalse(completed_for(item,{'seconds':0}))
            source.write_text('{"edited":true}')
            self.assertFalse(completed_for(item,{'seconds':60}))
            output.unlink()
            self.assertFalse(completed_for(item,{'seconds':60}))

    def test_single_instance_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'app.lock'
            guard=InstanceLock(path)
            try:
                with self.assertRaises(RuntimeError): InstanceLock(path)
            finally:
                guard.close()
            guard=InstanceLock(path);guard.close()


if __name__=='__main__':unittest.main()
