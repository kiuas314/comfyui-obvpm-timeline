# Unattended H3 batches

`H3 Batch Plan` compiles a version 2 YAML screenplay into MiniMax H3's base
prompt format, then emits one clip at a time. `H3 Batch
Commit` checkpoints only after the MP4 and its `.mctx.safetensors` sidecar
exist. Version 1 manifests containing a raw `prompt` per clip remain valid.
The compiled layout follows MiniMax's
[official H3 base prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md).

The complete example is [`examples/h3_batch.yaml`](../examples/h3_batch.yaml).

Paste that complete YAML directly into H3 Batch Plan's multiline
`manifest_yaml` field. It is stored with the ComfyUI workflow, so no separate
manifest file is required.

The node is prefilled with a short castle smoke test. `castle_establishing`
uses `context: none`; `ballroom_dance` starts a second independent root; and
`dance_to_kiss` uses `context: previous` to inherit the dance before ending on
a kiss. This provides both a hard-cut and a continuation test without editing
the example first.

## Authoring model

The manifest separates durable production facts from events that happen in a
particular clip:

- `project` holds language, visual style, global story context, continuity and
  the negative prompt.
- `characters` is the character bible. A speaking character has one stable
  `speaker_id` (`S1`, `S2`, etc.) for the whole film. For Ref2V, assign
  `reference_image: 1` to the character shown in Picture 1,
  `reference_image: 2` for Picture 2, and so on.
- `locations` holds reusable visual and ambient-sound descriptions.
- `audio` holds default or named non-diegetic music descriptions.
- `defaults` holds generation/context settings and common cast, location,
  music and camera values.
- `clips` holds context routing plus shot-specific action, cast, dialogue and
  overrides.

Only characters named in a clip or shot's `cast` are written into that
prompt. Their appearance, wardrobe and voice are repeated because every clip
is a fresh text-conditioning run, even when its latent context continues a
previous take.

Reference-bound cast members also produce H3 subject definitions:

```yaml
characters:
  princess:
    name: Princess Elara
    reference_image: 1
    appearance: an elegant young woman with green eyes
  prince:
    name: Prince Adrian
    reference_image: 2
    appearance: a young man with warm brown eyes and dark hair
```

This compiles into:

```text
subject_definitions:
<Subject 1> is Princess Elara depicted in <Picture 1>.
<Subject 2> is Prince Adrian depicted in <Picture 2>.
```

Each picture number can belong to only one character. The workflow's first
reference-image input is Picture 1, the second is Picture 2, and so on.

Values resolve from broadest to narrowest:

```text
project/libraries -> defaults -> clip -> shot
```

A `character_overrides` entry changes appearance or wardrobe for one clip
(for example an age change or disguise) without mutating the character bible.
It cannot change `speaker_id`.

## Clips and context

The existing context forms are unchanged:

```yaml
context: none                    # new root; hard cut from its neighbours
context: previous                # extend the prior manifest clip
context: an_earlier_clip_id      # branch from an earlier completed take
context:
  from: previous
  window: 39
  mode: masked
  cut: 158                       # optional delivered-frame trim point
```

For a root, the compiled description says that a new scene opens. For a
continuation, it says that the shot continues from inherited visual and audio
context. Optional continuity controls make handoff intent explicit:

```yaml
continuity:
  inherit_motion: true
  inherit_action: true
  notes: Preserve the direction of the key light and falling rain.
```

## Shots, camera and dialogue

A normal one-shot clip uses `shot`; a clip with internal edits uses `shots`.
The first shot has no timestamp. Every later shot needs a strictly increasing
`at` time inside the clip duration:

```yaml
shots:
  - framing: medium-wide shot
    action: Mara approaches the telescope.
  - at: 3.5
    framing: close-up
    action: Her hand stops over the focusing wheel.
    dialogue:
      - speaker: mara
        language: English
        delivery: under her breath
        text: "Not again."
```

The compiler renders the second entry as `[Shot 2] At 00:03.500, the camera
cuts to...` and renders dialogue as `<d>[English] Not again.</d>`. A dialogue
speaker must exist, have a stable speaker ID, and be present in that shot's
cast.

Camera fields compile into natural H3 prose:

```yaml
camera:
  movement: push_in
  amplitude: small
  speed: slow
  target: the letter in her hands
```

Supported movements are `static`, `push_in`, `pull_out`, `zoom_in`,
`zoom_out`, `pan_left`, `pan_right`, `truck_left`, `truck_right`, `tilt_up`,
`tilt_down`, `pedestal_up`, `pedestal_down`, `arc`, `tracking`, `handheld`,
`shake_slightly`, `shake_strongly`, `pov`, `roll_clockwise`, and
`roll_counterclockwise`. Amplitude is `small`, `normal`, or `large`; speed is
`slow`, `normal`, or `fast`.

## Compiled output

Every structured clip contains the three core sections below. Clips with
reference-bound cast also begin with `subject_definitions`:

```text
subject_definitions:
<Subject 1> is a character depicted in <Picture 1>.

integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

The exact compiled prompt is emitted from `H3 Batch Plan` and saved in the
take's metadata. The YAML remains the editable source of truth. For a special
case that should bypass compilation entirely, use:

```yaml
- id: custom_clip
  context: none
  raw_prompt: >-
    An exact prompt to send to H3 without modification.
```

Manifest validation happens before sampling. Unknown characters or locations,
duplicate speaker IDs, invalid camera values, dialogue from characters outside
the cast, malformed shot times, and changes to a running manifest are refused
before they consume generation time.
