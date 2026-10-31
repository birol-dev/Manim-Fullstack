"""Guidance for AI clients: how to choose, write, style and export a Studio video.

No Manim import. Everything that can be read from the live catalog (template ids,
``when_to_use``/``not_for``, field limits, presets, themes, aspects, formats, qualities,
tracks) is generated from it, so it cannot drift from what is installed. Only the
tactics below are hand-written.

``register_guidance(server, service)`` adds one tool (``guide``), the MCP prompts and
the MCP resources to a server built by ``studio.mcp_server.create_server``.
"""

from __future__ import annotations

from .sound import EFFECTS, TRACKS

TOPICS = ("start", "templates", "writing", "platforms", "look", "sound", "export", "many", "troubleshooting")

SUMMARIES = {
    "start": "The workflow, from the goal to the download link.",
    "templates": "What each template is for (and not for), with its presets.",
    "writing": "Tactics for on-screen text, and every field's character limit.",
    "platforms": "Aspect, length and safe zone for each destination.",
    "look": "Themes, backgrounds, energy, ending and brand colours.",
    "sound": "Effects, bundled music, uploads, volume and fading.",
    "export": "Formats, qualities, transparency, render times, retries.",
    "many": "One video per row of a list: make_many, columns and skipped rows.",
    "troubleshooting": "What to do when a tool returns an error.",
}


# -- reading the live catalog ---------------------------------------------------------

def _definitions(schema: dict) -> dict:
    return (schema or {}).get("$defs") or {}


def _resolve(schema: dict, value):
    for _ in range(6):
        if not isinstance(value, dict) or "$ref" not in value:
            break
        value = _definitions(schema).get(str(value["$ref"]).rsplit("/", 1)[-1], {})
    return value if isinstance(value, dict) else {}


def _walk_strings(schema: dict) -> list:
    """(path, property) for every string in a params schema, including list items."""
    found = []

    def walk(properties, prefix):
        for name, raw in (properties or {}).items():
            prop = dict(raw or {})
            variants = prop.get("anyOf") or prop.get("oneOf") or []
            string_variant = next((v for v in variants if isinstance(v, dict) and v.get("type") == "string"), None)
            if string_variant:
                prop = {**{k: v for k, v in prop.items() if k not in ("anyOf", "oneOf")}, **string_variant}
            prop = _resolve(schema, prop)
            if prop.get("type") == "string":
                found.append((prefix + name, prop))
            elif prop.get("type") == "array":
                items = _resolve(schema, prop.get("items") or {})
                walk(items.get("properties"), f"{prefix}{name}[].")

    walk((schema or {}).get("properties"), "")
    return found


def _limits_line(template: dict) -> str:
    parts = [f"{path} ≤ {prop['maxLength']}" for path, prop in _walk_strings(template.get("schema") or {})
             if isinstance(prop.get("maxLength"), int)]
    return " · ".join(parts) or "no free text fields"


def _emphasis_paths(template: dict) -> list:
    return [path for path, prop in _walk_strings(template.get("schema") or {})
            if "asterisk" in str(prop.get("description") or "").casefold()]


def _seconds(value) -> str:
    value = float(value)
    return f"{value:g} s"


def _length(template: dict) -> str:
    if template.get("length_from_params"):
        return "length set by the content"
    return (f"{_seconds(template.get('min_length', 0))}-{_seconds(template.get('max_length', 0))} "
            f"(default {_seconds(template.get('default_length', 0))})")


def _aspects(template: dict) -> str:
    aspects = list(template.get("aspects") or [])
    default = template.get("default_aspect")
    if default in aspects:
        aspects.remove(default)
        return ", ".join([f"{default} by default"] + aspects) if aspects else f"{default} only"
    return ", ".join(aspects) or "16:9"


def _preset_list(template: dict, with_summary: bool = True) -> str:
    rows = []
    for preset in template.get("presets") or []:
        if with_summary and preset.get("summary"):
            rows.append(f"`{preset['id']}` — {str(preset['summary']).rstrip('.')}")
        else:
            rows.append(f"`{preset['id']}` ({preset.get('title') or preset['id']})")
    return "; ".join(rows) or "none"


def _template_line(template: dict) -> str:
    return (f"- **{template['id']}** — {template['title']} · {_aspects(template)} · {_length(template)}. "
            f"**For:** {template['when_to_use']} "
            f"**Not for:** {template.get('not_for') or 'nothing in particular.'} "
            f"**Presets:** {_preset_list(template)}")


def _defs_enum(schema: dict, definition: str, name: str) -> list:
    prop = ((_definitions(schema).get(definition) or {}).get("properties") or {}).get(name) or {}
    return list(prop.get("enum") or [])


def _settings_enum(schema: dict, name: str) -> list:
    prop = (schema.get("properties") or {}).get(name) or {}
    return list(prop.get("enum") or [])


def _footer(catalog: dict) -> str:
    ids = ", ".join(f"`{t['id']}`" for t in catalog.get("templates", []))
    themes = ", ".join(f"`{t['id']}`" for t in catalog.get("themes", []))
    aspects = ", ".join(f"`{a['id']}`" for a in catalog.get("aspects", []))
    return ("---\n"
            f"Installed templates: {ids}. Themes: {themes}. Aspects: {aspects}. "
            "`guide(\"templates\")` explains each template; `guide(\"writing\")` lists every text limit; "
            "`get_template(id)` returns the live params schema and presets.")


def _unknown(topic: str) -> str:
    lines = [f"Unknown guide topic **{topic or '(empty)'}**. Available topics:", ""]
    lines += [f"- **{key}** — {SUMMARIES[key]}" for key in TOPICS]
    return "\n".join(lines)


# -- hand-written tactics ---------------------------------------------------------------

def _render_start(catalog: dict) -> str:
    templates = "\n".join(f"- **{t['id']}** — {t['summary']}" for t in catalog.get("templates", []))
    return f"""# Start here: make a short video in ten steps

You are making a short animated clip from the templates installed in this Studio. The
person watches the project in the app and downloads the exported file at the end.

1. **Understand the goal first.** Who watches it (students, customers, a friend, a
   team), where it will be shown (a phone story, YouTube, a classroom projector, a shop
   screen) and roughly how long it should run. If any of that is missing, choose a
   sensible default, say what you assumed, and keep it short.
2. **Pick the template by the job.** `search_templates(query="...")` matches everyday
   words (sale, birthday, timer, quiz, quote, year review). Then `get_template(template)`
   for the exact params schema, settings schema, defaults, presets and limits. Never
   invent a field name: unknown fields are refused.
3. **Start from a preset.** A preset is a finished card (realistic content + look). Copy
   its `params`/`settings` and change only what the person asked for. `quick_video(
   template, preset, params, settings)` does preset → project → storyboard in one call.
4. **Keep the words short.** Respect every `maxLength`; the layouts are tested against
   those limits, not against longer text. One idea per card, 5-7 words per line.
5. **Choose the aspect for the destination.** `settings.aspect`: 16:9 for YouTube and
   slides, 9:16 with `safe_zone=true` for Shorts/Reels/TikTok/Stories, 4:5 or 1:1 for
   the Instagram feed. See `guide("platforms")`.
6. **Create (or update) the project.** `create_project(template, params, settings, title)`
   saves it and returns its id; use a title the person will recognize.
7. **Look at it.** `preview(project_id, mode="storyboard")` returns a storyboard image and
   frame times. Actually inspect the image: clipped text, empty space, the wrong word
   emphasized, text under a platform button.
8. **Revise with `update_project`.** Call `get_project` first: a supplied `params` or
   `settings` replaces the whole object, so send the complete object and the `revision` you
   read as `base_revision`. If it answers 409, someone else saved meanwhile: nothing changed,
   so read the project again and decide what to keep. Preview again.
9. **Motion is optional.** `preview(project_id, mode="motion")` queues a 720p preview with
   sound for the first 20 seconds; poll `get_motion`. It costs time, so use it only when
   timing or animation matters.
10. **Export and deliver.** `export_project(project_id, format="mp4", quality="1080p")`
    queues a job; poll `get_export(export_id)` until `status` is `done`, then give the
    person `download_url`, the `project_id` and the `app_url` from `create_project`.
    If it failed, read `error`, fix the input, export again (or `retry_export`).

Many videos at once (a class list, a product list) use `make_many`; read
`guide("many")` for the column mapping and the row limits.

Good work needs no extra flourishes: one clear message, legible text, one look, sound
that suits the room, and the right shape for where it plays.

## Templates in this installation

{templates}

Full instructions per topic: `guide("start")` (this page), `guide("templates")`,
`guide("writing")`, `guide("platforms")`, `guide("look")`, `guide("sound")`,
`guide("export")`, `guide("troubleshooting")`."""


def _render_templates(catalog: dict) -> str:
    lines = [
        "# Templates and their presets",
        "",
        "Pick the template whose job matches, then start from one of its presets and change",
        "only what is needed. `get_template(id)` returns the live params schema and defaults.",
        "",
    ]
    lines += [_template_line(t) for t in catalog.get("templates", [])]
    lines += [
        "",
        "A preset's `settings` (theme, energy, aspect) are part of the look: keep them unless",
        "the person asks for something else. If two templates seem to fit, prefer the one whose",
        "`when_to_use` names the job; use the catalogue's `not_for` line to rule the other out.",
    ]
    return "\n".join(lines)


def _render_writing(catalog: dict) -> str:
    limits = "\n".join(f"- **{t['id']}**: {_limits_line(t)}" for t in catalog.get("templates", []))
    emphasis = []
    for template in catalog.get("templates", []):
        paths = _emphasis_paths(template)
        if paths:
            emphasis.append(f"**{template['id']}** "
                            + ", ".join(f"`{path}`" for path in paths))
    emphasis_block = ("Fields that colour emphasized words: " + "; ".join(emphasis) + "."
                      if emphasis else "No field in this installation supports *emphasis*.")
    return f"""# Writing for the screen

People read a short video in glances, so write for glances, not paragraphs.

- **5-7 words per line, one idea per card.** If a sentence needs "and", it may need two
  cards or two videos.
- **Lead with the point.** The headline carries the message; the kicker sets context; the
  details answer when, where and how much. Do not repeat the kicker in the headline.
- **Use `*asterisks*` for one or two key words only.** {emphasis_block}
  Never wrap a whole sentence; emphasis loses meaning when everything is emphasized.
- **Put numbers in number fields, not in text.** `countdown.seconds`, `quiz.correct` and
  `quiz.think_seconds`, `celebration.number`, `year_in_review` stat `value`, `steps`
  highlight. Number formatting (thousands separators, decimals) follows `settings.locale`
  (`en`, `tr`, `de`, ...).
- **No emoji.** No field accepts them. Use a bundled icon instead: call `list_icons()` and
  put the name in an icon field (calendar, clock, map-pin, gift, star, cake...).
- **Plain language.** Write dates and times the way people say them ("Sat 14 June, 7 pm",
  "Doors 18:30"), not as ISO strings.
- **Leave optional fields empty** (`""` for text, `null` for images/colors) when they add
  nothing; empty fields stay hidden. Never write "N/A", "none" or a label like "Date:".
- **Reading time.** People read about three words a second. `quote` paces its own reveal
  and never runs shorter than `settings.length`; give a quiz 6-10 `think_seconds`; a timer
  runs in real seconds, so 300 means five minutes on the clock.
- **Check the storyboard.** If a line wraps to four or more lines, or a card looks empty,
  shorten the text or drop a field rather than shrinking the layout.

## Text limits (the layout is tested against these)

{limits}"""


def _render_platforms(catalog: dict) -> str:
    aspects = ", ".join(f"`{a['id']}` {a['label'].lower()}" for a in catalog.get("aspects", []))
    return f"""# Where it will be shown

The destination decides the shape, the length and how much margin the text needs.

| Destination | `settings.aspect` | Also set | Notes |
|---|---|---|---|
| YouTube, Vimeo, a website, slide decks | `16:9` | — | The default. Slides want large text and few words; a 10-30 s clip works well. |
| YouTube Shorts, Reels, TikTok, Stories, WhatsApp status | `9:16` | `safe_zone=true` | Keep the message in the middle: buttons and captions cover the bottom and right. |
| Instagram feed | `4:5` (or `1:1`) | — | `4:5` fills more of a phone screen than `1:1`; both work in the feed. |
| Classroom projector | `16:9` | large text, `energy="calm"` | People read from the back of a room; avoid fine detail and fast motion. |
| Email, chat, docs | GIF (silent, loops) or MP4 | short, 5-10 s | A GIF has no sound; put the message on screen. MP4 for WhatsApp/Teams. |
| Shop screen, lobby, signage | `16:9` | `loopable` templates | A calm loop with a long hold reads better than a busy one. |

- **Aspect changes the layout.** The same params are re-laid-out for each ratio, so
  preview again after changing `aspect`. Templates accept only their own list
  (`get_template(...).aspects`); this installation offers {aspects}.
- **Length is advisory.** Platform limits change, so check the platform's current limit
  before promising a duration. Each template also has its own range; `get_template` shows
  `min_length`/`max_length`, and timers set their own length from the content.
- **Safe zone.** `safe_zone=true` keeps text clear of the buttons and captions at the
  bottom and right of vertical video. Turn it on for every 9:16 post; it is unnecessary
  for 16:9.
- **Sound is optional for the viewer.** Most feeds autoplay muted: the message must work
  with the sound off, and music is a bonus. See `guide("sound")`.
- **GIF or PNG are silent** — a GIF loops without audio, a PNG is one still poster frame."""


def _render_look(catalog: dict) -> str:
    themes = "\n".join(
        f"- **{t['id']}** — {t['name']} ({'dark' if t.get('dark') else 'light'}); accents "
        + ", ".join(t.get("accent") or []) for t in catalog.get("themes", []))
    settings = catalog.get("settings_schema") or {}
    background = _defs_enum(settings, "Background", "kind") or ["theme", "solid", "gradient", "transparent"]
    energy = _settings_enum(settings, "energy") or ["calm", "normal", "punchy"]
    ending = _settings_enum(settings, "ending") or ["hold", "fade", "cut"]
    return f"""# How it looks

## Themes (live from the catalog)

{themes}

Pick one theme per video and keep it. Rough fit: `clean` for business, classes and
everyday notices; `midnight` for tech, evening events and quotes; `pop` for promotions
and celebrations; `newsroom` for editorial and product news; `pastel` for warm,
community and kids content; `chalk` for teaching.

## Background

`settings.background.kind` is one of {", ".join(f"`{kind}`" for kind in background)}:

- `theme` (default) uses the theme's own background — the safest choice.
- `solid` fills with `background.color` (`#RRGGBB`).
- `gradient` blends `background.color` into `background.color2` (both `#RRGGBB`).
- `transparent` has no background at all: export `mov` or `webm` to keep the alpha
  channel. Asking for MP4 with a transparent background returns MOV (MP4 cannot hold it).

## Energy and ending

- `settings.energy`: {", ".join(f"`{e}`" for e in energy)}. It changes how fast elements
  move in and out, not how long text stays readable. `calm` for quotes, classroom and
  formal notices; `punchy` for sales, celebrations and social.
- `settings.ending`: {", ".join(f"`{e}`" for e in ending)}. `hold` keeps the last frame
  (best when the video is paused or embedded), `fade` ends softly (social), `cut` stops
  cleanly (loops, signage).

## Brand and accents

`settings.brand` carries the brand kit for one video. Every field is optional; send
`null` (or leave it out) to stop using it:

```json
{{
  "settings": {{
    "aspect": "9:16",
    "brand": {{
      "accent": "#2563EB",
      "accent2": "#F97316",
      "font": "Inter",
      "logo": "agent-1a2b3c4d5e6f7890.png"
    }}
  }}
}}
```

- `brand.accent` and `brand.accent2` replace the theme's first two accent colours.
- `brand.font` is a font the app bundles: `Inter` or `JetBrains Mono` (aliases such as
  `Inter Studio` work). Any other name silently keeps the theme's own font, so never
  rely on a font being installed on the render machine.
- `brand.logo` is an uploaded image name: call `add_image` first, then pass the returned
  `name`. Templates draw it small (about 7% of the short side) in a corner that suits
  their layout and fade it in with the first content. A missing or unreadable file is
  skipped with a warning instead of failing the render, so preview before exporting.
- A template `accent` param (timer ring, quote highlights) colours that one element — do
  not set it to a different colour than the brand accent.
- Keep contrast: dark text on light themes, light text on dark themes. The theme already
  pairs `text` with `bg` and `on_accent` with `accent`; avoid two saturated colours next
  to each other, and avoid placing a brand accent on a background of the same hue.
- `settings.locale` (`en`, `tr`, `de`, ...) formats numbers and dates; it does not
  translate your text.

Preview after any look change and check the storyboard: legibility on a phone matters
more than decoration."""


def _render_sound(catalog: dict) -> str:
    tracks = "\n".join(f"  - `{t['id']}` — {t['title']}: {t['description']}"
                       for t in (catalog.get("music_tracks") or TRACKS))
    return f"""# Sound

Sound sits in `settings.sound` and never changes the scene's timing.

- **Effects are on by default** (`sound.effects: true`, `sound.effects_volume: 0.75`).
  Templates cue them where they help: a tick in a countdown's last seconds, a chime when
  a timer finishes, a correct-answer chime in a quiz, a sparkle on a celebration, a soft
  whoosh on an announcement, a tick after each number in a year recap. Turn them off for
  quiet rooms with `"sound": {{"effects": false}}`.
- **Bundled music** (original, no licensing worries) — pick one id for
  `settings.sound.music.track` and leave `music.asset` empty. `list_music_tracks()`
  returns them with audition URLs:
{tracks}
- **Your own music**: `upload_audio(data_base64, filename)` (MP3, M4A/AAC, WAV or OGG,
  at most 50 MB and 10 minutes) returns a name for `settings.sound.music.asset`. Use the
  track **or** the asset, never both — that is a validation error.
- **Volume, fade and loop**: `music.volume` is 0-1 (1 = the mastered level, about -16 LUFS;
  50% is about -10 dB, 25% about -22.5 dB). `music.fade_out` fades over the last 1.5 s and
  `music.loop` repeats a short source. Effects and music are 48 kHz stereo.
- **Silent outputs**: GIF and PNG never carry audio, and posters/storyboards are silent.
  MP4, WebM and MOV carry the mix.
- The available effect names are {", ".join(f"`{name}`" for name in EFFECTS)}; templates
  choose them, so you normally do not need to name one.
- A motion preview (`preview(mode="motion")`) plays the mix, but only the first 20 seconds;
  a long timer's finish chime is outside it. Export to hear the ending."""


def _format_rows(catalog: dict) -> str:
    rows = []
    for fmt in catalog.get("formats", []):
        notes = []
        if fmt.get("kind") == "image":
            notes.append("one still frame")
        if fmt.get("transparent"):
            notes.append("can keep transparency")
        rows.append(f"- `{fmt['id']}` — {fmt['label']}" + (f" ({', '.join(notes)})" if notes else ""))
    return "\n".join(rows)


def _quality_rows(catalog: dict) -> str:
    rows = []
    for quality in catalog.get("qualities", []):
        detail = f"{quality['short']} px on the short side"
        if f"{quality['fps']} fps" not in quality["label"]:
            detail += f", {quality['fps']} fps"
        rows.append(f"- `{quality['id']}` — {quality['label']}, {detail}")
    return "\n".join(rows)


def _render_export(catalog: dict) -> str:
    formats = _format_rows(catalog)
    qualities = _quality_rows(catalog)
    fps_templates = [t for t in catalog.get("templates", []) if t.get("export_fps")]
    fps_line = ("; ".join(f"`{t['id']}` renders at {t['export_fps']} fps" for t in fps_templates)
                or "no template overrides the frame rate")
    return f"""# Export

An export is a background job: `export_project` returns immediately with a job id, and
you poll `get_export(export_id)` until `status` is `done` (or `failed`/`cancelled`).
Finished records carry `download_url` (absolute) and `filename`.

## Formats

{formats}

- `mp4` is the universal choice (H.264 video, AAC audio). Send it unless the person asked
  for something else.
- `gif` loops and is silent; keep it short (a few seconds) because the file grows fast.
- `png` is one still (the poster frame), useful as a thumbnail.
- `webm` and `mov` can keep an alpha channel; use them for overlays in an editor. A
  transparent background asked for as MP4 becomes MOV automatically.

## Qualities

{qualities}

`draft` is for checking quickly, `720p` for chat and classroom screens, `1080p` for
publishing, `1080p60` for fast motion, `4k` for large screens. Bigger costs more time.

## Frame rate and timing

{fps_line}. A timer's content is mostly still, so the renderer uses its suggested rate
whatever the quality says. Templates whose length comes from the content (timers, quiz,
quote pacing) ignore `settings.length`.

## How long a render takes

As a rule of thumb a 1080p export takes about the clip's own length plus a few seconds of
start-up; draft is several times faster and 4K several times slower. A long timer is
cheap per second but the file is long. Do not guess: poll `get_export` for `progress`
and wait for `done`.

## Cancelling, retrying, removing

- `cancel_export(export_id)` stops a queued or running job.
- `retry_export(export_id)` starts a **new** job from the request stored on a finished
  record (new id); use it after a failure without rebuilding the project.
- `remove_export(export_id)` forgets a finished record and deletes its file unless
  `delete_file=false`. Cancel a running export before removing it.
- `list_exports()` lists the history newest first, like the app's Exports page.

## Where the files go

Finished files live in the app's `workspace/media/studio/exports/` folder and are served at
`/media/studio/exports/...`; `download_url` is the absolute address for the person. The
project itself is saved separately, so exporting twice does not change it."""


def _render_many(catalog: dict) -> str:
    templates = "\n".join(f"- **{t['id']}** — {t['summary']}" for t in catalog.get("templates", []))
    return f"""# One video per row of a list

When the person has a spreadsheet (30 names, 20 products), do not call `create_project` and
`export_project` in a loop. `make_many` reads the rows, fills the template's fields from the
columns, and queues one export per usable row.

## Step by step

1. **Choose the template and a starting look.** `get_template(template)` returns its schema,
   presets and defaults. Start from a preset (`make_many(..., preset="...")`) so the words
   around the mapped fields already read well, or send `params` and `settings` yourself.
2. **Find the fillable fields.** Only the template's simple top-level `text`, `number` and
   `color` fields can be filled from a list. Lists (`details`, `options`, table rows),
   pictures, icons, toggles and fixed choices keep the design's own values. The `fields`
   array from the Studio's Make many page lists them for a person; for an agent,
   `get_template(...)["schema"]["properties"]` and its `x-widget` values show the same.
3. **Map a column to a field by index.** `mapping` is `{{"headline": 0, "big_text": 1}}`:
   the field name points at a column index in every row. `rows` are cell lists without the
   header row:

   ```json
   {{
     "template": "announcement",
     "preset": "event-invite",
     "rows": [["Summer fair", "14.06", "Come along"], ["Bake sale", "21.06", "Open to all"]],
     "mapping": {{"headline": 0, "big_text": 1, "call_to_action": 2}},
     "title_column": 0,
     "format": "mp4",
     "quality": "1080p"
   }}
   ```

   An empty cell keeps the design's own value; it never blanks a field. A title column names
   each video and its file. Without one, videos are named after the design and their row.
4. **Respect the limits.** At most 200 rows and 40 columns. Keep every cell plain text; the
   template's normal validation still applies. Dates should be written the way a person says
   them ("14 June 2026"), not as spreadsheet serial numbers.
5. **Read the result.** `make_many` answers `{{batch_id, export_ids, row_errors, batch}}`.
   Rows that fail validation are skipped and named in `row_errors` with their row number,
   field and a plain message; the other rows are already queued. Show the person which rows
   were skipped and why, rather than silently dropping them.
6. **Wait and deliver.** Poll `get_export(export_id)` for each id until it is `done`, or call
   `list_exports()` and use the records carrying that `batch_id`. Finished files sit in one
   subfolder named after the batch. Give the person each `download_url`, or the app's
   Exports page at `app_url`.

Mistakes wait for a fix, not for a loop: correct the mapped values or the row text and call
`make_many` again with just the bad rows. `retry_export` repeats one failed job from its
stored request. A batch's own cancel and retry actions are in the app.

## Templates that work well for lists

{templates}"""


def _render_troubleshooting(_catalog: dict) -> str:
    return """# Troubleshooting

Tool errors come back as `ToolError` with JSON like
`{"detail": "Invalid input for announcement.", "errors": [{"field": "params.headline",
"message": "..."}]}`. Read the `field` path and fix exactly that value.

- **`params.<name>` / `settings.<name>`** — the field path uses dots; list items are
  0-based (`params.details.2.text`). `get_template(template)` shows the accepted fields,
  types, enums, `maxLength`, minimum/maximum and item counts.
- **"Unknown field"** — you invented a field. Call `get_template` and use only the names
  in `schema.properties`. Do not send `id`, `version` or gallery-only keys.
- **"Unknown template"** — `search_templates(query=...)` and use an id from `guide(
  "templates")`.
- **Text too long** — shorten the text. Do not split one field across two fields or set a
  negative index; the layout is tested against the declared limits, not longer text.
- **Number out of range** — respect `minimum`/`maximum`. In a quiz, `correct` is 1-based:
  1 is the first answer, so it can never exceed `len(options)`. In steps, `highlight` is
  0 (off) to the number of steps.
- **A missing image** — an image field takes an uploaded asset name. Send the picture with
  `add_image(data_base64)` (PNG, JPEG, GIF, WebP or SVG, at most 8 MB) and use the returned
  `name`. Names are content-addressed, so sending the same picture twice is safe.
- **A missing icon** — `list_icons()` returns the bundled names; a template's default icon
  is used when the field is empty.
- **Music refused** — `settings.sound.music.track` and `music.asset` are mutually
  exclusive. Pick one; an uploaded asset must be a name returned by `upload_audio`.
- **The project saved but the preview failed** — that is expected: projects may hold
  incomplete input while someone types, but previews and exports validate. The error names
  the field.
- **An export failed** — `get_export` shows `error` and the job's `message`. Read it; fix
  the project with `update_project` (call `get_project` first) and export again, or
  `retry_export` to repeat the stored request. A renderer error that names no field is
  usually a template limit (text too long, an image that cannot be read).
- **A preview looks stale** — previews are cached by their exact content. Change a field
  (even back and forth) or use `preview` again; identical content intentionally reuses
  the image.
- **"Could not reach / start Manim Studio"** — with the desktop setup (`--desktop-data`)
  the server starts Studio in the background by itself; the first call after a quiet spell
  can take up to half a minute, so try once more. With `--url`, the app must be open.
  HTTP clients should check the `/mcp/` address and credential from Connect to AI.
- **A job never finishes** — cancel it (`cancel_export` / `cancel_motion`) and start again;
  a stuck render is better replaced than waited on."""


_RENDERERS = {
    "start": _render_start,
    "templates": _render_templates,
    "writing": _render_writing,
    "platforms": _render_platforms,
    "look": _render_look,
    "sound": _render_sound,
    "export": _render_export,
    "many": _render_many,
    "troubleshooting": _render_troubleshooting,
}


async def topic_markdown(service, topic: str = "start") -> str:
    """The guide for *topic* as markdown; an unknown topic lists the topics."""
    catalog = await service.catalog()
    key = (topic or "start").strip().casefold()
    renderer = _RENDERERS.get(key)
    body = renderer(catalog) if renderer else _unknown(key)
    return body.rstrip() + "\n\n" + _footer(catalog) + "\n"


# -- resources -------------------------------------------------------------------------

def compact_catalog(catalog: dict) -> dict:
    """Templates, presets and themes without the bulky schemas."""
    return {
        "templates": [
            {
                "id": t["id"], "title": t["title"], "summary": t["summary"], "category": t["category"],
                "when_to_use": t["when_to_use"], "not_for": t.get("not_for", ""),
                "aspects": t["aspects"], "default_aspect": t["default_aspect"],
                "min_length": t["min_length"], "max_length": t["max_length"],
                "default_length": t["default_length"],
                "length_from_params": bool(t.get("length_from_params")),
                "presets": [
                    {"id": p["id"], "title": p["title"], "summary": p["summary"],
                     "settings": p.get("settings") or {}}
                    for p in t.get("presets") or []
                ],
            }
            for t in catalog.get("templates", [])
        ],
        "themes": catalog.get("themes", []),
        "aspects": catalog.get("aspects", []),
        "formats": catalog.get("formats", []),
        "qualities": catalog.get("qualities", []),
        "music_tracks": catalog.get("music_tracks", []),
    }


def template_resource(info: dict) -> dict:
    """One template's params schema, presets and the tactics that apply to it."""
    limits = _limits_line(info)
    emphasis = _emphasis_paths(info)
    tips = [
        f"Start from a preset: {_preset_list(info, with_summary=False)}. Copy its params and settings, "
        "then change only what the person asked for.",
        f"Field limits: {limits}.",
    ]
    if emphasis:
        tips.append("Wrap one or two key words in *asterisks* to colour them in "
                    + ", ".join(f"`{path}`" for path in emphasis) + ".")
    tips += [
        f"Default aspect {info['default_aspect']}; accepted: {', '.join(info['aspects'])}. "
        "Preview again after changing it.",
        "Create with `quick_video` for a project plus storyboard in one call, then look at the "
        "storyboard before exporting.",
    ]
    return {
        "id": info["id"], "title": info["title"], "summary": info["summary"],
        "category": info["category"], "when_to_use": info["when_to_use"], "not_for": info.get("not_for", ""),
        "aspects": info["aspects"], "default_aspect": info["default_aspect"],
        "min_length": info["min_length"], "max_length": info["max_length"],
        "default_length": info["default_length"],
        "length_from_params": bool(info.get("length_from_params")),
        "schema": info["schema"], "defaults": info["defaults"],
        "presets": [
            {"id": p["id"], "title": p["title"], "summary": p["summary"], "category": p["category"],
             "params": p["params"], "settings": p["settings"], "tags": p.get("tags", [])}
            for p in info.get("presets") or []
        ],
        "tips": tips,
    }


# -- prompts ---------------------------------------------------------------------------

def _template_menu(catalog: dict, ids=None) -> str:
    rows = []
    for template in catalog.get("templates", []):
        if ids is not None and template["id"] not in ids:
            continue
        rows.append(f"- `{template['id']}` ({template['title']}) — "
                    f"{str(template['summary']).rstrip('.')}")
    return "\n".join(rows)


def _presets_of(catalog: dict, template_id: str) -> str:
    template = next((t for t in catalog.get("templates", []) if t["id"] == template_id), None)
    return _preset_list(template, with_summary=False) if template else "none"


def _make_video_prompt(goal: str, audience: str, platform: str, catalog: dict) -> str:
    return f"""Make a video with Manim Studio.

Goal: {goal}
Audience: {audience or "not given - choose a sensible audience and say what you assumed"}
Platform: {platform or "not given - use 9:16 for phones, 16:9 for everything else"}

Work in this order:
1. `search_templates(query="{goal}")` for candidates, then `get_template(template)` for the
   exact params schema and presets. Never invent a field: unknown fields are refused.
2. Pick the closest preset and call `quick_video(template, preset=..., params={{...}},
   settings={{...}})`. It creates the project and returns a storyboard image in one call.
3. Look at the storyboard image. Fix clipped or crowded text. To change something, call
   `get_project` first, send the complete params/settings to `update_project`, then
   `preview(project_id, mode="storyboard")` again.
4. When it reads well, `export_project(project_id, format="mp4", quality="1080p")` and poll
   `get_export(export_id)` until `status` is `done`. Give the person `download_url`, the
   project id and `app_url`.

Tactics: 5-7 words per line, one idea per card; respect every maxLength; put numbers in
number fields; wrap one or two key words in *asterisks* for emphasis; no emoji (use icons
from `list_icons()`); leave optional fields empty. Aspect: 16:9 for YouTube/slides, 9:16
with `safe_zone=true` for Shorts/Reels/TikTok/Stories, 4:5 or 1:1 for the Instagram feed.
Music: bundled `calm`, `upbeat` or `playful` in `settings.sound.music.track`, or upload
with `upload_audio`. Read `guide("start")` if unsure.

Templates available:
{_template_menu(catalog)}"""


def _make_quiz_prompt(topic: str, questions: str, catalog: dict) -> str:
    return f"""Make quiz videos with Manim Studio: one question per video.

Topic: {topic}
Questions: {questions}

Work in this order for each question:
1. `get_template("quiz")` for the exact fields, then `quick_video("quiz",
   preset="general-knowledge", params={{...}}, settings={{"theme": "midnight"}})`.
2. params: `label` ("Question 2 of 5"), `question` (plain text, 120 characters at most,
   write 7 x 8 = ? instead of formulas), `options` (2-4 items, each
   {{"text": "..."}} of 40 characters at most; plain strings are accepted),
   `correct` (1-based index into `options`), `think_seconds` (6-10 for a class, 3-30
   allowed), `explanation` (why the answer is right, 120 characters at most), and
   `show_letters` true unless the letters confuse the question.
   To put a whole quiz in one video, add `questions`: up to 11 more questions with those same fields.
3. Look at the storyboard `quick_video` returns: check that `correct` points at the right
   answer, the options fit and the question is readable. Two answers make it true/false.
4. `export_project(project_id, format="mp4", quality="1080p")` and poll `get_export`
   until `done`. Return each `download_url` and project id with its question.

Quiz presets: {_presets_of(catalog, "quiz")}. Use 16:9 for a projector and 9:16 with
`safe_zone=true` for social. The video's length comes from `think_seconds` plus the
reveal, so there is no length setting to tune."""


def _classroom_timer_prompt(minutes: str, activity: str, catalog: dict) -> str:
    try:
        seconds = int(round(float(minutes) * 60))
    except (TypeError, ValueError):
        seconds = None
    seconds_text = f"{seconds} seconds" if seconds is not None else "minutes multiplied by 60"
    seconds_value = seconds if seconds is not None else 300
    return f"""Make a classroom timer video with Manim Studio.

Minutes: {minutes}
Activity: {activity or "a quiet working period"}

Work in this order:
1. `get_template("countdown")`, then `quick_video("countdown", preset="classroom-timer",
   params={{"seconds": {seconds_value}, "title": "{activity or "Quiet working time"}",
   "style": "ring"}}, settings={{"aspect": "16:9", "energy": "calm"}})`.
2. params: `seconds` (3-3600; {seconds_text}), `title` (60 characters at most), `subtitle`
   (80 at most, e.g. "Back at 10:30"), `style` (`ring`, `bar`, or `big` for a 10-to-1
   launch countdown), `finish_text` (40 at most, e.g. "Time's up!"), `warn_last` true,
   `confetti` only when celebrating.
3. The video lasts exactly as long as the timer: the length comes from `seconds`, and
   `settings.length` is ignored. A motion preview only shows the first 20 seconds, so read
   the storyboard rather than waiting for the finish.
4. `export_project(project_id, format="mp4", quality="720p")` (the clock is simple; 720p
   is plenty for a projector) and poll `get_export` until `done`. Tell the person the
   real duration and hand over `download_url` and the project id.

Countdown presets: {_presets_of(catalog, "countdown")}. Use `16:9` for a projector and
`9:16` with `safe_zone=true` for a phone."""


def _announce_event_prompt(what: str, when: str, where: str, catalog: dict) -> str:
    return f"""Make an announcement video with Manim Studio.

What: {what}
When: {when or "not given - leave the time out until the person supplies it"}
Where: {where or "not given - leave it out"}

Work in this order:
1. `get_template("announcement")`, then `quick_video("announcement",
   preset="event-invite", params={{...}}, settings={{"aspect": "9:16"}})`.
2. params: `layout` (`bold`, `split` for a photo, or `poster` for a ticket), `kicker` (28
   characters at most), `headline` (40 at most; wrap one key word in *asterisks*),
   `big_text` (12 at most: a date like "14.06" or a word like "OPEN"), `details` (0-4
   items of {{"text": "...", "icon": "..."}} with 32 characters each), `call_to_action`
   (40 at most) and `qr_text` for a link to show as a QR code.
3. Put when/where/price in `details`, one fact per line, with icons from `list_icons()`
   (calendar, clock, map-pin, ticket). Never more than four details.
4. Look at the storyboard for crowding, then `export_project(project_id, format="mp4",
   quality="1080p")` and poll `get_export` until `done`. Hand over `download_url` and the
   project id. Add a photo with `add_image` first if the person has one.

Announcement presets: {_presets_of(catalog, "announcement")}. Use 9:16 with
`safe_zone=true` for stories and statuses, 16:9 for a screen or slides."""


def _review_video_prompt(project_id: str) -> str:
    return f"""Critique Manim Studio project {project_id} and make it better.

Work in this order:
1. `get_project("{project_id}")` for its template, params, settings and title.
2. `preview("{project_id}", mode="storyboard")` and look at every frame.
3. Judge, in this order: one clear idea per card; text fits with no clipping and no block
   longer than three or four lines; hierarchy (headline carries the message, details
   support it); contrast and theme; reading time per card; aspect and safe zone for the
   destination; sound if the file will play with audio.
4. List the concrete edits as field paths and new values, most important first, and say
   what to keep.
5. Apply them: call `get_project` again, send the complete `params`/`settings` object to
   `update_project`, then `preview(project_id, mode="storyboard")` and show the revision.
6. Export only if the person asked; otherwise hand back the improved project id.

Tactics: 5-7 words per line, one idea per card, respect every maxLength, put numbers in
number fields, use *asterisks* for one or two key words only, no emoji. Read
`guide("writing")` and `guide("look")` for the full rules. Never invent fields: use
`get_template` for the schema."""


# -- registration ----------------------------------------------------------------------

def register_guidance(server, service) -> None:
    """Add `guide`, the MCP prompts and the MCP resources to *server* (built by create_server)."""

    @server.tool(title="Guide", description=(
        "Read the Manim Studio guide before making anything. Topics: start (the workflow), templates, "
        "writing, platforms, look, sound, export, many (one video per list row), troubleshooting. "
        "Returns markdown."))
    async def guide(topic: str = "start") -> str:
        """Guidance for making a good video: start, templates, writing, platforms, look, sound,
        export, many or troubleshooting. Unknown topics list the topics."""
        return await topic_markdown(service, topic)

    @server.prompt(name="make_video", title="Make a video",
                   description="Plan, make and export a video from a plain-language goal.")
    async def make_video(goal: str, audience: str = "", platform: str = "") -> str:
        return _make_video_prompt(goal, audience, platform, await service.catalog())

    @server.prompt(name="make_quiz", title="Make a quiz",
                   description="Make one multiple-choice question video per question.")
    async def make_quiz(topic: str, questions: str = "1") -> str:
        return _make_quiz_prompt(topic, questions, await service.catalog())

    @server.prompt(name="classroom_timer", title="Make a classroom timer",
                   description="Make a countdown video for a lesson, break or activity.")
    async def classroom_timer(minutes: str, activity: str = "") -> str:
        return _classroom_timer_prompt(minutes, activity, await service.catalog())

    @server.prompt(name="announce_event", title="Announce an event",
                   description="Make an announcement video with what, when and where.")
    async def announce_event(what: str, when: str = "", where: str = "") -> str:
        return _announce_event_prompt(what, when, where, await service.catalog())

    @server.prompt(name="review_video", title="Review a video",
                   description="Critique a saved project's storyboard and apply concrete edits.")
    async def review_video(project_id: str) -> str:
        return _review_video_prompt(project_id)

    @server.resource("studio://guide/{topic}", name="guide", title="Manim Studio guide",
                     description="The same markdown as the guide() tool.", mime_type="text/markdown")
    async def guide_resource(topic: str) -> str:
        return await topic_markdown(service, topic)

    @server.resource("studio://catalog", name="catalog", title="Studio catalog",
                     description="Templates, presets, themes, aspects, formats and qualities.",
                     mime_type="application/json")
    async def catalog_resource() -> dict:
        return compact_catalog(await service.catalog())

    @server.resource("studio://templates/{template_id}", name="template",
                     title="Template details",
                     description="Params schema, presets, defaults and tips for one template.",
                     mime_type="application/json")
    async def template_resource_endpoint(template_id: str) -> dict:
        return template_resource(await service.template_info(template_id))
