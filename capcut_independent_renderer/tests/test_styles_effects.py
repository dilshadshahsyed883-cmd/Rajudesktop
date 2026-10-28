"""Regression coverage derived from the uploaded 1028 draft's actual schema."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from captions import parse_caption, write_ass, wrapped_lines
from effects import parse_effect
from engine import Draft, render, executable, chunk_times
from fontinfo import read_font, fallback_font


def text_material():
    return {'id':'text','type':'subtitle','content':json.dumps({
        'styles':[{'fill':{'alpha':1,'content':{'render_type':'solid','solid':{'alpha':1,'color':[0,0,0]}}},
                   'font':{'path':fallback_font()},'range':[0,16],'size':5}],
        'text':'A WTA 500 event.'}),
        'global_alpha':1,'text_alpha':1,'font_size':5,'font_path':fallback_font(),
        'text_color':'#000000','background_color':'#ffdc00','background_alpha':1,
        'background_style':1,'background_round_radius':.40000000596,
        'background_width':.28000000119,'background_height':.28000000119,
        'background_horizontal_offset':0,'background_vertical_offset':0,
        'border_color':'','border_width':.08,'has_shadow':False,'line_max_width':.82}


def hdr_material():
    return {'id':'hdr','name':'HDR','type':'video_effect','apply_target_type':2,'value':1,
            'adjust_params':[{'name':name,'value':value} for name,value in (
                ('effects_adjust_intensity',.02),('effects_adjust_range',.11),
                ('effects_adjust_luminance',.18),('effects_adjust_filter',.32),
                ('effects_adjust_size',.7),('effects_adjust_number',.45))]}


def project(folder,with_text=True,with_effect=False,image=None):
    tracks=[]
    materials={'texts':[text_material()]}
    if image:
        materials['videos']=[{'id':'image','type':'photo','path':str(image)}]
        tracks.append({'type':'video','segments':[{'material_id':'image','target_timerange':{'start':0,'duration':2000000}}]})
    if with_text:
        tracks.append({'type':'text','segments':[{'material_id':'text','target_timerange':{'start':500000,'duration':1000000},
            'clip':{'transform':{'x':0,'y':-.8}}}]})
    if with_effect:
        materials['video_effects']=[hdr_material()]
        tracks.append({'type':'effect','segments':[{'material_id':'hdr','target_timerange':{'start':500000,'duration':1000000}}]})
    raw={'fps':30,'duration':2000000,'canvas_config':{'width':640,'height':360},'materials':materials,'tracks':tracks}
    path=Path(folder)/'draft_content.json';path.write_text(json.dumps(raw))
    return Draft(str(path))


def frame(path,at):
    return subprocess.run([executable('ffmpeg'),'-v','error','-ss',str(at),'-i',str(path),
        '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout


class StyleTests(unittest.TestCase):
    @unittest.skipUnless(fallback_font(),'System test font required')
    def test_family_is_read_from_actual_font_file_and_not_guessed_from_filename(self):
        font=read_font(fallback_font())
        self.assertTrue(font.family)
        self.assertGreater(font.width('WWWW',54),font.width('iiii',54))
        with tempfile.TemporaryDirectory() as folder:
            draft=project(folder)
            self.assertEqual(draft.font_status[0]['status'],'source_font')
            self.assertEqual(draft.captions[0].font,font.family)
            self.assertFalse(any('Arial/system fallback selected' in warning for warning in draft.warnings))

    def test_full_range_style_is_not_a_word_highlight_animation(self):
        c,warnings=parse_caption(text_material(),{},0,1,0)
        self.assertFalse(any('ranges' in w for w in warnings))
        self.assertEqual(c.background_color,'&H0000DCFF')
        self.assertEqual(c.color,'&H00000000')
        self.assertEqual(c.outline_width,0)

    def test_empty_animation_placeholders_are_not_reported_as_missing_animations(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=project(folder)
            raw=draft.raw
            raw['materials']['material_animations']=[{'id':f'anim{i}','type':'sticker_animation','animations':[]} for i in range(404)]
            draft.path.write_text(json.dumps(raw))
            summary=Draft(str(draft.path)).summary()
            self.assertEqual(summary['animation_materials_empty'],404)
            self.assertEqual(summary['animation_materials_active'],0)
            self.assertFalse(any('material_animations' in warning for warning in summary['unsupported_feature_summary']))

    def test_background_is_separate_timed_rounded_shape_and_text_preserves_black(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=project(folder)
            path=Path(folder)/'captions.ass'
            self.assertEqual(write_ass(path,draft.captions,640,360,2),1)
            events=[line for line in path.read_text(encoding='utf-8-sig').splitlines() if line.startswith('Dialogue:')]
            self.assertEqual(len(events),2)
            self.assertIn(r'\p1',events[0]);self.assertIn(' b ',events[0])
            self.assertIn('&H0000DCFF',events[0])
            self.assertIn(r'\c&H00000000',events[1])
            self.assertNotIn(r'\fad',events[0])

    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'FFmpeg required')
    def test_real_schema_background_and_text_pixels_are_visible_and_timed(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=project(folder)
            out,report=render(draft,folder,'Original',0,lambda *_:None,threading.Event())
            pixels=frame(out,.8)
            yellow=[]
            for i in range(0,len(pixels),3):
                r,g,b=pixels[i:i+3]
                if r>180 and g>140 and b<60:yellow.append(i//3)
            self.assertGreater(len(yellow),500)
            minx,maxx=min(i%640 for i in yellow),max(i%640 for i in yellow)
            miny,maxy=min(i//640 for i in yellow),max(i//640 for i in yellow)
            # Black glyph interiors lie within the yellow background rectangle.
            black=sum(max(pixels[(y*640+x)*3:(y*640+x)*3+3])<60
                for y in range(miny+4,maxy-3) for x in range(minx+4,maxx-3))
            self.assertGreater(black,50)
            after=frame(out,1.8)
            self.assertLess(max(after),50)
            self.assertEqual(json.loads(report.read_text())['caption_backgrounds_in_export'],1)


class EffectTests(unittest.TestCase):
    def test_hdr_keeps_source_parameters_and_discloses_approximation(self):
        effect=parse_effect(hdr_material(),{},0,1)
        self.assertEqual(effect.parameters['effects_adjust_intensity'],.02)
        self.assertIn('eq=',effect.filter());self.assertIn('unsharp=',effect.filter())
        summary=effect.summary()
        self.assertFalse(summary['native_capcut_equivalence'])
        self.assertEqual(summary['unmapped_parameters'],['effects_adjust_number'])

    def test_unknown_and_masked_effects_are_not_claimed_supported(self):
        material=hdr_material();material['name']='Unknown effect'
        with self.assertRaises(ValueError):parse_effect(material,{},0,1)
        material=hdr_material();material['effect_mask']=[{'id':'mask'}]
        with self.assertRaises(ValueError):parse_effect(material,{},0,1)

    def test_effect_timerange_creates_frame_aligned_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            draft=project(folder,with_effect=True)
            self.assertEqual(chunk_times(draft,2),[(0,.5),(.5,1.5),(1.5,2)])

    @unittest.skipUnless(executable('ffmpeg') and executable('ffprobe'),'FFmpeg required')
    def test_hdr_filter_changes_pixels_only_inside_its_timerange(self):
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'pattern.png'
            subprocess.run([executable('ffmpeg'),'-v','error','-y','-f','lavfi','-i',
                'testsrc2=size=640x360:rate=1','-frames:v','1',str(image)],check=True)
            draft=project(folder,with_text=False,with_effect=True,image=image)
            on,report=render(draft,folder,'Original',0,lambda *_:None,threading.Event())
            off,_=render(draft,folder,'Original',0,lambda *_:None,threading.Event(),effects_enabled=False)
            for at in (.2,1.8):self.assertEqual(frame(on,at),frame(off,at))
            a,b=frame(on,.8),frame(off,.8)
            self.assertGreater(sum(abs(x-y) for x,y in zip(a,b)),1000)
            self.assertEqual(json.loads(report.read_text())['effects_applied_in_export'],1)


if __name__=='__main__':unittest.main()
