"""Exercise the actual queue worker without creating a Tk window."""
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import App


class WorkerTests(unittest.TestCase):
    def test_fifo_continues_after_a_blocked_or_failed_project(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=[]
            for name in ('Missing','Fails','Works'):
                folder=Path(directory)/name;folder.mkdir()
                raw={'name':name,'duration':1000000,'canvas_config':{'width':320,'height':180},
                     'materials':{'texts':[{'id':'t','content':'hello'}]},
                     'tracks':[{'type':'text','segments':[{'material_id':'t','target_timerange':{'start':0,'duration':1000000}}]}]}
                if name=='Missing':
                    raw['materials']['videos']=[{'id':'v','path':'nonexistent.mp4'}]
                    raw['tracks'].append({'type':'video','segments':[{'material_id':'v','target_timerange':{'start':0,'duration':1000000}}]})
                path=folder/'draft_content.json';path.write_text(json.dumps(raw));paths.append((len(paths),str(path)))
            worker=SimpleNamespace(signal=queue.Queue(),cancel=threading.Event())
            calls=[]
            def fake_render(draft,*args,**kwargs):
                calls.append(draft.name)
                if draft.name=='Fails':raise RuntimeError('intentional test failure')
                return Path(directory)/'result.mp4',Path(directory)/'result.report.json'
            with patch('app.render',side_effect=fake_render):
                App.worker(worker,paths,'',str(Path(directory)/'out'),'Original',60,False)
            events=[]
            while not worker.signal.empty():events.append(worker.signal.get())
            self.assertEqual(calls,['Fails','Works'])
            states=[(e[1],e[2]) for e in events if e[0]=='state']
            self.assertIn((0,'Blocked: Missing media'),states)
            self.assertIn((1,'Failed'),states)
            self.assertIn((2,'Verified - limitations'),states)
            self.assertEqual(events[-1],('finished',))
            self.assertEqual(len(list((Path(directory)/'out').glob('*FAILED.report.json'))),1)


if __name__=='__main__':unittest.main()
