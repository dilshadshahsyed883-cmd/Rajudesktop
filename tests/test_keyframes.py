import tempfile
import unittest
from pathlib import Path

from scene_desktop.keyframes import (ffmpeg_expression,remove_keyframe,
                                     set_keyframe,validate_keyframes,value_at)
from scene_desktop.timeline import StudioProject,load,save


class KeyframeTests(unittest.TestCase):
    def test_interpolation_mutation_and_project_roundtrip(self):
        data = {}
        data = set_keyframe(data, "zoom", 0, 1., 2500)
        data = set_keyframe(data, "zoom", 2000, 2., 2500)
        self.assertEqual(value_at(data["zoom"], 1000,1),1.5)
        self.assertAlmostEqual(value_at(data["zoom"], 2500,1),2)
        expression = ffmpeg_expression(data["zoom"],1,24,1000,variable="on")
        self.assertIn("on+24.000000",expression)
        self.assertIn("if(",expression)
        with self.assertRaises(ValueError):
            set_keyframe(data,"zoom",2100,5,2500)
        with self.assertRaises(ValueError):
            validate_keyframes({"zoom":[{"at_ms":2000,"value":1.},{"at_ms":1,"value":2.}]},2500)
        with tempfile.TemporaryDirectory() as folder:
            p = StudioProject()
            image = Path(folder)/"still.png"
            image.touch()
            item = p.add(str(image),"image","v1",2500)
            item.keyframes = data
            path = Path(folder)/"project.sds2"
            save(p,path)
            loaded = load(path)
            self.assertEqual(loaded.item(item.id).keyframes,data)
        self.assertEqual(remove_keyframe(data,"zoom",2000)["zoom"],[{"at_ms":0,"value":1.}])

    def test_reject_nonfinite_wrong_property_and_out_of_bounds(self):
        for property_name,val in [("zoom",float("nan")),("zoom",float("inf")),("brightness",2)]:
            with self.assertRaises(ValueError):
                set_keyframe({},property_name,10,val,1000)
        with self.assertRaises(ValueError):
            set_keyframe({},"rotate",0,20,1000)
