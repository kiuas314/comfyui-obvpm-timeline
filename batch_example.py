"""Small structured screenplay prefilled in H3 Batch Plan."""

DEFAULT_BATCH_ID = "castle-dance-v1"
DEFAULT_BASE_FOLDER = "castle_dance_test"

DEFAULT_MANIFEST_YAML = """version: 2

project:
  title: The Moonlit Waltz
  prompt_format: h3_base
  language: English
  visual_style: >-
    Live-action romantic fantasy, lavish period costumes, cinematic
    anamorphic lenses, realistic faces and hands, graceful natural movement,
    warm candlelight, cool moonlight, and subtle film grain.
  story_context: >-
    At a royal winter ball, a young prince and princess meet beneath the
    chandeliers and discover that their formal dance has become sincere love.
  continuity: >-
    Keep both characters' faces, costumes, jewelry, height, and the ballroom
    lighting consistent throughout the dance.
  negative_prompt: >-
    subtitles, captions, watermark, modern objects, extra limbs, distorted
    hands, duplicate people, inconsistent costumes, cartoon, low quality

characters:
  prince:
    name: Prince Adrian
    appearance: >-
      a handsome 27-year-old man with warm brown eyes, wavy dark hair, a
      clean-shaven face, and an athletic build
    wardrobe: >-
      a fitted midnight-blue velvet military jacket with fine gold embroidery,
      a white high-collared shirt, dark formal trousers, and polished boots

  princess:
    name: Princess Elara
    appearance: >-
      an elegant 25-year-old woman with expressive green eyes, softly curled
      chestnut hair, and a delicate oval face
    wardrobe: >-
      an ivory silk ball gown embroidered with tiny silver stars, long white
      gloves, a small diamond tiara, and a moonstone necklace

locations:
  castle_exterior:
    description: >-
      A vast fairy-tale castle rises above snowy mountains at blue hour. Warm
      light glows from hundreds of windows beneath a bright full moon.
    soundscape: >-
      A gentle winter wind crosses the mountains while distant bells carry
      from the castle.

  grand_ballroom:
    description: >-
      A magnificent marble ballroom with gilded columns, tall arched windows,
      crystal chandeliers, hundreds of candles, and a polished floor reflecting
      moonlight. Formally dressed guests watch from the edge of the room.
    soundscape: >-
      Silk and footsteps move softly across polished marble beneath the quiet
      ambience of an attentive royal gathering.

audio:
  default_music: >-
    A romantic orchestral waltz led by warm strings and delicate harp, elegant
    and restrained, gradually resolving into a tender final phrase.

defaults:
  duration_seconds: 6
  music: default
  camera:
    movement: static
    amplitude: normal
    speed: normal

clips:
  # This establishing shot is an independent root with no inherited context.
  - id: castle_establishing
    context: none
    location: castle_exterior
    cast: []
    shot:
      framing: extreme wide establishing shot
      action: >-
        Snow drifts through the moonlight as the camera approaches the glowing
        castle, revealing tiny carriages arriving at its grand entrance.
      camera:
        movement: push_in
        amplitude: small
        speed: slow

  # This begins a new root after the exterior, creating a deliberate hard cut.
  - id: ballroom_dance
    context: none
    location: grand_ballroom
    cast: [prince, princess]
    duration_seconds: 8
    shot:
      framing: full-body medium-wide two-shot
      action: >-
        Prince Adrian offers his hand to Princess Elara. She accepts with a
        shy smile, and they begin a graceful waltz through the open center of
        the ballroom. Their eyes remain fixed on one another as her ivory skirt
        turns naturally around them.
      camera:
        movement: arc
        amplitude: normal
        speed: slow

  # This clip inherits the dance's final frames and carries the motion forward.
  - id: dance_to_kiss
    context: previous
    location: grand_ballroom
    cast: [prince, princess]
    duration_seconds: 8
    continuity:
      inherit_motion: true
      inherit_action: true
      notes: >-
        Continue their exact dance position and turning direction from the
        inherited frames. Preserve faces, costumes, and chandelier lighting.
    shots:
      - framing: medium two-shot
        action: >-
          Their waltz continues seamlessly, then slows beneath the central
          chandelier. Adrian gently draws Elara closer as the surrounding
          guests become still and the music softens.
        camera:
          movement: tracking
          amplitude: small
          speed: slow
      - at: 5.5
        framing: intimate close-up two-shot
        action: >-
          Elara rests one gloved hand against Adrian's cheek. They share a
          tender, unhurried kiss as candlelight shimmers behind them. The final
          image holds on their peaceful expressions while the waltz resolves.
        camera:
          movement: push_in
          amplitude: small
          speed: slow
"""
