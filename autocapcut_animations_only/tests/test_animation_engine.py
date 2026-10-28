import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from animation_engine import (image_clips,harvest_animations,make_plan,apply_animation,stable_media_fingerprint,
                              save,load_project,list_projects)


def fixture():
    a={'id':'a1','type':'sticker_animation','multi_language_current':'none','animations':[{'id':'native1','type':'group','resource_id':'native1','third_resource_id':'native1','start':0,'duration':4000000,'name':'Pendulum 1','category_name':'Trending-3','path':'/synthetic/effect','request_id':'old-request'}]}
    vs=[{'id':'p1','type':'photo','material_name':'first.jpg'},{'id':'v1','type':'video','material_name':'video.mp4'}, {'id':'p2','type':'photo','material_name':'second.png'}]
    return {'duration':12000000,'materials':{'videos':vs,'material_animations':[a], 'transitions':[{'id':'trans1','effect_id':'t'}]},
            'tracks':[{'id':'lower','type':'video','segments':[{'id':'s1','material_id':'p1','target_timerange':{'start':0,'duration':4000000},'source_timerange':{'start':99,'duration':4000000},'extra_material_refs':['a1','trans1'],'keyframe_refs':['keep1']}, {'id':'s2','material_id':'v1','target_timerange':{'start':4000000,'duration':4000000},'extra_material_refs':['trans1'],'volume':0.33}, {'id':'s3','material_id':'p2','target_timerange':{'start':8000000,'duration':4000000},'extra_material_refs':[],'keyframe_refs':['keep3']}]}, {'id':'audio','type':'audio','segments':[{'id':'music','volume':0.4}]}]}


def catalog():
    return [{'effect_id':'native1','name':'Pendulum 1','category':'Trending-3','duration_us':4000000,'path':'/synthetic/effect','template':copy.deepcopy(fixture()['materials']['material_animations'][0])}]

class CoreTests(unittest.TestCase):
    def test_image_only_target_inventory(self):
        clips=image_clips(fixture())
        self.assertEqual([c['name'] for c in clips], ['first.jpg','second.png'])
        self.assertEqual([c['segment_index'] for c in clips],[0,2])

    @patch('animation_engine.resource_is_available',return_value=True)
    def test_apply_never_modifies_video_or_timing_or_transitions(self,unused):
        before=fixture()
        rows,_=make_plan(before,catalog(),[(0,2)],'native1')
        self.assertEqual(rows[0]['status'],'Will Apply')
        after,result=apply_animation(before,catalog(),'native1',rows)
        self.assertEqual(result['changed'],1)
        self.assertEqual(before['tracks'][0]['segments'][1], after['tracks'][0]['segments'][1])
        self.assertEqual(before['tracks'][1],after['tracks'][1])
        self.assertEqual(before['materials']['transitions'],after['materials']['transitions'])
        self.assertEqual(stable_media_fingerprint(before),stable_media_fingerprint(after))
        self.assertEqual(len(after['materials']['material_animations']),2)
        self.assertIn('trans1', after['tracks'][0]['segments'][0]['extra_material_refs'])
        self.assertEqual(after['tracks'][0]['segments'][2]['keyframe_refs'],['keep3'])

    @patch('animation_engine.resource_is_available',return_value=True)
    def test_idempotency(self,unused):
        src=fixture();rows,_=make_plan(src,catalog(),[(0,2)],'native1')
        out,_=apply_animation(src,catalog(),'native1',rows)
        out2,res=apply_animation(out,catalog(),'native1',rows)
        self.assertEqual(out,out2)
        self.assertEqual(res['already_matching'],1)
        self.assertEqual(res['changed'],0)

    @patch('animation_engine.resource_is_available',return_value=True)
    def test_video_target_rejected(self,unused):
        rows,_=make_plan(fixture(),catalog(),[(0,1)],'native1')
        self.assertEqual(rows[0]['status'],'Skipped')
        self.assertEqual(apply_animation(fixture(),catalog(),'native1',rows)[1]['changed'],0)

    @patch('animation_engine.resource_is_available',return_value=True)
    def test_short_photo_retimed_to_image(self,unused):
        d=fixture();d['tracks'][0]['segments'][2]['target_timerange']['duration']=2000000
        rows,_=make_plan(d,catalog(),[(0,2)],'native1')
        self.assertEqual(rows[0]['status'],'Will Apply')
        self.assertEqual(rows[0]['applied_duration_us'],2_000_000)
        out,result=apply_animation(d,catalog(),'native1',rows)
        self.assertEqual(result['changed'],1)
        self.assertEqual(out['materials']['material_animations'][-1]['animations'][0]['duration'],2_000_000)
        self.assertEqual(out['tracks'][0]['segments'][2]['target_timerange']['duration'],2_000_000)

    def test_missing_effect_skipped(self):
        rows,_=make_plan(fixture(),catalog(),[(0,2)],'native1')
        self.assertEqual(rows[0]['status'],'Missing')

    def test_scan_requires_used_on_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'Test';p.mkdir()
            d=fixture();(p/'draft_content.json').write_text(json.dumps(d))
            catalog_entries=harvest_animations(root)
            self.assertEqual(len(catalog_entries),1)
            self.assertEqual(catalog_entries[0]['name'],'Pendulum 1')
            self.assertEqual(len(list_projects(root)),1)
            d['tracks'][0]['segments'][0]['extra_material_refs'].remove('a1')
            (p/'draft_content.json').write_text(json.dumps(d))
            self.assertEqual(harvest_animations(root),[])

    def test_preserves_unrelated_native_animation_material(self):
        src=fixture();src['materials']['material_animations'].append({'id':'in1','type':'sticker_animation','animations':[{'name':'Fade In','type':'in','id':'f1'}]})
        src['tracks'][0]['segments'][2]['extra_material_refs'].append('in1')
        after,_=apply_animation(src,catalog(),'native1',[{**image_clips(src)[1],'status':'Will Apply'}])
        self.assertIn('in1',after['tracks'][0]['segments'][2]['extra_material_refs'])
        self.assertEqual(stable_media_fingerprint(src),stable_media_fingerprint(after))

class NewFeatureTests(unittest.TestCase):
    @patch('animation_engine.resource_is_available',return_value=True)
    def test_short_animations_fit_1_7_2_5_3_6_4_seconds(self,unused):
        for duration in (1_700_000,2_500_000,3_600_000,4_000_000):
            d=fixture()
            d['tracks'][0]['segments'][2]['target_timerange']['duration']=duration
            entries=catalog();entries[0]['duration_us']=5_000_000
            entries[0]['template']['animations'][0]['duration']=5_000_000
            rows,_=make_plan(d,entries,[(0,2)],'native1')
            self.assertEqual(rows[0]['applied_duration_us'],duration)
            self.assertEqual(rows[0]['status'],'Will Apply')
            out,res=apply_animation(d,entries,'native1',rows)
            self.assertEqual(out['materials']['material_animations'][-1]['animations'][0]['duration'],duration)
            self.assertEqual(out['tracks'][0]['segments'][2]['target_timerange']['duration'],duration)
            self.assertEqual(out['tracks'][0]['segments'][1],d['tracks'][0]['segments'][1])
            self.assertEqual(stable_media_fingerprint(out),stable_media_fingerprint(d))

    @patch('animation_engine.resource_is_available',return_value=True)
    def test_random_all_available_no_back_to_back_when_multiple(self,unused):
        from animation_engine import make_plan
        d=fixture()
        # Add 7 more images to same track and a second independent visual layer.
        for i in range(7):
            mid=f'extra-photo-{i}'
            d['materials']['videos'].append({'id':mid,'type':'photo','material_name':mid+'.png'})
            d['tracks'][0]['segments'].append({'id':f'new{i}','material_id':mid,'target_timerange':{'start':12000000+i*2100000,'duration':2100000},'extra_material_refs':[]})
        d['tracks'].append({'type':'video','id':'upper','segments':[{'id':'upper-photo','material_id':'p2','target_timerange':{'start':0,'duration':1750000},'extra_material_refs':[]}]})
        entries=catalog()
        for i in range(2):
            entry=copy.deepcopy(entries[0]);entry['effect_id']=f'new{i}';entry['name']=f'Other {i}'
            entry['template']['animations'][0]['resource_id']=f'new{i}'
            entry['template']['animations'][0]['id']=f'new{i}'
            entries.append(entry)
        keys=[(x['track_index'],x['segment_index']) for x in image_clips(d)]
        rows,_=make_plan(d,entries,keys,mode='random',seed=12345)
        self.assertEqual(len(rows),len(keys))
        self.assertTrue(all(r['status']=='Will Apply' for r in rows))
        self.assertTrue(all(a['effect_id'] != b['effect_id'] for a,b in zip(rows,rows[1:])))
        self.assertEqual(rows,make_plan(d,entries,keys,mode='random',seed=12345)[0])
        out,result=apply_animation(d,entries,None,rows)
        self.assertEqual(result['changed'],len(keys))
        self.assertEqual(stable_media_fingerprint(d),stable_media_fingerprint(out))
        self.assertEqual(d['tracks'][0]['segments'][1],out['tracks'][0]['segments'][1])
        self.assertEqual(d['tracks'][1],out['tracks'][1])
        self.assertEqual(d['materials']['transitions'],out['materials']['transitions'])

    def test_random_missing_only_errors_when_nothing_available(self):
        with self.assertRaisesRegex(ValueError,'No locally available'):
            make_plan(fixture(),catalog(),[(0,2)],mode='random')

    @patch('animation_engine.resource_is_available',return_value=True)
    def test_no_valid_image_duration_is_skipped(self,unused):
        d=fixture();d['tracks'][0]['segments'][2]['target_timerange']['duration']=0
        row=make_plan(d,catalog(),[(0,2)],'native1')[0][0]
        self.assertEqual(row['status'],'Skipped')


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.project=self.root/'Demo';self.project.mkdir()
        self.main=self.project/'draft_content.json';self.main.write_text(json.dumps(fixture()))
        self.timeline_dir=self.project/'Timelines'/'ABC';self.timeline_dir.mkdir(parents=True)
        (self.project/'Timelines'/'project.json').write_text('{"main_timeline_id":"ABC"}')
        self.mirror=self.timeline_dir/'draft_content.json';self.mirror.write_bytes(self.main.read_bytes())
        self.original=self.main.read_bytes()

    def tearDown(self): self.temp.cleanup()

    @patch('animation_engine.capcut_running',return_value=False)
    @patch('animation_engine.resource_is_available',return_value=True)
    def test_backup_mirror_no_video_writes(self,available,cc):
        src,_,_=load_project(self.project)
        rows,_=make_plan(src,catalog(),[(0,2)],'native1')
        result=save(self.project,catalog(),'native1',rows)
        self.assertTrue(result['saved']);self.assertEqual(result['changed'],1)
        self.assertEqual(self.main.read_bytes(),self.mirror.read_bytes())
        d=json.loads(self.main.read_bytes())
        self.assertEqual(stable_media_fingerprint(d),stable_media_fingerprint(src))
        manifest=json.loads((Path(result['backup_dir'])/'manifest.json').read_text())
        self.assertTrue(any((Path(result['backup_dir'])/m['backup']).read_bytes()==self.original for m in manifest))

    @patch('animation_engine.capcut_running',return_value=True)
    @patch('animation_engine.resource_is_available',return_value=True)
    def test_capcut_open_blocks_all_writes(self,available,cc):
        rows,_=make_plan(fixture(),catalog(),[(0,2)],'native1')
        with self.assertRaisesRegex(RuntimeError,'CapCut is open'):
            save(self.project,catalog(),'native1',rows)
        self.assertEqual(self.main.read_bytes(),self.original)

    @patch('animation_engine.capcut_running',return_value=False)
    @patch('animation_engine.resource_is_available',return_value=True)
    def test_stale_photo_segment_identity_blocks(self,available,cc):
        rows,_=make_plan(fixture(),catalog(),[(0,2)],'native1')
        d=fixture();d['tracks'][0]['segments'][2]['id']='other'
        self.main.write_text(json.dumps(d));self.mirror.write_text(json.dumps(d))
        with self.assertRaisesRegex(RuntimeError,'changed since preview'):
            save(self.project,catalog(),'native1',rows)

if __name__=='__main__': unittest.main()