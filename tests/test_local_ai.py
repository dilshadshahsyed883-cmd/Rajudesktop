import io
import json
from unittest.mock import patch
import unittest

from scene_desktop.local_ai import _parse_model_response, plan_with_local_ai


class ModelDirectorTests(unittest.TestCase):
    def test_structured_local_model_output_and_unapproved_scene_state(self):
        mock_output = {
            "response": json.dumps({"scenes":[
                {"text":"Moon over city skyline","duration_ms":3000,"keywords":["moon","city"]},
                {"text":"Camera pans to forest","duration_ms":4000,"keywords":["forest"]}
            ]})
        }
        class FakeOpener:
            def open(self, req, timeout):
                self.url = req.full_url
                self.payload = json.loads(req.data)
                return io.BytesIO(json.dumps(mock_output).encode())
        opener = FakeOpener()
        with patch("scene_desktop.local_ai.request.build_opener", return_value=opener):
            scenes = plan_with_local_ai("The moon shines. Trees sway.", "local-model")
        self.assertEqual(opener.url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(opener.payload["stream"], False)
        self.assertEqual(scenes[1].start_ms,3000)
        self.assertFalse(scenes[0].approved)
        self.assertFalse(scenes[1].approved)

    def test_reject_bad_ai_output(self):
        for text in ["{}", "[]", '{"scenes":[{"text":"x","duration_ms":8}]}',
                     '{"scenes":[{"text":"","duration_ms":3000}]}']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                _parse_model_response(text)
        with self.assertRaises(ValueError):
            plan_with_local_ai("hello", "spaces in model name")


if __name__ == "__main__":
    unittest.main()
