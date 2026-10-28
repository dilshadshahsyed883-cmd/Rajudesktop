"""Smoke tests using local FFmpeg + temporary synthetic media."""
import json
import sys
import tempfile
import subprocess
import threading
import unittest
import array
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Draft, render, executable


class RendererTest(unittest.TestCase):
    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'Requires ffmpeg and ffprobe')
    def test_two_layer_render_with_audio(self):
        with tempfile.TemporaryDirectory() as dirname:
            d=Path(dirname);assets=d/'My Assets';assets.mkdir()
            # one clip with audio and a still image layered above
            subprocess.run([executable('ffmpeg'),'-y','-v','error',
                '-f','lavfi','-i','testsrc2=size=320x180:rate=20:duration=2.5',
                '-f','lavfi','-i','sine=frequency=660:sample_rate=44100:duration=2.5',
                '-shortest','-c:v','mpeg4','-c:a','aac',str(assets/'back video.mp4')],check=True)
            subprocess.run([executable('ffmpeg'),'-y','-v','error',
                '-f','lavfi','-i','color=red:size=200x100:rate=1','-frames:v','1',str(assets/'front.png')],check=True)
            draft=d/'My Draft';draft.mkdir()
            content={
                'name':'Rough Test','fps':20,'duration':2500000,
                'canvas_config':{'width':320,'height':180},
                'materials':{'videos':[{'id':'v1','path':str(assets/'back video.mp4'),'type':'video'},
                                      {'id':'v2','path':str(assets/'front.png'),'type':'photo'}]},
                'tracks':[
                    {'type':'video','segments':[{'material_id':'v1','target_timerange':{'start':0,'duration':2500000},
                      'source_timerange':{'start':0,'duration':2500000},'speed':1,'volume':.4}]},
                    {'type':'video','segments':[{'material_id':'v2','target_timerange':{'start':750000,'duration':1000000},
                      'source_timerange':{'start':0,'duration':1000000},'speed':1,'volume':1,
                      'clip':{'scale':{'x':.6,'y':.6},'transform':{'x':0.5,'y':0.5}}}]}
                ]}
            (draft/'draft_content.json').write_text(json.dumps(content),encoding='utf-8')
            loaded=Draft(str(draft))
            self.assertEqual(len(loaded.segments),2)
            self.assertEqual(loaded.missing,[])
            out,report=render(loaded,str(d/'rendered'),'Test 480p',0,lambda a,b:None,threading.Event())
            self.assertGreater(out.stat().st_size,1000)
            meta=json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(meta['status'],'completed')
            self.assertEqual(meta['video_segments'],1)
            self.assertEqual(meta['image_segments'],1)
            probe=subprocess.run([executable('ffprobe'),'-v','error','-show_entries','format=duration',
                                '-of','default=noprint_wrappers=1:nokey=1',str(out)],text=True,capture_output=True,check=True)
            self.assertTrue(2.2<float(probe.stdout)<2.9,probe.stdout)
            decoded=subprocess.run([executable('ffmpeg'),'-v','error','-ss','0.1','-i',str(out),
                '-t','0.2','-map','0:a:0','-f','s16le','-ac','1','-'],capture_output=True,check=True)
            samples=array.array('h');samples.frombytes(decoded.stdout)
            self.assertGreater(max(abs(value) for value in samples),100)

    def test_missing_media_refuses_render(self):
        with tempfile.TemporaryDirectory() as dirname:
            p=Path(dirname)
            (p/'draft_content.json').write_text(json.dumps({
                'name':'Missing','duration':1000000,
                'tracks':[{'type':'video','segments':[{'material_id':'x','target_timerange':{'start':0,'duration':1000000}}]}],
                'materials':{'videos':[{'id':'x','path':'missing.mp4'}]}}))
            draft=Draft(str(p))
            self.assertEqual(len(draft.missing),1)
            with self.assertRaises(ValueError):
                render(draft,str(p/'out'),'Test 480p',1,lambda a,b:None,threading.Event())

if __name__=='__main__':unittest.main()
