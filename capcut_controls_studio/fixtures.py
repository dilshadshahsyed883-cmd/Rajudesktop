"""Disposable JSON-only projects for isolated native-engine and frozen tests."""
import json
from pathlib import Path


def create_project(root, name='Demo Project'):
    root=Path(root)
    project=root/name
    timeline=project/'Timelines'/'active'
    timeline.mkdir(parents=True)
    cache=root/'native-animation-cache'
    cache.mkdir(exist_ok=True)
    image=root/'photo.jpg';video=root/'clip.mp4'
    image.write_bytes(b'original image fixture - never edited')
    video.write_bytes(b'original video fixture - never edited')
    raw={
        'id':name,'name':name,'duration':9_000_000,
        'canvas_config':{'width':1920,'height':1080},
        'materials':{
            'videos':[{'id':'photo','type':'photo','material_name':'photo.jpg','path':str(image)},
                      {'id':'video','type':'video','material_name':'clip.mp4','path':str(video)}],
            'transitions':[{'id':'native-transition','effect_id':name+'-fade','name':'Native Fade',
                            'category_name':'Basic','duration':400_000}],
            'material_animations':[{'id':'native-animation','type':'sticker_animation','animations':[
                {'id':name+'-combo','resource_id':name+'-combo','name':'Native Combo',
                 'category_name':'Trending','type':'group','start':0,'duration':4_000_000,'path':str(cache)}]}],
            'canvases':[], 'audios':[{'id':'voice','type':'audio','path':'voice.wav'}],
            'video_effects':[{'id':'untouched-effect','type':'video_effect','name':'Preserved fixture effect'}],
            'effects':[{'id':'untouched-filter','name':'Preserved fixture filter'}]},
        'tracks':[{'id':'visual','type':'video','segments':[
            {'id':'photo-1','material_id':'photo','extra_material_refs':['native-transition','native-animation','untouched-effect'],
             'target_timerange':{'start':0,'duration':2_500_000},'source_timerange':{'start':0,'duration':2_500_000},
             'clip':{'scale':{'x':1,'y':1},'transform':{'x':.15,'y':0}},'uniform_scale':{'on':True,'value':1}},
            {'id':'video-1','material_id':'video','extra_material_refs':[],
             'target_timerange':{'start':2_500_000,'duration':4_000_000},'source_timerange':{'start':0,'duration':4_000_000},
             'clip':{'scale':{'x':1,'y':1},'transform':{'x':.1,'y':0}},'uniform_scale':{'on':True,'value':1}},
            {'id':'photo-2','material_id':'photo','extra_material_refs':[],
             'target_timerange':{'start':6_500_000,'duration':2_500_000},'source_timerange':{'start':0,'duration':2_500_000},
             'clip':{'scale':{'x':1,'y':1},'transform':{'x':.15,'y':0}}}]},
          {'id':'voice-track','type':'audio','segments':[{'id':'narration','material_id':'voice',
            'target_timerange':{'start':0,'duration':9_000_000},'source_timerange':{'start':0,'duration':9_000_000}}]}]}
    for path in [project/'draft_content.json',timeline/'draft_content.json']:
        path.write_text(json.dumps(raw),encoding='utf8')
    (project/'Timelines'/'project.json').write_text(json.dumps({'main_timeline_id':'active'}))
    (project/'draft_meta_info.json').write_text(json.dumps({'tm_draft_modified':1,'draft_name':name}))
    return project,raw,[image,video]
