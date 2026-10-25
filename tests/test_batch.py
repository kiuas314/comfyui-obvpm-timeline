"""YAML batch parsing and its plan/save/commit checkpoint transaction."""

import importlib
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

    def write_manifest(self, data=None):
        path = os.path.join(self.input, "film.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data or self.manifest(), handle)
        return path

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
        self.write_manifest()
        planner = self.batch.H3BatchPlan()
        first = planner.plan("film.yaml", "movie-v1", "movie", 100)
        again = planner.plan("film.yaml", "movie-v1", "movie", 100)
        self.assertEqual(first[7], again[7])  # metadata
        self.assertEqual(first[8], again[8])  # ticket
        self.assertEqual(first[2], 100)
        self.assertEqual(first[4], [])

        first_path = self.saved_take("movie/opening_00001.mp4")
        result = self.batch.H3BatchCommit().commit(
            first_path, first[8], auto_export=False)
        self.assertFalse(result["result"][1])
        second = planner.plan("film.yaml", "movie-v1", "movie", 100)
        self.assertEqual(second[0], "B")
        self.assertEqual(second[2], 101)
        self.assertEqual(second[4][0]["source_path"],
                         "movie/opening_00001.mp4")

    def test_named_context_and_final_sequence(self):
        self.write_manifest()
        planner = self.batch.H3BatchPlan()
        commit = self.batch.H3BatchCommit()
        tickets = []
        paths = []
        for i, name in enumerate(("opening", "middle", "callback")):
            planned = planner.plan("film.yaml", "movie-v2", "movie", 5)
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

    def test_changed_manifest_does_not_reuse_checkpoint(self):
        path = self.write_manifest()
        self.batch.H3BatchPlan().plan(path, "movie-v3", "movie", 0)
        changed = self.manifest()
        changed["clips"][0]["prompt"] = "changed"
        self.write_manifest(changed)
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            self.batch.H3BatchPlan().plan(
                path, "movie-v3", "movie", 0)


if __name__ == "__main__":
    unittest.main()
