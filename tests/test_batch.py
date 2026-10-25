"""YAML batch parsing and its plan/save/commit checkpoint transaction."""

import importlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = "obvpm_batch_test"


class FakeTimeline:
    @staticmethod
    def _run_length(seconds, masks):
        return round(float(seconds) * 24) + (1 if masks else 0)

    def _specs_for(self, clip, role, window, cut, pin_mode="guide"):
        return [{"source_path": clip, "role": role, "window": window,
                 "cut": cut, "mode": pin_mode}]


def _load_module(input_dir, output_dir):
    package = types.ModuleType(PACKAGE)
    package.__path__ = [ROOT]
    sys.modules[PACKAGE] = package

    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_input_directory = lambda: input_dir
    folder_paths.get_output_directory = lambda: output_dir
    sys.modules["folder_paths"] = folder_paths

    compat = types.ModuleType(PACKAGE + ".compat")
    compat.require = lambda: None
    sys.modules[compat.__name__] = compat
    wiretypes = types.ModuleType(PACKAGE + ".wiretypes")
    wiretypes.PINSPECS = "OBVPM_H3_PINSPECS"
    sys.modules[wiretypes.__name__] = wiretypes
    mctx = types.ModuleType(PACKAGE + ".mctx")
    mctx.sidecar_path = lambda path: path + ".mctx.safetensors"
    sys.modules[mctx.__name__] = mctx
    frames = types.ModuleType(PACKAGE + ".frames")
    frames.WINDOW_CHOICES = ("5", "22", "39", "56")
    sys.modules[frames.__name__] = frames
    assemble = types.ModuleType(PACKAGE + ".nodes_assemble")
    assemble.H3Timeline = FakeTimeline
    sys.modules[assemble.__name__] = assemble
    preview = types.ModuleType(PACKAGE + ".preview_route")
    preview.export_calls = []
    preview.export_cut = lambda *args, **kwargs: (
        preview.export_calls.append((args, kwargs)) or
        ("movie/full_00001.mp4", False))
    sys.modules[preview.__name__] = preview
    sys.modules.pop(PACKAGE + ".nodes_batch", None)
    return importlib.import_module(PACKAGE + ".nodes_batch")


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="obvpm_batch_")
        self.input = os.path.join(self.tmp, "input")
        self.output = os.path.join(self.tmp, "output")
        os.makedirs(self.input)
        os.makedirs(self.output)
        self.batch = _load_module(self.input, self.output)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def manifest():
        # JSON is a YAML subset, keeping this test independent from whether
        # the harness installed the declared PyYAML dependency already.
        return {
            "version": 1,
            "defaults": {"duration_seconds": 8, "context": "previous"},
            "clips": [
                {"id": "opening", "context": "none", "prompt": "A"},
                {"id": "middle", "prompt": "B"},
                {"id": "callback", "context": "opening", "prompt": "C"},
            ],
        }

    @staticmethod
    def structured_manifest():
        return {
            "version": 2,
            "project": {
                "prompt_format": "h3_base",
                "language": "English",
                "visual_style": "Live-action cinematic, subtle film grain.",
                "story_context": "Mara returns during one stormy night.",
                "continuity": "Clothing and lighting remain consistent.",
                "negative_prompt": "subtitles, watermark",
            },
            "characters": {
                "mara": {
                    "name": "Mara Venn", "speaker_id": "S1",
                    "appearance": "a woman with hazel eyes and black hair",
                    "wardrobe": "a navy wool coat",
                    "voice": "a low, controlled English voice",
                },
            },
            "locations": {
                "dome": {
                    "description": "An old stone observatory above the sea.",
                    "soundscape": "Rain taps the glass.",
                },
            },
            "audio": {"default_music": "Sparse piano at a slow tempo."},
            "defaults": {
                "duration_seconds": 8, "context": "previous",
                "location": "dome", "cast": ["mara"], "music": "default",
                "camera": {"movement": "push_in", "amplitude": "small",
                           "speed": "slow"},
            },
            "clips": [
                {
                    "id": "opening", "context": "none",
                    "shot": {
                        "framing": "medium-wide shot",
                        "action": "Mara crosses toward the telescope.",
                    },
                    "dialogue": [{"speaker": "mara", "delivery": "quietly",
                                  "text": "You kept it pointed there."}],
                },
                {
                    "id": "continue",
                    "continuity": {"inherit_motion": True,
                                   "inherit_action": True},
                    "shot": {"action": "Mara grips the focusing wheel."},
                },
            ],
        }

    def saved_take(self, rel):
        path = os.path.join(self.output, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"video")
        with open(path + ".mctx.safetensors", "wb") as handle:
            handle.write(b"sidecar")
        return path

    def test_manifest_defaults_and_named_context(self):
        got = self.batch.parse_manifest(json.dumps(self.manifest()))
        self.assertEqual([c["context"] for c in got["clips"]],
                         ["none", "previous", "opening"])
        self.assertEqual(got["clips"][1]["duration_seconds"], 8)

    def test_structured_manifest_compiles_h3_sections(self):
        got = self.batch.parse_manifest(json.dumps(self.structured_manifest()))
        first = got["clips"][0]
        prompt = first["prompt"]
        self.assertIn("integrated_multimodal_description: [Shot 1]", prompt)
        self.assertIn("Live-action cinematic, subtle film grain.", prompt)
        self.assertIn("Mara returns during one stormy night.", prompt)
        self.assertIn("Mara Venn (S1) is a woman with hazel eyes", prompt)
        self.assertIn("wearing a navy wool coat", prompt)
        self.assertIn("Mara Venn (S1) says quietly: "
                      "<d>[English] You kept it pointed there.</d>", prompt)
        self.assertIn("The camera pushes in with small amplitude at slow speed.",
                      prompt)
        self.assertIn("overall_soundscape: Rain taps the glass.", prompt)
        self.assertIn("non_diegetic_music: Sparse piano", prompt)
        self.assertEqual(first["negative_prompt"], "subtitles, watermark")

        second = got["clips"][1]["prompt"]
        self.assertIn("continues seamlessly from the inherited", second)
        self.assertIn("Preserve the inherited camera motion and subject action",
                      second)

    def test_structured_multishot_timestamps_are_validated(self):
        data = self.structured_manifest()
        data["clips"][0].pop("shot")
        data["clips"][0].pop("dialogue")
        data["clips"][0]["shots"] = [
            {"action": "Mara enters."},
            {"at": 3.5, "action": "The view cuts closer.",
             "dialogue": [{"speaker": "mara", "text": "There."}]},
        ]
        prompt = self.batch.parse_manifest(json.dumps(data))["clips"][0]["prompt"]
        self.assertIn("[Shot 2] At 00:03.500, the camera cuts to", prompt)

        data["clips"][0]["shots"][1]["at"] = 8
        with self.assertRaisesRegex(ValueError, "before the 8.000s clip end"):
            self.batch.parse_manifest(json.dumps(data))

    def test_structured_unknown_character_is_refused(self):
        data = self.structured_manifest()
        data["clips"][0]["cast"] = ["nobody"]
        with self.assertRaisesRegex(ValueError, "unknown character"):
            self.batch.parse_manifest(json.dumps(data))

    def test_structured_duplicate_speaker_id_is_refused(self):
        data = self.structured_manifest()
        data["characters"]["elias"] = {
            "name": "Elias", "speaker_id": "S1",
        }
        with self.assertRaisesRegex(ValueError, "both use S1"):
            self.batch.parse_manifest(json.dumps(data))

    def test_reference_images_compile_to_h3_subject_definitions(self):
        data = self.structured_manifest()
        data["characters"]["mara"]["reference_image"] = 1
        parsed = self.batch.parse_manifest(json.dumps(data))
        prompt = parsed["clips"][0]["prompt"]
        self.assertIn("subject_definitions:\n<Subject 1> is Mara Venn "
                      "depicted in <Picture 1>.", prompt)
        self.assertIn("<Subject 1> (Mara Venn) (S1) is", prompt)

    def test_duplicate_reference_image_is_refused(self):
        data = self.structured_manifest()
        data["characters"]["mara"]["reference_image"] = 1
        data["characters"]["elias"] = {
            "name": "Elias", "reference_image": 1,
        }
        with self.assertRaisesRegex(ValueError, "both use Picture 1"):
            self.batch.parse_manifest(json.dumps(data))

    def test_structured_dialogue_speaker_must_be_in_cast(self):
        data = self.structured_manifest()
        data["clips"][0]["cast"] = []
        with self.assertRaisesRegex(ValueError, "not in this shot's cast"):
            self.batch.parse_manifest(json.dumps(data))

    def test_structured_raw_prompt_escape_hatch(self):
        data = self.structured_manifest()
        data["clips"] = [{"id": "raw", "context": "none",
                          "raw_prompt": "exact H3 prompt"}]
        got = self.batch.parse_manifest(json.dumps(data))
        self.assertEqual(got["clips"][0]["prompt"], "exact H3 prompt")

    def test_forward_context_is_refused(self):
        data = self.manifest()
        data["clips"][0]["context"] = "middle"
        with self.assertRaisesRegex(ValueError, "must be an earlier clip"):
            self.batch.parse_manifest(json.dumps(data))

    def test_self_context_is_refused(self):
        data = self.manifest()
        data["clips"][0]["context"] = "opening"
        with self.assertRaisesRegex(ValueError, "must be an earlier clip"):
            self.batch.parse_manifest(json.dumps(data))

    def test_active_item_repeats_until_commit_then_advances(self):
        manifest_yaml = json.dumps(self.manifest())
        planner = self.batch.H3BatchPlan()
        first = planner.plan(manifest_yaml, "movie-v1", "movie", 100)
        again = planner.plan(manifest_yaml, "movie-v1", "movie", 100)
        self.assertEqual(first[7], again[7])  # metadata
        self.assertEqual(first[8], again[8])  # ticket
        self.assertEqual(first[2], 100)
        self.assertEqual(first[4], [])

        first_path = self.saved_take("movie/opening_00001.mp4")
        result = self.batch.H3BatchCommit().commit(
            first_path, first[8], auto_export=False)
        self.assertFalse(result["result"][1])
        second = planner.plan(manifest_yaml, "movie-v1", "movie", 100)
        self.assertEqual(second[0], "B")
        self.assertEqual(second[2], 101)
        self.assertEqual(second[4][0]["source_path"],
                         "movie/opening_00001.mp4")

    def test_named_context_and_final_sequence(self):
        manifest_yaml = json.dumps(self.manifest())
        planner = self.batch.H3BatchPlan()
        commit = self.batch.H3BatchCommit()
        tickets = []
        paths = []
        for i, name in enumerate(("opening", "middle", "callback")):
            planned = planner.plan(manifest_yaml, "movie-v2", "movie", 5)
            if i == 2:
                self.assertEqual(planned[4][0]["source_path"], paths[0])
            rel = "movie/%s_00001.mp4" % name
            paths.append(rel)
            tickets.append(planned[8])
            result = commit.commit(self.saved_take(rel), planned[8],
                                   auto_export=(i == 2))
        self.assertTrue(result["result"][1])
        self.assertEqual(result["result"][0], "\n".join(paths))
        self.assertEqual(result["result"][2], "movie/full_00001.mp4")
        self.assertEqual(result["result"][3:], (3, 3))
        preview = sys.modules[PACKAGE + ".preview_route"]
        self.assertEqual(len(preview.export_calls), 1)
        self.assertEqual(preview.export_calls[0][0][0], "\n".join(paths))

    def test_pasted_yaml_plans_commits_and_resumes_without_a_file(self):
        yaml_text = json.dumps(self.manifest())
        planner = self.batch.H3BatchPlan()
        first = planner.plan(yaml_text, "inline-v1", "inline-movie", 40)
        self.assertEqual(first[0], "A")
        self.assertEqual(first[2], 40)
        ticket = json.loads(first[8])
        self.assertEqual(ticket["manifest_source"], "<pasted YAML>")
        self.assertEqual(ticket["total"], 3)

        result = self.batch.H3BatchCommit().commit(
            self.saved_take("inline-movie/opening_00001.mp4"),
            first[8], auto_export=False)
        self.assertFalse(result["result"][1])
        self.assertEqual(result["ui"]["batch"][0]["path"],
                         "inline-movie/opening_00001.mp4")
        self.assertTrue(result["ui"]["batch"][0]["add_to_timeline"])

        second = planner.plan(yaml_text, "inline-v1", "inline-movie", 40)
        self.assertEqual(second[0], "B")
        self.assertEqual(second[2], 41)

    def test_changed_pasted_yaml_does_not_reuse_checkpoint(self):
        planner = self.batch.H3BatchPlan()
        planner.plan(json.dumps(self.manifest()), "inline-v2", "inline-movie", 0)
        changed = self.manifest()
        changed["clips"][0]["prompt"] = "changed"
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            planner.plan(json.dumps(changed), "inline-v2", "inline-movie", 0)

    def test_pasted_yaml_widget_is_multiline_and_required(self):
        inputs = self.batch.H3BatchPlan.INPUT_TYPES()
        config = inputs["required"]["manifest_yaml"][1]
        self.assertTrue(config["multiline"])
        self.assertFalse(config["dynamicPrompts"])

    def test_empty_pasted_yaml_is_refused(self):
        with self.assertRaisesRegex(ValueError, "manifest_yaml is empty"):
            self.batch.H3BatchPlan().plan("", "empty-v1", "movie", 0)

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "PyYAML not installed")
    def test_default_castle_demo_has_two_roots_and_one_continuation(self):
        parsed = self.batch.parse_manifest(self.batch.DEFAULT_MANIFEST_YAML)
        self.assertEqual(
            [clip["context"] for clip in parsed["clips"]],
            ["none", "none", "previous"])
        self.assertEqual(
            [clip["id"] for clip in parsed["clips"]],
            ["castle_establishing", "ballroom_dance", "dance_to_kiss"])
        self.assertIn("tender, unhurried kiss", parsed["clips"][2]["prompt"])
        self.assertIn("<Subject 1> is Princess Elara depicted in <Picture 1>",
                      parsed["clips"][1]["prompt"])
        self.assertIn("<Subject 2> is Prince Adrian depicted in <Picture 2>",
                      parsed["clips"][1]["prompt"])
        inputs = self.batch.H3BatchPlan.INPUT_TYPES()["required"]
        self.assertEqual(inputs["batch_id"][1]["default"],
                         "castle-dance-ref2v-v1")
        self.assertEqual(inputs["base_folder"][1]["default"],
                         "castle_dance_test")


if __name__ == "__main__":
    unittest.main()
