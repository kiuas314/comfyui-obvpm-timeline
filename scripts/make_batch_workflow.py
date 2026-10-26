#!/usr/bin/env python3
"""Build the YAML-batch variant of the latest 007A workflow.

The source workflow stays byte-for-byte independent of the batch variant.  We
only replace its supervised prompt, seed, duration and pin-spec wiring, then
attach the transactional batch commit after the existing save node.
"""

import json
import copy
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
SETTINGS_ID = 1634
LORA_ID = 1635
REFERENCE_SELECT_ID = 1636
REFERENCE_NODE_IDS = tuple(range(1637, 1642))


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
        ("content_loras", "STRING"),
        ("reference_images", "STRING"),
    ]
    inputs = []
    for name, input_type in (
            ("manifest_yaml", "STRING"), ("batch_id", "STRING"),
            ("base_folder", "STRING"), ("base_seed", "INT"),
            ("run_selection", "STRING")):
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
        "pos": [-2650, 4710],
        "size": [1310, 2150],
        "flags": {},
        "order": 22,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": "H3 Story + Clip Editor",
        "properties": {"Node name for S&R": "H3BatchPlan"},
        "widgets_values": [DEFAULT_MANIFEST_YAML, DEFAULT_BATCH_ID,
                           DEFAULT_BASE_FOLDER, 0, "[]"],
        "widgets_values_named": {
            "manifest_yaml": DEFAULT_MANIFEST_YAML,
            "batch_id": DEFAULT_BATCH_ID,
            "base_folder": DEFAULT_BASE_FOLDER,
            "base_seed": 0,
            "run_selection": "[]",
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
        {"localized_name": "add_to_timeline", "name": "add_to_timeline",
         "type": "BOOLEAN", "widget": {"name": "add_to_timeline"},
         "link": None},
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
        "pos": [2760, 5070],
        "size": [360, 210],
        "flags": {},
        "order": 86,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": "H3 Batch Commit + Final Export",
        "properties": {"Node name for S&R": "H3BatchCommit"},
        "widgets_values": [True, "full", 19, True],
        "widgets_values_named": {
            "auto_export": True,
            "export_filename_prefix": "full",
            "crf": 19,
            "add_to_timeline": True,
        },
        "color": "#243342",
        "bgcolor": "#354b60",
    }


def settings_node():
    return {
        "id": SETTINGS_ID,
        "type": "H3BatchSettings",
        "pos": [-2650, 4610],
        "size": [1310, 100],
        "flags": {},
        "order": 21,
        "mode": 0,
        "inputs": [
            {"localized_name": "base_folder", "name": "base_folder",
             "type": "STRING", "widget": {"name": "base_folder"},
             "link": None},
            {"localized_name": "upscale_seed", "name": "upscale_seed",
             "type": "INT", "widget": {"name": "upscale_seed"},
             "link": None},
        ],
        "outputs": [
            {"localized_name": "base_folder", "name": "base_folder",
             "type": "STRING", "links": None},
            {"localized_name": "upscale_seed", "name": "upscale_seed",
             "type": "INT", "links": None},
        ],
        "title": "Shared Batch + Upscale Settings",
        "properties": {"Node name for S&R": "H3BatchSettings"},
        "widgets_values": [DEFAULT_BASE_FOLDER, 0],
        "widgets_values_named": {
            "base_folder": DEFAULT_BASE_FOLDER, "upscale_seed": 0},
        "color": "#243342",
        "bgcolor": "#354b60",
    }


def lora_node():
    return {
        "id": LORA_ID,
        "type": "H3BatchLoraApply",
        "pos": [2160, 5140],
        "size": [360, 100],
        "flags": {},
        "order": 78,
        "mode": 0,
        "inputs": [
            {"localized_name": "model", "name": "model", "type": "MODEL",
             "link": 3045},
            {"localized_name": "content_loras", "name": "content_loras",
             "type": "STRING", "link": 3046},
        ],
        "outputs": [{
            "localized_name": "model", "name": "model", "type": "MODEL",
            "links": None,
        }],
        "title": "Scene Content LoRAs (after global stack)",
        "properties": {"Node name for S&R": "H3BatchLoraApply"},
        "color": "#243342",
        "bgcolor": "#354b60",
    }


def reference_select_node():
    inputs = [{
        "localized_name": "reference_images", "name": "reference_images",
        "type": "STRING", "link": 3047,
    }]
    for index in range(9):
        inputs.append({
            "localized_name": "image_%d" % index,
            "name": "image_%d" % index,
            "type": "IMAGE", "link": None,
        })
    outputs = [{
        "localized_name": "ref_image_%d" % index,
        "name": "ref_image_%d" % index,
        "type": "IMAGE", "links": None,
    } for index in range(9)]
    return {
        "id": REFERENCE_SELECT_ID,
        "type": "H3BatchReferenceSelect",
        "pos": [520, 4020],
        "size": [360, 300],
        "flags": {}, "order": 79, "mode": 0,
        "inputs": inputs, "outputs": outputs,
        "title": "Select Storyboard Reference Images",
        "properties": {"Node name for S&R": "H3BatchReferenceSelect"},
        "color": "#243342", "bgcolor": "#354b60",
    }


def extra_reference_nodes(workflow):
    template = node_by_id(workflow, 1280)
    nodes = []
    for index, node_id in enumerate(REFERENCE_NODE_IDS, start=5):
        node = copy.deepcopy(template)
        node["id"] = node_id
        node["pos"] = [770 + (index - 5) * 510, 3860]
        node["order"] = 32 + index - 5
        node["title"] = "Picture %d - Load Images & Compose (obvpm)" % index
        for output in node.get("outputs", []):
            output["links"] = None
        for input_port in node.get("inputs", []):
            input_port["link"] = None
        nodes.append(node)
    return nodes


def note_node():
    return {
        "id": NOTE_ID,
        "type": "MarkdownNote",
        "pos": [-1040, 6480],
        "size": [470, 350],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "title": "YAML batch quick start",
        "properties": {"Node name for S&R": "MarkdownNote"},
        "widgets_values": [
            "## Story editor + unattended generation\n\n"
            "A three-clip castle dance demo is already loaded. It contains "
            "one independent establishing shot, then two ballroom clips that "
            "share context and end with a kiss.\n\n"
            "Load the princess reference into **Picture 1** and the prince "
            "reference into **Picture 2** in the Refs group.\n\n"
            "1. Edit clips and optional blocks in **H3 Story + Clip "
            "Editor**, or import an existing YAML screenplay.\n"
            "2. Choose a new `batch_id`; keep it unchanged to resume.\n"
            "3. Set **Shared Batch + Upscale Settings** once.\n"
            "4. Set aspect ratio and megapixels in **Batch Prompt + "
            "Resolution**. Leave Timeline upscaling off.\n"
            "5. Select a clip, then generate that clip, its root-shot "
            "segment, or the whole movie.\n\n"
            "The compiled H3 prompt is shown beneath every clip for "
            "debugging. YAML remains available for import, export, and "
            "advanced source editing. Scene content LoRAs are applied after "
            "the existing global Power LoRA stack.\n\n"
            "Each clip is checkpointed only after its MP4 and context sidecar "
            "are saved, then added to Timeline through the same lineage-aware "
            "operation as its manual add button. The final cut exports "
            "automatically when enabled on "
            "**H3 Batch Commit + Final Export**. After generation completes, "
            "turn Timeline upscaling on and use the normal Queue/Run button "
            "once; the completed planner is not part of that pass."
        ],
        "widgets_values_named": {},
    }


def build():
    workflow = json.loads(SOURCE.read_text(encoding="utf-8"))
    if any(node["id"] in {PLAN_ID, COMMIT_ID, NOTE_ID, SETTINGS_ID, LORA_ID,
                           REFERENCE_SELECT_ID, *REFERENCE_NODE_IDS}
           for node in workflow["nodes"]):
        raise RuntimeError("Batch node ids already exist in the source")

    # The planner replaces only the per-clip inputs. Resolution still uses the
    # original compact input component, and Timeline still supplies the mode
    # switch used to keep the upscale engine muted.
    replace_link_origin(workflow, 2730, PLAN_ID, 2, "INT")
    # Length goes straight to the generator. Keeping it in Timeline's shared
    # mode bundle would make the already-complete planner execute again during
    # the later upscale-only pass.
    replace_link_origin(workflow, 3036, PLAN_ID, 3, "INT")
    replace_link_origin(workflow, 2722, PLAN_ID, 4, "OBVPM_H3_PINSPECS")
    # The original combined UI component also emits base_folder, but its
    # prompt input now comes from the planner. Drive both folder consumers
    # directly so an upscale-only prompt never has to evaluate that component.
    replace_link_origin(workflow, 2562, SETTINGS_ID, 0, "STRING")
    replace_link_origin(workflow, 2698, SETTINGS_ID, 0, "STRING")
    replace_link_origin(workflow, 2696, SETTINGS_ID, 1, "INT")
    # Add scene-specific content LoRAs only to generation. The existing Power
    # LoRA Loader remains the project-wide baseline, and Timeline upscaling
    # continues to use the shared optimized model without a planner dependency.
    replace_link_origin(workflow, 2727, LORA_ID, 0, "MODEL")
    # The four existing storyboard picture loaders feed the selector. The
    # selector emits only the slots named by the active clip's location/cast.
    for link_id, output_slot in zip((2314, 2315, 2316, 2317), range(4)):
        replace_link_origin(workflow, link_id, REFERENCE_SELECT_ID,
                            output_slot, "IMAGE")

    workflow["nodes"] = [node for node in workflow["nodes"] if node["id"] != 765]
    workflow["nodes"].extend(
        [settings_node(), plan_node(), lora_node(), reference_select_node(),
         commit_node(), note_node()])
    workflow["nodes"].extend(extra_reference_nodes(workflow))

    # Reused link ids were redirected before the new planner existed, so add
    # those three output-side references now. Newly created links are handled
    # by add_link below.
    planner = node_by_id(workflow, PLAN_ID)
    planner["outputs"][2]["links"] = [2730]
    planner["outputs"][3]["links"] = [3036]
    planner["outputs"][4]["links"] = [2722]
    planner["outputs"][11]["links"] = [3046]
    planner["outputs"][12]["links"] = [3047]
    reference_selector = node_by_id(workflow, REFERENCE_SELECT_ID)
    reference_selector["outputs"][0]["links"] = [2314]
    reference_selector["outputs"][1]["links"] = [2315]
    reference_selector["outputs"][2]["links"] = [2316]
    reference_selector["outputs"][3]["links"] = [2317]
    node_by_id(workflow, LORA_ID)["outputs"][0]["links"] = [2727]
    shared = node_by_id(workflow, SETTINGS_ID)
    shared["outputs"][0]["links"] = [2562, 2698]
    shared["outputs"][1]["links"] = [2696]

    prompt_input = node_by_id(workflow, 761)
    prompt_input["pos"] = [-1040, 5970]
    prompt_input["title"] = "Batch Prompt + Resolution"
    prompt_input["inputs"][0]["link"] = 3038

    timeline = node_by_id(workflow, 1221)
    timeline["title"] = "Batch Mode Control — leave upscaling off"
    timeline["outputs"][0]["links"] = []

    # Keep the dense resolution table out of both working groups. It remains
    # nearby for reference without competing with the large YAML editor.
    resolution_reference = node_by_id(workflow, 118)
    resolution_reference["pos"] = [-1560, 6950]

    save = node_by_id(workflow, 1216)
    save["inputs"][6]["link"] = 3040
    save["inputs"][9]["link"] = 3041

    # Both result windows stay available. Frontend routing follows the mode of
    # their upstream Set node, so generation and upscale results cannot claim
    # one another.
    upscale_preview = node_by_id(workflow, 1342)
    upscale_preview["mode"] = 0
    upscale_preview["title"] = "H3 Upscale Result"

    add_link(workflow, 3038, PLAN_ID, 0, 761, 0, "STRING")
    add_link(workflow, 3040, PLAN_ID, 6, 1216, 6, "STRING")
    add_link(workflow, 3041, PLAN_ID, 7, 1216, 9, "STRING")
    add_link(workflow, 3042, 1216, 0, COMMIT_ID, 0, "STRING")
    add_link(workflow, 3043, PLAN_ID, 8, COMMIT_ID, 1, "STRING")
    add_link(workflow, 3044, SETTINGS_ID, 0, PLAN_ID, 2, "STRING")
    add_link(workflow, 3045, 1489, 0, LORA_ID, 0, "MODEL")
    add_link(workflow, 3046, PLAN_ID, 11, LORA_ID, 1, "STRING")
    add_link(workflow, 3047, PLAN_ID, 12, REFERENCE_SELECT_ID, 0, "STRING")
    add_link(workflow, 3048, 1280, 0, REFERENCE_SELECT_ID, 1, "IMAGE")
    add_link(workflow, 3049, 1282, 0, REFERENCE_SELECT_ID, 2, "IMAGE")
    add_link(workflow, 3050, 1283, 0, REFERENCE_SELECT_ID, 3, "IMAGE")
    add_link(workflow, 3051, 1284, 0, REFERENCE_SELECT_ID, 4, "IMAGE")
    for offset, node_id in enumerate(REFERENCE_NODE_IDS):
        add_link(workflow, 3052 + offset, node_id, 0,
                 REFERENCE_SELECT_ID, 5 + offset, "IMAGE")
    for offset in range(5):
        add_link(workflow, 3057 + offset, REFERENCE_SELECT_ID, 4 + offset,
                 797, 7 + offset, "IMAGE")

    ui_group = next(group for group in workflow["groups"] if group["id"] == 28)
    ui_group["title"] = "OBVPM H3 YAML Batch UI [restore]"
    ui_group["bounding"][3] = 2330
    workflow["groups"].append({
        "id": 35,
        "title": "H3 Story + Clip Editor",
        "bounding": [-2690, 4570, 1390, 2330],
        "color": "#3f789e",
        "flags": {},
    })
    workflow["last_node_id"] = REFERENCE_NODE_IDS[-1]
    workflow["last_link_id"] = 3061
    workflow["id"] = "f5ebfa5b-a853-4f6e-bb64-a02b9517d53c"
    workflow["extra"]["ds"] = {
        "scale": 0.53,
        "offset": [2470, -3160],
    }

    TARGET.write_text(json.dumps(workflow, separators=(",", ":")),
                      encoding="utf-8")


if __name__ == "__main__":
    build()
