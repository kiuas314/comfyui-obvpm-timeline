"""Structural checks for the ready-wired 007A YAML batch workflow."""

import json
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
WORKFLOW = os.path.join(
    ROOT, "workflows", "h3_obvpm_timeline_r2v_v0.1.4-007A-batch.json")


class BatchWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, "r", encoding="utf-8") as handle:
            cls.workflow = json.load(handle)
        cls.nodes = {node["id"]: node for node in cls.workflow["nodes"]}
        cls.links = {link[0]: link for link in cls.workflow["links"]}

    def test_graph_links_are_reciprocal(self):
        self.assertEqual(len(self.nodes), len(self.workflow["nodes"]))
        self.assertEqual(len(self.links), len(self.workflow["links"]))
        for link_id, link in self.links.items():
            _, origin_id, origin_slot, target_id, target_slot, _ = link
            self.assertIn(origin_id, self.nodes)
            self.assertIn(target_id, self.nodes)
            self.assertIn(
                link_id,
                self.nodes[origin_id]["outputs"][origin_slot].get("links")
                or [],
            )
            self.assertEqual(
                self.nodes[target_id]["inputs"][target_slot].get("link"),
                link_id,
            )

    def test_batch_path_drives_existing_generation_and_save_nodes(self):
        planner = next(node for node in self.workflow["nodes"]
                       if node["type"] == "H3BatchPlan")
        settings = next(node for node in self.workflow["nodes"]
                        if node["type"] == "H3BatchSettings")
        commit = next(node for node in self.workflow["nodes"]
                      if node["type"] == "H3BatchCommit")
        scene_loras = next(node for node in self.workflow["nodes"]
                           if node["type"] == "H3BatchLoraApply")
        save = next(node for node in self.workflow["nodes"]
                    if node["type"] == "H3TrimAndSaveVideoWithMCtx")

        targets = {
            output["name"]: [self.links[link_id][3]
                             for link_id in output.get("links") or []]
            for output in planner["outputs"]
        }
        self.assertIn(761, targets["prompt"])
        self.assertIn(1488, targets["seed"])
        self.assertIn(797, targets["length"])
        self.assertIn(1479, targets["pin_specs"])
        self.assertIn(save["id"], targets["filename_prefix"])
        self.assertIn(save["id"], targets["metadata"])
        self.assertIn(commit["id"], targets["ticket"])
        self.assertIn(scene_loras["id"], targets["content_loras"])
        self.assertEqual(self.links[commit["inputs"][0]["link"]][1],
                         save["id"])
        self.assertIn("manifest_yaml",
                      [input_["name"] for input_ in planner["inputs"]])
        self.assertIn("run_selection",
                      [input_["name"] for input_ in planner["inputs"]])
        self.assertIn("add_to_timeline",
                      [input_["name"] for input_ in commit["inputs"]])
        self.assertTrue(commit["widgets_values_named"]["add_to_timeline"])
        self.assertEqual(
            self.links[planner["inputs"][2]["link"]][1], settings["id"])
        folder_targets = [self.links[link_id][3]
                          for link_id in settings["outputs"][0]["links"]]
        self.assertIn(planner["id"], folder_targets)
        self.assertIn(1221, folder_targets)
        self.assertIn(1293, folder_targets)
        self.assertNotIn(761, folder_targets)
        self.assertEqual(self.links[2696][1], settings["id"])
        self.assertEqual(self.links[2730][1], planner["id"])

        generation = next(group for group in self.workflow["groups"]
                          if group["id"] == 27)["bounding"]
        sx, sy = scene_loras["pos"]
        sw, sh = scene_loras["size"]
        self.assertGreaterEqual(sx, generation[0])
        self.assertGreaterEqual(sy, generation[1])
        self.assertLessEqual(sx + sw, generation[0] + generation[2])
        self.assertLessEqual(sy + sh, generation[1] + generation[3])

        # Commit must be in the generation group so Timeline's normal group
        # muter removes the complete planner/commit chain from upscale runs.
        x, y = commit["pos"]
        width, height = commit["size"]
        self.assertGreaterEqual(x, generation[0])
        self.assertGreaterEqual(y, generation[1])
        self.assertLessEqual(x + width, generation[0] + generation[2])
        self.assertLessEqual(y + height, generation[1] + generation[3])

    def test_original_engine_settings_remain_present(self):
        types = [node["type"] for node in self.workflow["nodes"]]
        self.assertIn("MiniMaxH3ReferenceToVideo", types)
        self.assertIn("H3LivePreview", types)
        self.assertIn("MinimaxH3LatentUpscaler3D", types)
        self.assertIn("H3Timeline", types)
        upscale_preview = self.nodes[1342]
        self.assertEqual(upscale_preview["mode"], 0)
        self.assertEqual(upscale_preview["title"], "H3 Upscale Result")

        # Timeline owns the mode bundle's duration again; the planner's clip
        # duration only feeds the muted generation engine.
        self.assertEqual(self.links[2651][1], 1221)

    def test_upscale_result_has_no_implicit_planner_dependency(self):
        setters = {
            str(node.get("widgets_values", [None])[0]): node["id"]
            for node in self.workflow["nodes"] if node["type"] == "SetNode"
        }
        seen = set()
        pending = [1474]  # Set_upscale_result
        while pending:
            node_id = pending.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            node = self.nodes[node_id]
            for input_ in node.get("inputs", []):
                link_id = input_.get("link")
                if link_id in self.links:
                    pending.append(self.links[link_id][1])
            if node["type"] == "GetNode":
                key = str(node.get("widgets_values", [None])[0])
                if key in setters:
                    pending.append(setters[key])

        planner = next(node["id"] for node in self.workflow["nodes"]
                       if node["type"] == "H3BatchPlan")
        commit = next(node["id"] for node in self.workflow["nodes"]
                      if node["type"] == "H3BatchCommit")
        self.assertNotIn(planner, seen)
        self.assertNotIn(commit, seen)

    def test_batch_plan_has_its_own_full_height_group_and_ref_table_is_clear(self):
        planner = next(node for node in self.workflow["nodes"]
                       if node["type"] == "H3BatchPlan")
        groups = {group["title"]: group
                  for group in self.workflow["groups"]}
        plan_group = groups["H3 Story + Clip Editor"]["bounding"]
        ui_group = groups["OBVPM H3 YAML Batch UI [restore]"]["bounding"]
        self.assertEqual(plan_group[1], ui_group[1])
        self.assertEqual(plan_group[3], ui_group[3])
        self.assertLess(plan_group[0] + plan_group[2], ui_group[0])
        self.assertGreaterEqual(planner["pos"][0], plan_group[0])
        self.assertIn("reference_image: 1", planner["widgets_values"][0])
        self.assertIn("reference_image: 2", planner["widgets_values"][0])

        resolution = self.nodes[118]
        self.assertGreaterEqual(resolution["pos"][1],
                                ui_group[1] + ui_group[3])


if __name__ == "__main__":
    unittest.main()
