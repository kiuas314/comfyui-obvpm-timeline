# Unattended H3 batches

`H3 Batch Plan` compiles a version 2 YAML screenplay into MiniMax H3's base
prompt format, then emits one clip at a time. `H3 Batch
Commit` checkpoints only after the MP4 and its `.mctx.safetensors` sidecar
exist. Version 1 manifests containing a raw `prompt` per clip remain valid.
The compiled layout follows MiniMax's
[official H3 base prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md).

The complete example is [`examples/h3_batch.yaml`](../examples/h3_batch.yaml).

Import the complete YAML into **H3 Story + Clip Editor**, or paste it into the
Raw YAML tab. It is stored with the ComfyUI workflow, so no separate manifest
file is required. Export writes the current visual-editor document back to a
portable YAML file.

The clip list is divided into segments at every `context: none` root. Select a
clip to edit its blocks, add or remove optional overrides, and inspect the exact
compiled H3 prompt. Generation can queue only that clip, its complete root
segment, or every unfinished clip in the movie. Completed takes are added to
Timeline automatically for whole-story review and the later upscale pass.

To revise finished work without changing `batch_id`, enable **regenerate
existing takes** and then choose the clip, segment, or whole-movie generation
button. The selected completion records are reopened, so revised YAML is
accepted intentionally and new takes are queued. When each replacement
finishes, Timeline swaps it into every position occupied by the previous take
while preserving cuts and seam settings. Previous MP4 and sidecar files remain
on disk as recoverable takes; regeneration changes the active checkpoint and
Timeline cut rather than deleting media. Renaming a selected clip keeps the
same-position take as its replacement target. Moved clips have their checkpoint
positions reconciled, and removed clip IDs are retired from the checkpoint, so
a screenplay restructure cannot trap the batch behind stale state.

The node is prefilled with a short castle smoke test. `castle_establishing`
uses `context: none`; `ballroom_dance` starts a second independent root; and
`dance_to_kiss` uses `context: previous` to inherit the dance before ending on
a kiss. This provides both a hard-cut and a continuation test without editing
the example first.

Each successful H3 Batch Commit is automatically offered to the open Timeline
using the same lineage-aware placement as the Result Preview's **+ add to
timeline** button. Disable `add_to_timeline` on the commit node if you want to
keep completed takes off the Timeline. The ready-wired workflow keeps
generation and upscale previews separate. Once the chosen clips are in
Timeline, enable Timeline upscaling and use ComfyUI's normal Queue/Run action
for the upscale pass.

## Authoring model

The manifest separates durable production facts from events that happen in a
particular clip:

- `project` holds language, visual style, global story context, continuity and
  the negative prompt.
- `characters` is the character bible. A speaking character has one stable
  `speaker_id` (`S1`, `S2`, etc.) for the whole film. For Ref2V, assign
  `reference_image: 1` to the character shown in Picture 1,
  `reference_image: 2` for Picture 2, and so on.
- `locations` holds reusable visual and ambient-sound descriptions plus optional
  `reference_images` Picture slots. Those images are routed only when a clip
  selects that location.
- `audio` holds default or named non-diegetic music descriptions.
- `lora_library` gives installed content LoRAs short, reusable names.
- `defaults` holds generation/context settings and common cast, location,
  music and optional `content_loras` values.
- `clips` holds context routing, cast, a required `summary`, a complete
  `detailed_description`, and overrides including scene-specific content LoRAs.

The **Story globals** tab has a structured character library editor. Create a
stable character ID there, then edit its display name, Ref2V picture number,
speaker ID, appearance, wardrobe, and voice without writing JSON. In each clip,
enable **Cast** and use its dropdown to add characters from that library;
selected characters can be removed individually. A character cannot be deleted
from the library while story defaults or clips still reference it.

Locations have the same editor tab. Assign storyboard Picture numbers (for
example `reference_images: [3]`) to a location; the batch workflow routes those
images only for clips using that location.

Only characters named in a clip's `cast` are written into that prompt.
Reference-bound characters use their Picture as the identity source; characters
without a reference image retain their textual appearance definition.

## Scene content LoRAs

The workflow's existing **H3 Content LoRAs** Power Loader remains an additive
global stack. Scene LoRAs are applied after that stack and only on the clip
generation branch; the later whole-Timeline upscale does not wake the batch
planner or reapply the last scene's LoRA.

For fully manifest-controlled switching, leave the global Power Loader empty,
put common LoRAs in `defaults.content_loras`, and override them per clip. An
explicit empty list disables the defaults for that scene:

```yaml
lora_library:
  fantasy_light:
    name: h3/fantasy_light.safetensors
    strength: 0.7
  snow:
    name: h3/snow_weather.safetensors
    strength: 0.85

defaults:
  content_loras: [fantasy_light]

clips:
  - id: castle_exterior
    context: none
    content_loras:
      - preset: fantasy_light
        strength: 0.55
      - snow
    summary: Snow crosses the moonlit castle.
    detailed_description: Snow crosses the moonlit castle.

  - id: neutral_interior
    context: none
    content_loras: []  # no manifest-controlled content LoRAs
    summary: An undecorated room stands still.
    detailed_description: The undecorated room is still.
```

Each entry supports `name`, `preset`, `strength`, and `enabled`. Names are
resolved from ComfyUI's `models/loras` directory when that clip executes.

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
project/libraries -> defaults -> clip
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

For a continuation, `retention_analysis` records that visual and audio context
must carry forward. Optional continuity controls make handoff intent explicit:

```yaml
continuity:
  inherit_motion: true
  inherit_action: true
  notes: Preserve the direction of the key light and falling rain.
```

## Detailed description

Each clip always shows two required text fields: `summary` and
`detailed_description`. Summary is the concise clip overview placed in H3's
`summary` section. Detailed description contains framing, action, camera
movement, timing, and dialogue exactly as you want H3 to receive them:

```yaml
summary: Mara approaches the telescope and realizes something is wrong.
detailed_description: >-
  A medium-wide shot follows Mara toward the telescope. At 3.5 seconds, cut to
  a close-up as her hand stops over the focusing wheel. Under her breath, she
  says <d>[English] Not again.</d>
```

The compiler prepends the selected global visual style and location description,
then uses this text without decomposing it into framing/action/camera fields.
Locations are selected by ID from the **Story globals** location library. The
visual editor keeps Summary and Detailed description visible and non-removable
on every version 2 clip. The older `shot` and `shots` schema remains
import-compatible; opening a legacy clip in the visual editor derives its
summary and converts its action text to the simpler form. A manifest imported
without `summary` also receives a derived summary so older files keep working.

## Compiled output

Every structured clip contains these sections:

```text
subject_definitions:
<Subject 1> is a character depicted in <Picture 1>.

summary:
The concise action of this clip.

retention_analysis:
Retain <Subject 1> identity and visual characteristics from <Picture 1>.

detailed_description:
[Shot 1] ...

overall_soundscape:
...

Non_diegetic_music:
...
```

For a reference-bound character, `subject_definitions` and
`retention_analysis` establish the Picture as the identity source. The compiler
does not repeat that character's textual face/body description in
`detailed_description`, avoiding competition with Ref2V conditioning.

The exact compiled prompt is visible in the story editor, emitted from
`H3 Batch Plan`, and saved in the take's metadata. The YAML remains the
portable source of truth. For a special
case that should bypass compilation entirely, use:

```yaml
- id: custom_clip
  context: none
  raw_prompt: >-
    An exact prompt to send to H3 without modification.
```

Manifest validation happens before sampling. Unknown characters or locations,
duplicate speaker IDs, empty detailed descriptions, and changes to a running
manifest are refused before they consume generation time.
