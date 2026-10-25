"""Structured YAML -> MiniMax H3 base prompt compiler.

This module has no ComfyUI imports so the authoring format can be validated in
small unit tests and by external tools. It targets H3's base
T2VA/I2VA/FL2VA/L2VA prompt format, including explicit Subject-to-Picture
bindings for reference-image characters. Reference asset order is owned by
the workflow that supplies those images.
"""

import re

_SPEAKER_RE = re.compile(r"^S[1-9][0-9]*$")

PROJECT_FIELDS = {
    "title", "prompt_format", "language", "visual_style", "story_context",
    "continuity", "negative_prompt",
}
CHARACTER_FIELDS = {
    "name", "speaker_id", "reference_image", "appearance", "wardrobe", "voice",
}
LOCATION_FIELDS = {"description", "soundscape"}
AUDIO_FIELDS = {"default_soundscape", "default_music", "music"}
STRUCTURED_DEFAULT_FIELDS = {"cast", "location", "music", "camera", "soundscape"}
STRUCTURED_CLIP_FIELDS = {
    "raw_prompt", "cast", "location", "music", "camera", "soundscape",
    "continuity", "shot", "shots", "dialogue", "character_overrides",
    "detailed_description",
}
SHOT_FIELDS = {
    "at", "framing", "action", "camera", "cast", "dialogue", "transition",
}
DIALOGUE_FIELDS = {"speaker", "text", "language", "delivery", "voiceover"}
CAMERA_FIELDS = {"movement", "amplitude", "speed", "target"}

_MOTIONS = {
    "static": "holds a static shot",
    "push_in": "pushes in",
    "pull_out": "pulls out",
    "zoom_in": "zooms in",
    "zoom_out": "zooms out",
    "pan_left": "pans left",
    "pan_right": "pans right",
    "truck_left": "trucks left",
    "truck_right": "trucks right",
    "tilt_up": "tilts up",
    "tilt_down": "tilts down",
    "pedestal_up": "pedestals up",
    "pedestal_down": "pedestals down",
    "arc": "moves in an arc around the subject",
    "tracking": "tracks the subject",
    "handheld": "moves with restrained handheld motion",
    "shake_slightly": "shakes slightly",
    "shake_strongly": "shakes strongly",
    "pov": "holds the subject's point of view",
    "roll_clockwise": "rolls clockwise",
    "roll_counterclockwise": "rolls counterclockwise",
}


def _mapping(value, where):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("H3 batch: %s must be a mapping." % where)
    return dict(value)


def _unknown(mapping, allowed, where):
    extra = sorted(set(mapping) - set(allowed))
    if extra:
        raise ValueError("H3 batch: %s has unknown fields: %s."
                         % (where, ", ".join(extra)))


def _clean(value):
    return str(value or "").strip()


def normalize_globals(root):
    """Validate and normalize v2 project/character/location/audio libraries."""
    project = _mapping(root.get("project"), "project")
    _unknown(project, PROJECT_FIELDS, "project")
    prompt_format = _clean(project.get("prompt_format") or "h3_base")
    if prompt_format != "h3_base":
        raise ValueError("H3 batch: project.prompt_format must be h3_base.")
    project["prompt_format"] = prompt_format
    project["language"] = _clean(project.get("language") or "English")
    for field in ("title", "visual_style", "story_context", "continuity",
                  "negative_prompt"):
        project[field] = _clean(project.get(field))

    characters = {}
    speaker_ids = {}
    reference_images = {}
    for key, value in _mapping(root.get("characters"), "characters").items():
        char_id = _clean(key)
        if not char_id:
            raise ValueError("H3 batch: character ids cannot be empty.")
        char = _mapping(value, "character %r" % char_id)
        _unknown(char, CHARACTER_FIELDS, "character %r" % char_id)
        char = {field: _clean(char.get(field)) for field in CHARACTER_FIELDS
                if field != "reference_image"}
        reference_image = value.get("reference_image")
        if reference_image in (None, ""):
            reference_image = None
        else:
            try:
                reference_image = int(reference_image)
            except (TypeError, ValueError):
                raise ValueError("H3 batch: character %r reference_image must "
                                 "be a picture number from 1 to 9." % char_id)
            if not 1 <= reference_image <= 9:
                raise ValueError("H3 batch: character %r reference_image must "
                                 "be a picture number from 1 to 9." % char_id)
            if reference_image in reference_images:
                raise ValueError(
                    "H3 batch: characters %r and %r both use Picture %d."
                    % (reference_images[reference_image], char_id,
                       reference_image))
            reference_images[reference_image] = char_id
        char["reference_image"] = reference_image
        char["name"] = char["name"] or char_id.replace("_", " ").title()
        sid = char["speaker_id"].strip("()")
        if sid and not _SPEAKER_RE.match(sid):
            raise ValueError("H3 batch: character %r speaker_id must look like "
                             "S1, S2, and so on." % char_id)
        if sid in speaker_ids:
            raise ValueError("H3 batch: characters %r and %r both use %s."
                             % (speaker_ids[sid], char_id, sid))
        if sid:
            speaker_ids[sid] = char_id
        char["speaker_id"] = sid
        characters[char_id] = char

    locations = {}
    for key, value in _mapping(root.get("locations"), "locations").items():
        loc_id = _clean(key)
        if isinstance(value, str):
            value = {"description": value}
        loc = _mapping(value, "location %r" % loc_id)
        _unknown(loc, LOCATION_FIELDS, "location %r" % loc_id)
        locations[loc_id] = {field: _clean(loc.get(field))
                             for field in LOCATION_FIELDS}

    audio = _mapping(root.get("audio"), "audio")
    _unknown(audio, AUDIO_FIELDS, "audio")
    music = _mapping(audio.get("music"), "audio.music")
    audio = {
        "default_soundscape": _clean(audio.get("default_soundscape")),
        "default_music": _clean(audio.get("default_music")),
        "music": {str(k): _clean(v) for k, v in music.items()},
    }
    return {"project": project, "characters": characters,
            "locations": locations, "audio": audio}


def _cast(value, characters, where):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("H3 batch: %s must be a list of character ids." % where)
    out = []
    for item in value:
        char_id = _clean(item)
        if char_id not in characters:
            raise ValueError("H3 batch: %s names unknown character %r."
                             % (where, char_id))
        if char_id not in out:
            out.append(char_id)
    return out


def _location(value, locations, where):
    if value is None or value == "":
        return {"description": "", "soundscape": ""}
    if isinstance(value, str):
        key = value.strip()
        if key not in locations:
            raise ValueError("H3 batch: %s names unknown location %r."
                             % (where, key))
        return dict(locations[key])
    loc = _mapping(value, where)
    _unknown(loc, LOCATION_FIELDS, where)
    return {field: _clean(loc.get(field)) for field in LOCATION_FIELDS}


def _camera(value, base=None, where="camera"):
    camera = dict(base or {})
    camera.update(_mapping(value, where))
    _unknown(camera, CAMERA_FIELDS, where)
    motion = _clean(camera.get("movement") or "static").lower().replace(" ", "_")
    if motion not in _MOTIONS:
        raise ValueError("H3 batch: %s movement %r is not supported."
                         % (where, motion))
    amplitude = _clean(camera.get("amplitude") or "normal").lower()
    speed = _clean(camera.get("speed") or "normal").lower()
    if amplitude not in ("small", "normal", "large"):
        raise ValueError("H3 batch: %s amplitude must be small, normal, or "
                         "large." % where)
    if speed not in ("slow", "normal", "fast"):
        raise ValueError("H3 batch: %s speed must be slow, normal, or fast."
                         % where)
    return {"movement": motion, "amplitude": amplitude, "speed": speed,
            "target": _clean(camera.get("target"))}


def _camera_sentence(camera):
    phrase = "The camera " + _MOTIONS[camera["movement"]]
    if camera["amplitude"] != "normal" and camera["movement"] != "static":
        phrase += " with %s amplitude" % camera["amplitude"]
    if camera["speed"] != "normal" and camera["movement"] != "static":
        phrase += " at %s speed" % camera["speed"]
    if camera["target"]:
        phrase += " toward %s" % camera["target"]
    return phrase + "."


def _timestamp(value, duration, previous, where):
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = _clean(value)
        pieces = text.split(":")
        try:
            if len(pieces) == 2:
                seconds = float(pieces[0]) * 60 + float(pieces[1])
            else:
                seconds = float(text)
        except ValueError:
            raise ValueError("H3 batch: %s timestamp %r is invalid."
                             % (where, value))
    if not previous < seconds < duration:
        raise ValueError("H3 batch: %s timestamp %.3f must be after %.3f and "
                         "before the %.3fs clip end."
                         % (where, seconds, previous, duration))
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return seconds, "%02d:%06.3f" % (minutes, remainder)


def _character(char_id, globals_, overrides):
    char = dict(globals_["characters"][char_id])
    override = _mapping(overrides.get(char_id),
                        "character_overrides.%s" % char_id)
    _unknown(override, CHARACTER_FIELDS,
             "character_overrides.%s" % char_id)
    for key, value in override.items():
        if key in ("speaker_id", "reference_image"):
            raise ValueError("H3 batch: character_overrides cannot change a "
                             "stable speaker_id or reference_image.")
        char[key] = _clean(value)
    return char


def _character_definition(char):
    if char.get("reference_image"):
        label = "<Subject %d> (%s)" % (char["reference_image"], char["name"])
    else:
        label = char["name"]
    if char.get("speaker_id"):
        label += " (%s)" % char["speaker_id"]
    parts = []
    if char.get("appearance"):
        parts.append(char["appearance"])
    if char.get("wardrobe"):
        parts.append("wearing " + char["wardrobe"])
    if char.get("voice") and char.get("speaker_id"):
        parts.append("speaking with " + char["voice"])
    if not parts:
        return label + "."
    if len(parts) == 1:
        description = parts[0]
    else:
        description = ", ".join(parts[:-1]) + ", and " + parts[-1]
    return "%s is %s." % (label, description)


def _dialogue(items, cast, globals_, overrides, default_language, where):
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("H3 batch: %s must be a list." % where)
    out = []
    for index, value in enumerate(items):
        line_where = "%s[%d]" % (where, index)
        line = _mapping(value, line_where)
        _unknown(line, DIALOGUE_FIELDS, line_where)
        speaker = _clean(line.get("speaker"))
        if speaker not in globals_["characters"]:
            raise ValueError("H3 batch: %s names unknown speaker %r."
                             % (line_where, speaker))
        if speaker not in cast:
            raise ValueError("H3 batch: %s speaker %r is not in this shot's "
                             "cast." % (line_where, speaker))
        char = _character(speaker, globals_, overrides)
        sid = char.get("speaker_id")
        if not sid:
            raise ValueError("H3 batch: speaking character %r needs a "
                             "speaker_id." % speaker)
        text = line.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("H3 batch: %s needs non-empty text." % line_where)
        language = _clean(line.get("language") or default_language)
        delivery = _clean(line.get("delivery"))
        voiceover = bool(line.get("voiceover", False))
        lead = "%s (%s) " % (char["name"], sid)
        if voiceover:
            lead += "says in an off-screen voiceover"
        else:
            lead += "says"
        if delivery:
            lead += " %s" % delivery
        rendered = "%s: <d>[%s] %s</d>" % (lead, language, text.strip())
        if voiceover:
            rendered += (" while the on-screen characters' lips remain "
                         "closed.")
        out.append(rendered)
    return out


def _music(value, audio):
    value = "default" if value is None else value
    if value is False or _clean(value).lower() in ("none", "n/a", "off"):
        return "N/A"
    text = _clean(value)
    if text == "default":
        return audio["default_music"] or "N/A"
    if text in audio["music"]:
        return audio["music"][text] or "N/A"
    return text or "N/A"


def compile_prompt(globals_, clip, defaults, context, duration, clip_id):
    """Compile one normalized v2 clip into the structured H3 prompt fields."""
    raw = clip.get("raw_prompt", clip.get("prompt"))
    if raw is not None:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("H3 batch: clip %r raw prompt is empty." % clip_id)
        return raw.strip()

    characters = globals_["characters"]
    default_cast = defaults.get("cast")
    cast = _cast(clip.get("cast", default_cast), characters,
                 "clip %r cast" % clip_id)
    overrides = _mapping(clip.get("character_overrides"),
                         "clip %r character_overrides" % clip_id)
    for char_id in overrides:
        if char_id not in characters:
            raise ValueError("H3 batch: clip %r overrides unknown character %r."
                             % (clip_id, char_id))
        if char_id not in cast:
            raise ValueError("H3 batch: clip %r overrides %r, which is not in "
                             "its cast." % (clip_id, char_id))

    loc_value = clip.get("location", defaults.get("location"))
    location = _location(loc_value, globals_["locations"],
                         "clip %r location" % clip_id)
    base_camera = _camera(defaults.get("camera"), where="defaults.camera")
    base_camera = _camera(clip.get("camera"), base_camera,
                          "clip %r camera" % clip_id)

    paragraphs = []
    summary_actions = []
    retention = []
    defined = set()
    if context != "none":
        retention.append(
            "Retain visual, motion, lighting, wardrobe, and audio "
            "continuity from the inherited clip context.")
    continuity = clip.get("continuity",
                          globals_["project"].get("continuity"))
    if isinstance(continuity, dict):
        allowed = {"inherit_motion", "inherit_action", "notes"}
        continuity = _mapping(continuity, "clip %r continuity" % clip_id)
        _unknown(continuity, allowed, "clip %r continuity" % clip_id)
        inherited = []
        if continuity.get("inherit_motion"):
            inherited.append("camera motion")
        if continuity.get("inherit_action"):
            inherited.append("subject action")
        if inherited and context != "none":
            retention.append("Preserve inherited %s without a reset."
                             % " and ".join(inherited))
        if _clean(continuity.get("notes")):
            retention.append(_clean(continuity["notes"]))
    elif _clean(continuity):
        retention.append(_clean(continuity))

    detailed = clip.get("detailed_description")
    if detailed is not None:
        legacy_fields = [key for key in ("shot", "shots", "camera", "dialogue")
                         if clip.get(key) is not None]
        if legacy_fields:
            raise ValueError("H3 batch: clip %r cannot combine "
                             "detailed_description with %s."
                             % (clip_id, " or ".join(legacy_fields)))
        if not isinstance(detailed, str) or not detailed.strip():
            raise ValueError("H3 batch: clip %r detailed_description is empty."
                             % clip_id)
        pieces = [globals_["project"].get("visual_style"),
                  location["description"]]
        for char_id in cast:
            character = _character(char_id, globals_, overrides)
            if not character.get("reference_image"):
                pieces.append(_character_definition(character))
        pieces.append(detailed.strip())
        paragraphs.append(" ".join(one for one in pieces if one))
        first_line = detailed.strip().splitlines()[0].strip()
        summary_actions.append(first_line)
        defined.update(cast)
    else:
        shots = clip.get("shots")
        if shots is not None and clip.get("shot") is not None:
            raise ValueError("H3 batch: clip %r cannot have both shot and shots."
                             % clip_id)
        if shots is None:
            shots = [clip.get("shot")]
        if not isinstance(shots, list) or not shots or shots[0] is None:
            raise ValueError(
                "H3 batch: structured clip %r needs detailed_description, "
                "shot, or shots." % clip_id)
        if len(shots) > 1 and clip.get("dialogue") is not None:
            raise ValueError("H3 batch: clip %r with multiple shots must put "
                             "dialogue inside each shot." % clip_id)

        previous_time = 0.0
        for index, value in enumerate(shots):
            where = "clip %r shots[%d]" % (clip_id, index)
            shot = _mapping(value, where)
            _unknown(shot, SHOT_FIELDS, where)
            if index == 0 and shot.get("at") is not None:
                raise ValueError("H3 batch: clip %r first shot must not have a "
                                 "timestamp." % clip_id)
            if index:
                if shot.get("at") is None:
                    raise ValueError("H3 batch: %s needs an at timestamp." % where)
                previous_time, stamp = _timestamp(
                    shot["at"], duration, previous_time, where)
                transition = _clean(
                    shot.get("transition") or "the camera cuts to")
                opening = "[Shot %d] At %s, %s" % (
                    index + 1, stamp, transition)
            else:
                opening = "[Shot 1]"

            shot_cast = _cast(
                shot.get("cast", cast), characters, where + ".cast")
            pieces = []
            if index == 0:
                style = globals_["project"].get("visual_style")
                if style:
                    pieces.append(style)
                if location["description"]:
                    pieces.append(location["description"])
            for char_id in shot_cast:
                if char_id not in defined:
                    character = _character(char_id, globals_, overrides)
                    if not character.get("reference_image"):
                        pieces.append(_character_definition(character))
                    defined.add(char_id)
            framing = _clean(shot.get("framing"))
            action = _clean(shot.get("action"))
            if not action:
                raise ValueError("H3 batch: %s needs an action." % where)
            summary_actions.append(action)
            if framing:
                pieces.append("A %s frames the action." % framing)
            pieces.append(action)
            pieces.append(_camera_sentence(
                _camera(shot.get("camera"), base_camera,
                        where + ".camera")))
            dialogue = shot.get("dialogue")
            if index == 0 and dialogue is None:
                dialogue = clip.get("dialogue")
            pieces.extend(_dialogue(
                dialogue, shot_cast, globals_, overrides,
                globals_["project"]["language"], where + ".dialogue"))
            paragraphs.append(opening + " " + " ".join(pieces))

    sound_parts = [globals_["audio"]["default_soundscape"],
                   location["soundscape"]]
    sound = clip.get("soundscape", defaults.get("soundscape"))
    explicit_silence = (sound is False
                        or _clean(sound).lower() in ("none", "n/a", "silent"))
    if explicit_silence:
        sound_parts = []
    elif _clean(sound):
        sound_parts.append(_clean(sound))
    soundscape = " ".join(part for part in sound_parts if part)
    if not soundscape:
        soundscape = ("N/A" if explicit_silence else
                      "Natural environmental ambience consistent with the "
                      "described scene.")
    music = _music(clip.get("music", defaults.get("music")), globals_["audio"])
    subjects = []
    reference_retention = []
    for char_id in sorted(
            defined,
            key=lambda one: (globals_["characters"][one].get(
                "reference_image") or 999, one)):
        char = _character(char_id, globals_, overrides)
        picture = char.get("reference_image")
        if picture:
            subjects.append("<Subject %d> is %s depicted in <Picture %d>."
                            % (picture, char["name"], picture))
            reference_retention.append(
                "Retain <Subject %d> identity and visual characteristics "
                "from <Picture %d>; do not replace them with a textual "
                "appearance." % (picture, picture))
    subject_text = "\n".join(subjects) if subjects else "N/A"
    summary = summary_actions[0] if summary_actions else "N/A"
    story = globals_["project"].get("story_context")
    if story:
        summary = "%s %s" % (story, summary)
    retention = reference_retention + retention
    retention_text = "\n".join(retention) if retention else "N/A"

    return ("subject_definitions:\n%s\n\n"
            "summary:\n%s\n\n"
            "retention_analysis:\n%s\n\n"
            "detailed_description:\n%s\n\n"
            "overall_soundscape:\n%s\n\n"
            "Non_diegetic_music:\n%s"
            % (subject_text, summary, retention_text,
               "\n\n".join(paragraphs), soundscape, music))
