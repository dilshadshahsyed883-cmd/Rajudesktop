import unittest
from scene_desktop.timeline import StudioProject
from scene_desktop.live_preview_math import (
    active_layers,active_captions,placement_for,classify_gl_renderer,
    MAX_CACHE_BYTES,PREVIEW_MAX_SIDE
)


class LivePreviewMathTests(unittest.TestCase):
    def test_layer_order_and_timeline_scrubbing(self):
        p=StudioProject(width=1280,height=720)
        background=p.add("bg.png","image","v1",5000)
        overlay=p.add("overlay.png","image","v2",3000,start_ms=1000)
        title=p.add("","text","captions",900,start_ms=1200,text="Title")
        self.assertEqual([x.id for x in active_layers(p,1300)],[background.id,overlay.id])
        self.assertEqual([x.id for x in active_layers(p,4500)],[background.id])
        self.assertEqual(len(active_captions(p,1300)),1)
        self.assertEqual(len(active_captions(p,2500)),0)
        p.track("v2").visible=False
        self.assertEqual([x.id for x in active_layers(p,1300)],[background.id])

    def test_motion_transition_keyframe_and_vendor_classification(self):
        p=StudioProject(width=1280,height=720)
        item=p.add("source.png","image","v1",4000)
        item.effects={"motion":"pan_right","brightness":.1}
        item.transition_in="slide_left"
        item.transition_ms=1000
        before=placement_for(item,0,1280,720)
        mid=placement_for(item,2000,1280,720)
        self.assertGreater(before.translate_x,1000)
        self.assertEqual(mid.translate_x,0)
        self.assertGreater(before.zoom,1)
        item.keyframes={"zoom":[{"at_ms":0,"value":1.0},
                                {"at_ms":4000,"value":2.0}]}
        self.assertAlmostEqual(placement_for(item,2000,1280,720).zoom,1.5)
        self.assertEqual(classify_gl_renderer("llvmpipe (LLVM 15.0)"),"software")
        self.assertEqual(classify_gl_renderer("NVIDIA GeForce RTX 4060","NVIDIA"),"hardware-candidate")
        self.assertEqual(classify_gl_renderer(""),"unknown")
        self.assertLess(PREVIEW_MAX_SIDE,1920)
        self.assertGreater(MAX_CACHE_BYTES,24*1024*1024)
