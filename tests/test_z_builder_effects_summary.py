"""Summary contract tests: native names/IDs, cache honesty and zero private paths."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from z_builder.effects_summary import render_effects_summary, scan_effects_summary


class EffectsSummaryTests(unittest.TestCase):
    @staticmethod
    def sample_animations():
        return [
            {"name": "Pendulum 2", "effect_id": "6811007833069326862",
             "category": "Trending-3", "duration_us": 5000000,
             "cache_available": True, "path": "C:/Users/secret/CapCut/Cache/Private"},
            {"name": "Wobble", "effect_id": "missing1", "category": "Trending-3",
             "duration_us": 5000000, "cache_available": False,
             "path": "C:/Users/secret/Deleted"},
            {"name": 'Name "Quoted"', "effect_id": "special1", "category": "Trending-3",
             "duration_us": 2500000, "cache_available": True},
        ]

    @staticmethod
    def sample_transitions():
        return [
            {"name": "Pull in", "effect_id": "672422", "category": "Trending",
             "from_project": "Personal Project", "template": {"path": "C:/private/abc"}},
            {"name": "Blink", "effect_id": "effect-blink", "category": "Transitions"},
        ]

    def test_deterministic_exact_native_ids_and_availability(self):
        first = render_effects_summary(self.sample_animations(), self.sample_transitions())
        second = render_effects_summary(list(reversed(self.sample_animations())),
                                        list(reversed(self.sample_transitions())))
        self.assertEqual(first, second)
        self.assertIn("native_combo_animations_available=2", first)
        self.assertIn("native_combo_animations_missing_cache=1", first)
        self.assertIn("transitions_detected_in_saved_drafts=2", first)
        self.assertIn('name="Pendulum 2" | effect_id="6811007833069326862"', first)
        self.assertIn('name="Name \\"Quoted\\"" | effect_id="special1"', first)
        self.assertIn('name="Pull in" | effect_id="672422"', first)
        self.assertIn("duration_seconds=2.5", first)
        self.assertIn("transition_resource_cache_verified=no", first)

    def test_unavailable_animation_not_in_available_section(self):
        report = render_effects_summary(self.sample_animations(), [])
        available = report.split("[AVAILABLE_NATIVE_COMBO_ANIMATIONS]")[1].split("[DETECTED_TRANSITIONS]")[0]
        unavailable = report.split("[MISSING_NATIVE_COMBO_ANIMATIONS]")[1].split("[CHATGPT_SCENE_PLAN_RULES]")[0]
        self.assertNotIn("Wobble", available)
        self.assertIn('name="Wobble"', unavailable)
        self.assertIn("selectable=no", unavailable)

    def test_no_personal_local_paths_or_projects_leak(self):
        report = render_effects_summary(self.sample_animations(), self.sample_transitions())
        for sensitive in ["C:/Users/", "C:/private/", "Personal Project", "secret", "Private", "Deleted"]:
            self.assertNotIn(sensitive, report)
        self.assertIn("Z Builder v8 accepts combo=", report)
        self.assertIn("images/photos, NEVER video clips", report)

    def test_empty_catalog_explicit_and_safe(self):
        report = render_effects_summary([], [], different_folders=True)
        self.assertIn("native_combo_animations_available=0", report)
        self.assertIn("transitions_detected_in_saved_drafts=0", report)
        self.assertIn("catalogs_scanned_from_different_folders=yes", report)
        self.assertIn("(none", report)

    def test_scan_uses_exact_configured_roots(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            anim = [{"effect_id":"one","name":"Pendulum 1","duration_us":5000000,
                     "category":"Trending-3","path":"/not/saved/path"}]
            trn = [{"effect_id":"two","name":"Pull in","category":"Trending"}]
            with (mock.patch("z_builder.effects_summary.harvest_animations", return_value=anim) as ha,
                  mock.patch("z_builder.effects_summary.harvest_transitions", return_value=trn) as ht,
                  mock.patch("z_builder.effects_summary.resource_is_available", return_value=True) as ra):
                report = scan_effects_summary(first, second)
            ha.assert_called_once_with(Path(second), trending_only=True)
            ht.assert_called_once_with(Path(first))
            ra.assert_called_once_with(anim[0])
            self.assertIn('effect_id="one"', report)
            self.assertIn('effect_id="two"', report)
            self.assertIn("catalogs_scanned_from_different_folders=yes", report)
            self.assertNotIn(first, report)
            self.assertNotIn(second, report)

    def test_missing_roots_explained_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_a = Path(tmp) / "missing-A"
            missing_b = Path(tmp) / "missing-B"
            with self.assertRaisesRegex(FileNotFoundError, "CapCut project folders"):
                scan_effects_summary(missing_a, missing_b)


if __name__ == "__main__":
    unittest.main()
