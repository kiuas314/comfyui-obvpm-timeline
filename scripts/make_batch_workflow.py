#!/usr/bin/env python3
"""Build the YAML-batch variant of the latest 007A workflow.

The source workflow stays byte-for-byte independent of the batch variant.  We
only replace its supervised prompt, seed, duration and pin-spec wiring, then
attach the transactional batch commit after the existing save node.
"""

import json
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workflows" / "h3_obvpm_timeline_r2v_v0.1.4-007A.json"
TARGET = ROOT / "workflows" / "h3_obvpm_timeline_r2v_v0.1.4-007A-batch.json"
EXAMPLE = runpy.run_path(str(ROOT / "batch_example.py"))
DEFAULT_MANIFEST_YAML = EXAMPLE["DEFAULT_MANIFEST_YAML"]
DEFAULT_BATCH_ID = EXAMPLE["DEFAULT_BATCH_ID"]
DEFAULT_BASE_FOLDER = EXAMPLE["DEFAULT_BASE_FOLDER"]

PLAN_ID = 1631
COMMIT_ID = 1632
NOTE_ID = 1633


def node_by_id(workflow, node_id):
    return next(node for node in workflow["nodes"] if node["id"] == node_id)


def replace_link_origin(workflow, link_id, origin_id, origin_slot, link_type):
    link = next(link for link in workflow["links"] if link[0] == link_id)
    old_origin = node_by_id(workflow, link[1])
    old_links = old_origin["outputs"][link[2]].get("links") or []
    old_origin["outputs"][link[2]]["links"] = [one for one in old_links
                                                if one != link_id]
    link[1], link[2], link[5] = origin_id, origin_slot, link_type


def add_link(workflow, link_id, origin_id, origin_slot, target_id,
             target_slot, link_type):
    workflow["links"].append(
        [link_id, origin_id, origin_slot, target_id, target_slot, link_type])
    origin = node_by_id(workflow, origin_id)
    links = origin["outputs"][origin_slot].get("links")
    if links is None:
        links = []
        origin["outputs"][origin_slot]["links"] = links
    links.append(link_id)
    node_by_id(workflow, target_id)["inputs"][target_slot]["link"] = link_id


def plan_node():
    names = [
        ("prompt", "STRING"),
        ("negative_prompt", "STRING"),
        ("seed", "INT"),
        ("length", "INT"),
        ("pin_specs", "OBVPM_H3_PINSPECS"),
        ("base_folder", "STRING"),
        ("filename_prefix", "STRING"),
        ("metadata", "STRING"),
        ("ticket", "STRING"),
        ("index", "INT"),
        ("total", "INT"),
    ]
    inputs = []
    for name, input_type in (
            ("manifest_yaml", "STRING"), ("batch_id", "STRING"),
            ("base_folder", "STRING"), ("base_seed", "INT")):
        inputs.append({
            "localized_name": name,
            "name": name,
            "type": input_type,
            "widget": {"name": name},
            "link": None,
        })
    outputs = []
    for index, (name, output_type) in enumerate(names):
        outputs.append({
            "localized_name": name,
            "name": name,
            "type": output_type,
            "links": None,
        })
    return {
        "id": PLAN_ID,
        "type": "H3BatchPlan",
        "pos": [-1040, 5180],
        "size": [470, 760],
        "flags": {},
        "order": 22,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": "H3 YAML Batch Plan — queue remaining",
        "properties": {"Node name for S&R": "H3BatchPlan"},
        "widgets_values": [DEFAULT_MANIFEST_YAML, DEFAULT_BATCH_ID,
                           DEFAULT_BASE_FOLDER, 0],
        "widgets_values_named": {
            "manifest_yaml": DEFAULT_MANIFEST_YAML,
            "batch_id": DEFAULT_BATCH_ID,
            "base_folder": DEFAULT_BASE_FOLDER,
            "base_seed": 0,
        },
        "color": "#243342",
        "bgcolor": "#354b60",
    }


def commit_node():
    inputs = [
        {"localized_name": "path", "name": "path", "type": "STRING",
         "link": 3042},
        {"localized_name": "ticket", "name": "ticket", "type": "STRING",
         "link": 3043},
        {"localized_name": "auto_export", "name": "auto_export",
         "type": "BOOLEAN", "widget": {"name": "auto_export"},
         "link": None},
        {"localized_name": "export_filename_prefix",
         "name": "export_filename_prefix", "type": "STRING",
         "widget": {"name": "export_filename_prefix"}, "link": None},
        {"localized_name": "crf", "name": "crf", "type": "INT",
         "widget": {"name": "crf"}, "link": None},
    ]
    outputs = [
        {"localized_name": name, "name": name, "type": output_type,
         "links": None}
        for name, output_type in (
            ("sequence", "STRING"), ("complete", "BOOLEAN"),
            ("final_path", "STRING"), ("completed", "INT"),
            ("total", "INT"))
    ]
    return {
        "id": COMMIT_ID,
        "type": "H3BatchCommit",
        "pos": [3160, 4900],
        "size": [360, 210],
        "flags": {},
        "order": 86,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": "H3 Batch Commit + Final Export",
        "properties": {"Node name for S&R": "H3BatchCommit"},
        "widgets_values": [True, "full", 19],
        "widgets_values_named": {
            "auto_export": True,
            "export_filename_prefix": "full",
            "crf": 19,
        },
        "color": "#243342",
        "bgcolor": "#354b60",
    }


def note_node():
    return {
        "id": NOTE_ID,
        "type": "MarkdownNote",
        "pos": [-1040, 6480],
        "size": [470, 310],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "title": "YAML batch quick start",
        "properties": {"Node name for S&R": "MarkdownNote"},
        "widgets_values": [
            "## Unattended YAML batch\n\n"
            "A three-clip castle dance demo is already loaded. It contains "
            "one independent establishing shot, then two ballroom clips that "
            "share context and end with a kiss.\n\n"
            "1. Run the demo as-is, or replace all of `manifest_yaml` on "
            "**H3 YAML Batch Plan** with your screenplay.\n"
            "2. Choose a new `batch_id`; keep it unchanged to resume.\n"
            "3. Set the shared output `base_folder`.\n"
            "4. Set aspect ratio and megapixels in **Batch Prompt + "
            "Resolution**. Leave Timeline upscaling off.\n"
            "5. Click **queue remaining** on the plan node.\n\n"
            "Each clip is checkpointed only after its MP4 and context sidecar "
            "are saved. The final cut exports automatically when enabled on "
            "**H3 Batch Commit + Final Export**."
        ],
        "widgets_values_named": {},
    }


def build():
    workflow = json.loads(SOURCE.read_text(encoding="utf-8"))
    if any(node["id"] in {PLAN_ID, COMMIT_ID, NOTE_ID}
           for node in workflow["nodes"]):
        raise RuntimeError("Batch node ids already exist in the source")

    # The planner replaces only the per-clip inputs. Resolution still uses the
    # original compact input component, and Timeline still supplies the mode
    # switch used to keep the upscale engine muted.
    replace_link_origin(workflow, 2696, PLAN_ID, 2, "INT")
    replace_link_origin(workflow, 2651, PLAN_ID, 3, "INT")
    replace_link_origin(workflow, 2722, PLAN_ID, 4, "OBVPM_H3_PINSPECS")

    workflow["nodes"] = [node for node in workflow["nodes"] if node["id"] != 765]
    workflow["nodes"].extend([plan_node(), commit_node(), note_node()])

    # Reused link ids were redirected before the new planner existed, so add
    # those three output-side references now. Newly created links are handled
    # by add_link below.
    planner = node_by_id(workflow, PLAN_ID)
    planner["outputs"][2]["links"] = [2696]
    planner["outputs"][3]["links"] = [2651]
    planner["outputs"][4]["links"] = [2722]

    prompt_input = node_by_id(workflow, 761)
    prompt_input["pos"] = [-1040, 5970]
    prompt_input["title"] = "Batch Prompt + Resolution"
    prompt_input["inputs"][0]["link"] = 3038
    prompt_input["inputs"][3]["link"] = 3039

    timeline = node_by_id(workflow, 1221)
    timeline["title"] = "Batch Mode Control — leave upscaling off"
    timeline["outputs"][0]["links"] = []
    timeline["outputs"][1]["links"] = []

    save = node_by_id(workflow, 1216)
    save["inputs"][6]["link"] = 3040
    save["inputs"][9]["link"] = 3041

    add_link(workflow, 3038, PLAN_ID, 0, 761, 0, "STRING")
    add_link(workflow, 3039, PLAN_ID, 5, 761, 3, "STRING")
    add_link(workflow, 3040, PLAN_ID, 6, 1216, 6, "STRING")
    add_link(workflow, 3041, PLAN_ID, 7, 1216, 9, "STRING")
    add_link(workflow, 3042, 1216, 0, COMMIT_ID, 0, "STRING")
    add_link(workflow, 3043, PLAN_ID, 8, COMMIT_ID, 1, "STRING")

    ui_group = next(group for group in workflow["groups"] if group["id"] == 28)
    ui_group["title"] = "OBVPM H3 YAML Batch UI [restore]"
    ui_group["bounding"][3] = 2330
    workflow["groups"].append({
        "id": 34,
        "title": "Batch Checkpoint + Final Export",
        "bounding": [3130, 4770, 430, 370],
        "color": "#3f789e",
        "flags": {},
    })

    workflow["last_node_id"] = NOTE_ID
    workflow["last_link_id"] = 3043
    workflow["id"] = "f5ebfa5b-a853-4f6e-bb64-a02b9517d53c"
    workflow["extra"]["ds"] = {
        "scale": 0.53,
        "offset": [2470, -3160],
    }

    TARGET.write_text(json.dumps(workflow, separators=(",", ":")),
                      encoding="utf-8")


if __name__ == "__main__":
    build()
