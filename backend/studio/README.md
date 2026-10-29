# Template studio

Fill-in templates rendered with Manim. People use them through the Studio UI (gallery →
form → preview → export); agents use them through MCP. Both go through one service layer.

```text
backend/studio/
  schema.py      field helpers, TemplateMeta, Preset, RenderSettings      (no Manim)
  themes.py      theme tokens                                              (no Manim)
  formats.py     aspect -> pixels, frame sizing (short side = 8 units)     (no Manim)
  numfmt.py      locale-aware number formatting                            (no Manim)
  registry.py    template discovery, catalog, validate_job()               (no Manim)
  runner.py      the one file Manim renders for exports (static)
  dev.py         render a template's posters/storyboards/videos to look at
  kit/           the template kit (imports Manim): StudioScene, fit_text, Counter, shapes, media
  templates/<id>/schema.py   META, Params, PRESETS   (no Manim)
  templates/<id>/scene.py    class Template(StudioScene)
  assets/fonts/  bundled .ttf/.otf, registered with Pango at render time
  assets/icons/  bundled line icons (<name>.svg), used by kit.media.icon()
```

Modules outside `kit/` and `templates/*/scene.py` must never import Manim: it takes ~3 s
to load, and the API and MCP server use them on every request.

## Shipped gallery posters

Run `python -m backend.studio.bake_posters` from the repository root after changing a
template, preset, kit, render settings, font or icon. This uses the warm worker to bake
every catalog preset with the gallery's exact params/settings and 360px short side.
`assets/posters/manifest.json` maps each preset to its portable content-based cache key.
The freshness test fails with the rebake command when a preset is missing or stale.
Desktop packaging checks freshness, then copies the whole backend tree including
`assets/posters/`. First requests copy exact matching PNGs into the writable preview
cache; changed requests or stale artwork fall through to normal rendering.

The tool uses `workspace/studio/tmp/poster-bake` as scratch space. In a restricted environment,
use `--work-dir frontend/node_modules/.cache/poster-bake`.

## Motion previews

`POST /api/studio/motion` accepts `{project, template, params, settings}`. `project` is
a project id or a stable editor-session id. It returns a job immediately; poll
`GET /api/studio/motion/<id>` and cancel with `DELETE` on the same path. A newer
request for the same project cancels its previous job. MCP `preview` also accepts
`mode="motion"`; poll `get_motion` or stop it with `cancel_motion`.

A separate warm `PreviewWorker` renders silent MP4s at 720px on the long side and
15fps, independently of the export queue and still/storyboard worker. Playback is
limited to the **first 20 seconds of the real timeline**; it does not speed up a long
countdown. The response includes `duration` and `truncated` for the UI caption.
Only an explicit Play click starts rendering. Edits cancel the pending job and return
to the still. Finished videos share the bounded preview cache, with keys covering
template/kit/icons, content, settings, uploaded asset stamps and preview limits.

## Writing a template

`templates/<id>/schema.py`:

```python
from typing import Literal
from studio.schema import TemplateMeta, TemplateParams, Item, Preset, text, number, choice, toggle, items, image, icon, color, HexColor

META = TemplateMeta(id="<id>", title=..., summary=..., category="announce", when_to_use=..., not_for=...)

class Params(TemplateParams):
    headline: str = text("Big Sale", title="Headline", max_length=40)
    ...

PRESETS = [Preset(id="weekend-sale", title="Weekend sale", summary=..., params={...}, settings={"theme": "pop"})]
```

* Every field has a `title` (form label); give agents a `description` where it isn't obvious.
* Limits (`max_length`, `ge/le`, `min_items/max_items`) are what the layout is tested against.
  Pick them so the longest allowed content still looks good.
* Optional text is `""` (empty = hidden). Optional images/icons/colors are `None`.
* Presets are gallery cards: realistic, ready-to-use content, each with its own theme/look.
  A good template has 2-5 presets that show its range.

`templates/<id>/scene.py`:

```python
from manim import *
from studio.kit import StudioScene, fit_text, label, Counter, shapes, media, size_for_height
from .schema import META, Params

class Template(StudioScene):
    Params = Params
    META = META

    def build(self):
        p, theme, lay, m = self.p, self.theme, self.layout, self.motion
        ...
```

What `StudioScene` gives you:

| | |
|---|---|
| `self.p` | validated Params |
| `self.s` | RenderSettings (aspect, length, theme, background, brand, energy, ending, safe_zone, locale) |
| `self.theme` | `bg bg2 surface text muted line on_accent accent(i) font display_weight radius display(text)` |
| `self.layout` | safe area: `point(x, y)` in fractions, `region(x0,y0,x1,y1)`, `safe.split_rows/split_cols`, `Region.fit(mob)`, `is_portrait/is_landscape/is_square`, `unit` (1% of short side) |
| `self.motion` | `appear(mob, style)` (rise, drop, slide_left, slide_right, fade, pop, grow, write), `appear_each(mobs, style)`, `leave(*mobs)`, `enter/exit/stagger` durations, `t(seconds)`, `reading_time(text)` — all scaled by energy |
| `self.asset(name)` | path of an uploaded image named in params, or None |
| `self.poster()` | call at the most representative moment (thumbnails); optional |
| `self.target_length` | the requested length; `construct` pads with a hold to reach it. Templates whose content sets the length (timers) set it themselves |
| `self.remaining()` | seconds left before the ending |

After `build()` the base class holds until `target_length` and plays the ending
(`hold` / `fade` / `cut`). Don't fade everything out yourself.

Kit helpers:

* `fit_text(text, width=, height=, size=, min_size=, max_lines=, font=theme.font, weight=, color=, emphasis_color=, align=)` —
  wraps (balanced), shrinks to fit, `*word*` emphasis. Use it for anything a person types.
* `label(text, size=, max_width=)` — a single line that shrinks, never wraps.
* `Counter(value, size=, fmt={...}|formatter=)` + `counter.counting(start, end)` — animated
  numbers without per-frame Pango (never `always_redraw(lambda: Text(...))`: 2.7x slower).
  `fmt` = `numfmt.format_number` keywords; pass `locale=self.s.locale`.
* `size_for_height(h, font=, weight=)` — font size whose digits are `h` units tall.
* `shapes.card / pill / badge / divider / full_frame / Confetti / qr_code(data, size=)`.
* `media.image(path, height=, width=, shape="any|square|circle|rounded")`, `media.svg_logo(path, height=)`,
  `media.icon(name, size=, color=)`.

Rules:

1. Lay out from `self.layout` only — no absolute coordinates. Every template must look
   right in 16:9, 9:16, 1:1 and 4:5 (or restrict `META.aspects`).
2. Colors from `self.theme` (or a color param). Fonts from `theme.font`.
3. All typed text through `fit_text`/`label`; numbers through `Counter` or `numfmt`.
4. Nothing may leave the safe area or overlap other text, with the longest allowed content.
5. No LaTeX (`MathTex`, `Tex`, `DecimalNumber`, `Integer`, `NumberLine` labels, axis numbers).
6. Speed budget: an export at 1080p30 should take at most ~2x the video's length.
7. Text must be readable on a phone: nothing smaller than `size=24` (short side is always 8 units).

Check your work:

```bash
python backend/studio/dev.py <id>                         # posters + storyboards, every preset, 3 aspects
python backend/studio/dev.py <id> --aspects 4:5 --params '{"headline": "the longest text allowed..."}'
python backend/studio/dev.py <id> --video --quality 720p --preset <preset>
```

Output lands in `workspace/.studio-dev/`; open the PNGs and look at them.

## Service and HTTP API (`/api/studio`)

The service layer (`studio/service.py`) is what both the REST routes (`studio/api.py`) and
the MCP server (`studio/mcp_server.py`) call. Validation errors come back as
`registry.TemplateError` with `errors = [{"field": "params.items.2.value", "message": ...}]`.

| Method & path | Body | Returns |
|---|---|---|
| `GET /api/studio/catalog` | — | `{sections: [{id, title, cards: [card]}], templates: [template], themes: [theme], aspects, qualities}` |
| `POST /api/studio/preview` | `{template, params, settings, mode: "poster"\|"storyboard"}` | `{url, mode, width, height, cached, ms, storyboard?: {frames, columns, times, frame_size, length}}`; 422 `{detail, errors}` |
| `POST /api/studio/exports` | `{template, params, settings, format: "mp4"\|"gif"\|"webm"\|"mov"\|"png", quality: "draft"\|"720p"\|"1080p"\|"1080p60"\|"4k", title?}` | 202 `export` |
| `GET /api/studio/exports` | — | `[export]`, newest first |
| `GET /api/studio/exports/{id}` | — | `export` |
| `DELETE /api/studio/exports/{id}` | — | cancels a queued or running export |
| `GET /api/studio/projects` | — | `[{id, title, template, updated, poster_url}]` |
| `POST /api/studio/projects` | `{title?, template, params, settings}` | `project` |
| `GET/PUT/DELETE /api/studio/projects/{id}` | PUT: `{title?, params?, settings?}` | `project` |
| `GET /api/studio/icons` | — | `[name]`; each served at `/api/studio/icons/{name}.svg` |
| `POST /api/studio/images` | `{data: base64 or data URL}` (PNG/JPEG/GIF/WebP/SVG, ≤ 8 MB) | 201 `{name, width, height}`; `name` goes in an image field |

* `card` = `{id, template, title, summary, category, params, settings, tags}` (a preset).
* `template` = TemplateMeta fields + `schema` (JSON Schema of Params; `x-widget` per field) + `defaults` + `presets`.
* `theme` = `{id, name, dark, bg, text, accent: [5 colors]}`.
* `export` = `{id, template, title, format, quality, status: "queued"|"rendering"|"done"|"failed"|"cancelled", progress: 0-100|null, message, url?, filename?, size?, duration?, error?, created}`.
* `project` = `{id, title, template, params, settings, created, updated}` (stored as `workspace/studio/projects/<id>.json`).
* Images in params are file names from the existing upload endpoint (`POST /api/upload-asset`, served at `/assets/<name>`).
* Previews are cached by a hash of (template id + version, params, settings, mode) and served from `/media/studio/previews/`.
  Exports land in `workspace/media/studio/exports/` (served at `/media/studio/exports/...`).

### Form widgets (`x-widget` in the JSON Schema)

`text`, `textarea`, `number`, `integer`, `duration` (seconds; shown as mm:ss), `choice`
(enum; `x-labels` maps values to labels), `toggle`, `color` (`#RRGGBB` or null = theme),
`image` (asset file name; `x-shape`: any/circle/logo), `icon` (bundled icon name), `list`
(array of objects; `x-item-title`), `table` (array of objects shown as a grid that accepts
pasted rows from a spreadsheet). Other keys: `title` (label), `description` (help),
`maxLength`, `minimum`/`maximum`, `minItems`/`maxItems`, `x-placeholder`, `x-unit`, `x-step`.

## Agent connections (MCP)

The app mounts Streamable HTTP at `/mcp/`. The gallery's **Connect to AI** button
returns the actual address and a workspace credential. This credential works only
for Studio projects, previews, exports and MCP tools; it does not open the Author API
in desktop mode. The server's Host/Origin checks also apply to MCP.

Tools: `search_templates`, `get_template`, `create_project`, `list_projects`,
`get_project`, `update_project`, `preview`, `export_project`, `get_export`,
`cancel_export`, `add_image`, `list_icons`. A preview returns an image for the agent to inspect.
`get_template` also returns `settings_schema` (themes, formats, background, brand, timing).
`add_image` takes base64 and returns the name to put in an image field.
Exports return immediately; poll `get_export` for the completed download URL.
Project updates replace each supplied object; fetch first to preserve other fields.
Draft projects can save incomplete input, while previews and exports validate it.

For clients that use stdio, run the bridge against the same running app:

```json
{
  "mcpServers": {
    "manim-studio": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/Manim/backend/studio/mcp_server.py", "--url", "http://127.0.0.1:8000", "--token-file", "/absolute/path/to/workspace/studio/mcp-token"]
    }
  }
}
```

The bridge shares the app's queue and projects; it does not launch a second backend.
Install `backend/requirements.txt` in that Python environment. For custom credentials
use `MANIM_MCP_TOKEN` on the server and `COMPOSER_TOKEN` on the bridge. Keep credentials
private; removing `workspace/studio/mcp-token` creates a new one on next connection.

Desktop launchers may set `MANIM_WORKSPACE`, `MANIM_FRONTEND_DIR` and `MANIM_API_TOKEN`.
With a desktop token set, `/api/desktop/session?token=...` exchanges the launch token
for an HttpOnly session cookie and redirects to `/`; HTTP and Author WebSockets then
require that session. The desktop launcher disables access logs to keep it out of URLs
in logs. The agent credential stays separate and must be sent explicitly as a bearer
header at `/mcp/`, even when a browser session is active.
