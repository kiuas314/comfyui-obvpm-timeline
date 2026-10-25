"""Unattended, YAML-driven H3 clip generation.

The batch is deliberately split in two. ``H3BatchPlan`` reads the next
unfinished manifest item and prepares the prompt/pins. ``H3BatchCommit`` is
wired after the save node and advances the checkpoint only after both the MP4
and its sidecar exist.  A cancelled or failed prompt therefore retries the
same item instead of silently leaving a hole in the film.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import threading

import folder_paths

from . import compat
from . import mctx
from . import wiretypes as wt
from . import batch_prompt
from .batch_example import (DEFAULT_BASE_FOLDER, DEFAULT_BATCH_ID,
                            DEFAULT_MANIFEST_YAML)
from .nodes_assemble import H3Timeline

_LOG = logging.getLogger("obvpm.h3")
_STATE_VERSION = 1
_LOCK = threading.RLock()
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def _load_yaml(text, source="manifest"):
    """Parse YAML safely, with a useful install error.

    JSON remains a valid fallback because it is a subset of YAML.  This makes
    diagnostics and minimal installations usable while PyYAML is being added;
    block scalars and normal YAML syntax require the declared dependency.
    """
    try:
        import yaml
    except ImportError:
        try:
            return json.loads(text)
        except ValueError:
            raise RuntimeError(
                "H3 batch manifests need PyYAML. Install this node pack's "
                "dependencies (pip install PyYAML) and restart ComfyUI.")
    try:
        return yaml.safe_load(text)
    except Exception as exc:
        raise ValueError("H3 batch: invalid YAML in %s: %s" % (source, exc))


def _as_mapping(value, where):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("H3 batch: %s must be a mapping." % where)
    return dict(value)


def parse_manifest(text, source="manifest"):
    """Validate and normalise a manifest without touching batch state."""
    raw = _load_yaml(text, source)
    if isinstance(raw, list):
        raw = {"clips": raw}
    root = _as_mapping(raw, "the manifest root")
    defaults = _as_mapping(root.get("defaults"), "defaults")
    clips = root.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("H3 batch: 'clips' must be a non-empty list.")
    version = int(root.get("version", 1))
    if version not in (1, 2):
        raise ValueError("H3 batch: unsupported manifest version %s."
                         % version)

    globals_ = None
    if version == 2:
        allowed_root = {
            "version", "project", "characters", "locations", "audio",
            "defaults", "clips",
        }
        unknown_root = sorted(set(root) - allowed_root)
        if unknown_root:
            raise ValueError("H3 batch: manifest has unknown fields: %s."
                             % ", ".join(unknown_root))
        globals_ = batch_prompt.normalize_globals(root)

    allowed_defaults = {
        "negative_prompt", "duration_seconds", "context", "window",
        "mode", "seed", "filename_prefix", "metadata",
    }
    if version == 2:
        allowed_defaults |= batch_prompt.STRUCTURED_DEFAULT_FIELDS
    unknown = sorted(set(defaults) - allowed_defaults)
    if unknown:
        raise ValueError("H3 batch: unknown defaults: %s."
                         % ", ".join(unknown))

    out, seen = [], set()
    for index, item in enumerate(clips):
        clip = _as_mapping(item, "clips[%d]" % index)
        allowed_clip = allowed_defaults | {"id", "prompt"}
        if version == 2:
            allowed_clip |= batch_prompt.STRUCTURED_CLIP_FIELDS
        unknown = sorted(set(clip) - allowed_clip)
        if unknown:
            raise ValueError("H3 batch: clip %d has unknown fields: %s."
                             % (index, ", ".join(unknown)))
        merged = dict(defaults)
        merged.update(clip)
        clip_id = str(merged.get("id") or "").strip()
        if not _ID_RE.match(clip_id):
            raise ValueError(
                "H3 batch: clips[%d].id must start with a letter or number "
                "and contain only letters, numbers, '.', '_' or '-'." % index)
        if clip_id in seen:
            raise ValueError("H3 batch: duplicate clip id %r." % clip_id)
        context = merged.get("context", "none" if index == 0 else "previous")
        context_opts = {}
        if isinstance(context, dict):
            context_opts = dict(context)
            context = context_opts.pop("from", "previous")
        if context is None or context is False:
            context = "none"
        context = str(context).strip()
        if context not in ("none", "previous"):
            if context not in seen:
                raise ValueError(
                    "H3 batch: clip %r refers to context %r, which must be "
                    "an earlier clip id, 'previous', or 'none'."
                    % (clip_id, context))
        seen.add(clip_id)
        allowed_context = {"window", "mode", "cut"}
        extra = sorted(set(context_opts) - allowed_context)
        if extra:
            raise ValueError("H3 batch: clip %r has unknown context fields: %s."
                             % (clip_id, ", ".join(extra)))

        duration = float(merged.get("duration_seconds", 8.0))
        if not 0.2 <= duration <= 150.0:
            raise ValueError("H3 batch: clip %r duration_seconds must be "
                             "between 0.2 and 150." % clip_id)
        window = str(context_opts.get("window", merged.get("window", "39")))
        from . import frames as fr
        if window not in fr.WINDOW_CHOICES:
            raise ValueError("H3 batch: clip %r window must be one of %s."
                             % (clip_id, "/".join(fr.WINDOW_CHOICES)))
        mode = str(context_opts.get("mode", merged.get("mode", "masked")))
        if mode not in ("masked", "guide", "both"):
            raise ValueError("H3 batch: clip %r mode must be masked, guide, "
                             "or both." % clip_id)
        cut = context_opts.get("cut")
        if cut is not None and int(cut) < 0:
            raise ValueError("H3 batch: clip %r context.cut cannot be negative."
                             % clip_id)
        seed = merged.get("seed")
        if seed is not None and not 0 <= int(seed) < 2 ** 64:
            raise ValueError("H3 batch: clip %r seed must be a uint64." % clip_id)
        prefix = str(merged.get("filename_prefix") or clip_id).strip()
        if not prefix or "/" in prefix or "\\" in prefix:
            raise ValueError("H3 batch: clip %r filename_prefix must be a "
                             "single filename component." % clip_id)
        metadata = merged.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("H3 batch: clip %r metadata must be a mapping."
                             % clip_id)

        if version == 1:
            prompt = merged.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("H3 batch: clip %r needs a non-empty prompt."
                                 % clip_id)
            prompt = prompt.strip()
            negative_prompt = str(merged.get("negative_prompt") or "")
        else:
            prompt = batch_prompt.compile_prompt(
                globals_, clip, defaults, context, duration, clip_id)
            negative_prompt = str(
                merged.get("negative_prompt")
                or globals_["project"].get("negative_prompt") or "")

        out.append({
            "id": clip_id,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration_seconds": duration,
            "context": context,
            "window": window,
            "mode": mode,
            "cut": None if cut is None else int(cut),
            "seed": None if seed is None else int(seed),
            "filename_prefix": prefix,
            "metadata": dict(metadata or {}),
        })
    result = {"version": version, "clips": out}
    if globals_ is not None:
        result["authoring"] = globals_
    return result


def load_manifest(yaml_text):
    """Parse and identify a manifest pasted into the workflow."""
    yaml_text = str(yaml_text or "")
    if not yaml_text.strip():
        raise ValueError("H3 batch: manifest_yaml is empty. Paste the complete "
                         "YAML manifest into H3 Batch Plan.")
    source = "<pasted YAML>"
    manifest = parse_manifest(yaml_text, source)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    return manifest, hashlib.sha256(canonical).hexdigest(), source


def _folder_text(value):
    return str(value or "").strip().replace("\\", "/").strip("/")


def _state_path(base_folder, batch_id):
    batch_id = str(batch_id or "").strip()
    if not _ID_RE.match(batch_id):
        raise ValueError("H3 batch: batch_id must start with a letter or "
                         "number and contain only letters, numbers, '.', "
                         "'_' or '-'.")
    root = os.path.abspath(folder_paths.get_output_directory())
    folder = os.path.abspath(os.path.join(root, _folder_text(base_folder)))
    if os.path.commonpath([root, folder]) != root:
        raise ValueError("H3 batch: base_folder escapes the output folder.")
    key = hashlib.sha256(batch_id.encode("utf-8")).hexdigest()[:20]
    return os.path.join(folder, ".obvpm_batch", key + ".json")


def _read_state(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def _write_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".batch-", suffix=".tmp",
                               dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def _new_state(batch_id, manifest_hash, manifest_source):
    return {
        "version": _STATE_VERSION,
        "batch_id": batch_id,
        "manifest_hash": manifest_hash,
        "manifest_source": manifest_source,
        "completed": [],
        "active": None,
        "final_path": "",
    }


def _validated_state(path, batch_id, manifest_hash, manifest_source):
    state = _read_state(path)
    if state is None:
        state = _new_state(batch_id, manifest_hash, manifest_source)
        _write_state(path, state)
    if state.get("version") != _STATE_VERSION:
        raise ValueError("H3 batch: checkpoint %s has an unsupported version."
                         % path)
    if state.get("batch_id") != batch_id:
        raise ValueError("H3 batch: checkpoint id mismatch at %s." % path)
    if state.get("manifest_hash") != manifest_hash:
        raise ValueError(
            "H3 batch: this manifest changed after batch %r started. Use a "
            "new batch_id to start the revised film; the existing takes "
            "and checkpoint were left untouched." % batch_id)
    return state


def _completed_map(state):
    return {str(one["id"]): str(one["path"])
            for one in state.get("completed", [])}


def _relative_clip(path):
    root = os.path.abspath(folder_paths.get_output_directory())
    absolute = os.path.abspath(str(path or ""))
    if not os.path.isabs(str(path or "")):
        absolute = os.path.abspath(os.path.join(root, str(path)))
    if os.path.commonpath([root, absolute]) != root:
        raise ValueError("H3 batch: saved clip is outside the output folder: %s"
                         % absolute)
    return os.path.relpath(absolute, root).replace(os.sep, "/")


def batch_status(manifest_yaml, batch_id, base_folder):
    manifest, digest, source = load_manifest(manifest_yaml)
    path = _state_path(base_folder, batch_id)
    with _LOCK:
        state = _validated_state(path, batch_id, digest, source)
        completed = _completed_map(state)
        pending = [c["id"] for c in manifest["clips"]
                   if c["id"] not in completed]
        return {
            "total": len(manifest["clips"]),
            "completed": len(completed),
            "remaining": len(pending),
            "next": pending[0] if pending else None,
            "active": (state.get("active") or {}).get("id"),
            "final_path": state.get("final_path") or "",
            "export_error": state.get("export_error") or "",
            "state_path": path,
        }


def register():
    """Register the small read-only status route used by the queue button."""
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.post("/obvpm/h3/batch_status")
    async def _batch_status(request):
        import asyncio
        try:
            data = await request.json()
            found = await asyncio.to_thread(
                batch_status, str(data.get("manifest_yaml", "")),
                str(data.get("batch_id", "")),
                str(data.get("base_folder", "")))
            # The absolute checkpoint path is useful in Python errors but is
            # not sent to a browser that only needs counts and state.
            found.pop("state_path", None)
            return web.json_response(found)
        except Exception as exc:
            _LOG.info("obvpm.h3: batch_status failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=400)


class H3BatchPlan:
    CATEGORY = "obvpm/h3/batch"
    FUNCTION = "plan"
    RETURN_TYPES = ("STRING", "STRING", "INT", "INT", wt.PINSPECS,
                    "STRING", "STRING", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("prompt", "negative_prompt", "seed", "length",
                    "pin_specs", "base_folder", "filename_prefix",
                    "metadata", "ticket", "index", "total")
    DESCRIPTION = (
        "Reads the next unfinished clip from YAML pasted into the node. Queue "
        "this workflow once per remaining clip; H3 Batch Commit "
        "checkpoints each successful save, so an interruption resumes the "
        "same item.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "manifest_yaml": ("STRING", {
                "default": DEFAULT_MANIFEST_YAML, "multiline": True,
                "dynamicPrompts": False,
                "tooltip": "Paste the complete YAML manifest here. It is "
                           "saved inside the ComfyUI workflow."}),
            "batch_id": ("STRING", {
                "default": DEFAULT_BATCH_ID,
                "tooltip": "Checkpoint identity. Change it to start a new "
                           "run; keep it unchanged to resume."}),
            "base_folder": ("STRING", {
                "default": DEFAULT_BASE_FOLDER,
                "tooltip": "Output-relative folder for clips, final export, "
                           "and the hidden batch checkpoint."}),
            "base_seed": ("INT", {
                "default": 0, "min": 0, "max": 2 ** 64 - 1,
                "tooltip": "Used as base_seed + clip index when a clip has "
                           "no explicit seed."}),
        }}

    @classmethod
    def IS_CHANGED(cls, **_):
        # The checkpoint changes between otherwise-identical queued prompts.
        return float("nan")

    def plan(self, manifest_yaml, batch_id, base_folder, base_seed=0):
        compat.require()
        manifest, digest, source = load_manifest(manifest_yaml)
        state_path = _state_path(base_folder, batch_id)
        with _LOCK:
            state = _validated_state(state_path, batch_id, digest, source)
            completed = _completed_map(state)
            index = next((i for i, c in enumerate(manifest["clips"])
                          if c["id"] not in completed), None)
            if index is None:
                raise RuntimeError(
                    "H3 batch %r is complete (%d/%d clips)."
                    % (batch_id, len(completed), len(manifest["clips"])))
            clip = manifest["clips"][index]
            active = state.get("active")
            if active and (active.get("id") != clip["id"]
                           or int(active.get("index", -1)) != index):
                raise RuntimeError("H3 batch: checkpoint has an unexpected "
                                   "active item; use a new batch_id or inspect "
                                   "%s." % state_path)
            if not active:
                state["active"] = {"id": clip["id"], "index": index}
                _write_state(state_path, state)

        context_id = clip["context"]
        if context_id == "previous":
            context_id = manifest["clips"][index - 1]["id"] if index else "none"
        specs = []
        context_path = ""
        if context_id != "none":
            context_path = completed.get(context_id, "")
            if not context_path:
                raise RuntimeError("H3 batch: context %r for clip %r has not "
                                   "completed." % (context_id, clip["id"]))
            specs = H3Timeline()._specs_for(
                context_path, "extend", clip["window"], clip["cut"],
                pin_mode=clip["mode"])

        masks = bool(specs and clip["mode"] in ("masked", "both"))
        length = H3Timeline._run_length(clip["duration_seconds"], masks)
        seed = clip["seed"]
        if seed is None:
            seed = (int(base_seed) + index) % (2 ** 64)
        metadata = dict(clip["metadata"])
        metadata.update({
            "batch_id": batch_id,
            "batch_manifest_version": manifest["version"],
            "clip_id": clip["id"],
            "clip_index": index,
            "prompt": clip["prompt"],
            "seed": seed,
        })
        if manifest["version"] == 2:
            metadata["prompt_format"] = "h3_base"
        ticket = json.dumps({
            "version": _STATE_VERSION,
            "batch_id": batch_id,
            "manifest_hash": digest,
            "manifest_source": source,
            "base_folder": _folder_text(base_folder),
            "clip_id": clip["id"],
            "index": index,
            "total": len(manifest["clips"]),
            "metadata": metadata,
            "context_id": context_id,
            "context_path": context_path,
        }, separators=(",", ":"), ensure_ascii=False)
        _LOG.info("obvpm.h3: batch %s clip %d/%d %s (%s)", batch_id,
                  index + 1, len(manifest["clips"]), clip["id"],
                  "root" if not context_path else "extends " + context_id)
        return (clip["prompt"], clip["negative_prompt"], seed, length,
                specs, _folder_text(base_folder), clip["filename_prefix"],
                json.dumps(metadata, separators=(",", ":"),
                           ensure_ascii=False),
                ticket, index + 1, len(manifest["clips"]))


class H3BatchCommit:
    CATEGORY = "obvpm/h3/batch"
    FUNCTION = "commit"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING", "INT", "INT")
    RETURN_NAMES = ("sequence", "complete", "final_path", "completed", "total")
    DESCRIPTION = (
        "Wire the H3 save path and H3 Batch Plan ticket here. It advances the "
        "checkpoint only after the MP4 and mctx sidecar exist. On the final "
        "clip it can build and export the complete timeline automatically.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "path": ("STRING", {"forceInput": True}),
            "ticket": ("STRING", {"forceInput": True}),
            "auto_export": ("BOOLEAN", {"default": True}),
            "export_filename_prefix": ("STRING", {"default": "full"}),
            "crf": ("INT", {"default": 19, "min": 0, "max": 51}),
            "add_to_timeline": ("BOOLEAN", {
                "default": True,
                "tooltip": "After each successful commit, use the open "
                           "Timeline's normal lineage-aware add operation."}),
        }}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def commit(self, path, ticket, auto_export=True,
               export_filename_prefix="full", crf=19, add_to_timeline=True):
        try:
            item = json.loads(ticket)
        except (TypeError, ValueError):
            raise ValueError("H3 batch: invalid commit ticket.")
        if item.get("version") != _STATE_VERSION:
            raise ValueError("H3 batch: commit ticket version mismatch.")
        digest = item.get("manifest_hash")
        source = item.get("manifest_source") or "<pasted YAML>"
        total = int(item.get("total", 0))
        if not digest or total < 1:
            raise ValueError("H3 batch: manifest ticket is missing its "
                             "identity or clip count.")
        rel = _relative_clip(path)
        absolute = os.path.join(folder_paths.get_output_directory(), rel)
        if not os.path.isfile(absolute):
            raise ValueError("H3 batch: saved clip does not exist: %s" % absolute)
        if not os.path.isfile(mctx.sidecar_path(absolute)):
            raise ValueError("H3 batch: saved clip has no mctx sidecar: %s"
                             % absolute)

        state_path = _state_path(item.get("base_folder"), item.get("batch_id"))
        with _LOCK:
            state = _validated_state(state_path, item["batch_id"], digest,
                                     source)
            active = state.get("active") or {}
            if (active.get("id") != item.get("clip_id")
                    or int(active.get("index", -1)) != int(item.get("index", -2))):
                # Idempotence for a cached/replayed commit of the same path.
                done = _completed_map(state)
                if done.get(str(item.get("clip_id"))) != rel:
                    raise RuntimeError("H3 batch: commit does not match the "
                                       "active checkpoint item.")
            else:
                state.setdefault("completed", []).append({
                    "id": item["clip_id"],
                    "index": int(item["index"]),
                    "path": rel,
                    "metadata": item.get("metadata") or {},
                })
                state["active"] = None
                _write_state(state_path, state)
            completed = sorted(state.get("completed", []),
                               key=lambda one: int(one["index"]))

        sequence = "\n".join(one["path"] for one in completed)
        complete = len(completed) == total
        final_path = state.get("final_path") or ""
        export_error = ""
        if complete and auto_export and not final_path:
            try:
                from .preview_route import export_cut
                preview_name = ".obvpm_batch_%s" % hashlib.sha256(
                    item["batch_id"].encode("utf-8")).hexdigest()[:12]
                final_path, _ = export_cut(
                    sequence, int(crf), item.get("base_folder", ""),
                    preview_name, export_filename_prefix)
                with _LOCK:
                    state = _validated_state(
                        state_path, item["batch_id"], digest, source)
                    state["final_path"] = final_path
                    state.pop("export_error", None)
                    _write_state(state_path, state)
            except Exception as exc:
                # The expensive part succeeded: do not turn a delivery error
                # into another generation of the last clip.  The sequence is
                # returned for H3 Assemble/Timeline and the checkpoint records
                # a clear reason for the missing final file.
                export_error = "%s: %s" % (type(exc).__name__, exc)
                _LOG.exception("obvpm.h3: batch %s completed, but final "
                               "export failed", item["batch_id"])
                with _LOCK:
                    state = _validated_state(
                        state_path, item["batch_id"], digest, source)
                    state["export_error"] = export_error
                    _write_state(state_path, state)
        status = {
            "batch_id": item["batch_id"], "clip_id": item["clip_id"],
            "path": rel, "add_to_timeline": bool(add_to_timeline),
            "completed": len(completed), "total": total,
            "complete": complete, "final_path": final_path,
            "export_error": export_error,
        }
        return {"ui": {"batch": [status]},
                "result": (sequence, complete, final_path,
                           len(completed), total)}
