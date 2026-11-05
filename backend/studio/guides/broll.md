# Technical B-roll with Manim

Make each clip answer one visual question from the brief. The viewer should be able to point to the thing that changes and say what the change means. A diagram can carry the narration through its states without putting the whole script on screen.

## Plan the shots

1. Use the supplied script, timestamps, or reference to identify the beats. For each beat, write down the input, the operation, the result, and the object the eye should follow. If timing is open, start with a 6–10 second shot. Use the requested aspect, or start at 16:9.
2. Pick the visual that fits the operation. Use a row highlight for a scan, a tree for a decision, arrows for a data path, a comparison with aligned panels for a trade-off, or bars on the same scale for a quantity. Keep the same input visible through the comparison.
3. Block the shot into establish, change, and hold. Show the starting state, make each new event follow a narration cue, and hold the result for roughly one second or until the editor's cut. Leave room around the edges for crops, captions, or a talking head when requested.
4. Plan related clips as a set. Choose a background, type scale, stroke widths, and a color key once. Give files and scenes ordered names such as `01_scan.py` / `Clip01Scan` so the editor can assemble them in order. Use silence unless the brief calls for sound.

## Draw for the viewer

- Put the changing object first in the visual hierarchy. Keep stable objects in the same place across beats. Dim inactive branches or rows and pair the active color with a stroke, label, or moving marker so color is one of several cues.
- Use one display size for the main claim, one for labels, and monospaced type for literal keys, SQL, or counters. A few rows and an ellipsis can represent a large table. Check text at the size the clip will be viewed.
- Use accent colors consistently. The reference uses green for a chosen path or match and amber or red for work, cost, and rejected cases. Pick the palette for the project and reserve saturated color for meaning. Use high-contrast text even on dim panels.
- Build related objects as `VGroup`s, align them, then attach edges to their actual bounds. Place labels after the geometry fits. A fixed diagram with a few local changes is easier to follow during narration than repeated camera motion.
- Use `FadeIn` or `LaggedStart` to establish structure, `Create` to trace a line, `Transform` or `.animate` to change the same object, and `Indicate` or a fill change to mark a result. Keep the transform anchored so it is clear which object changed. Use `wait()` for readable holds and clean cuts.
- Treat figures in an explainer as measurements only when the brief supplies evidence. For a teaching example, use small numbers the viewer can count and label the drawing as simplified. Check that the keys, arrows, and outcome agree. Verify engine-specific claims before putting them on screen.

## Reference study

*Database Indexes Explained In 6 Minutes* builds almost all of its shots from a small set of elements on a quiet, dark stage. The table below maps observed shots and narration to Manim techniques. The production tool is unverified.

| Approximate time | What the shot teaches | How to build the visual in Manim |
| --- | --- | --- |
| 0:00–0:34 | A query triggers a row-by-row scan, then the view switches to a growing latency curve. | Keep the query above a table made from aligned text and rectangles. Move one highlight down the rows. Cut to `Axes` with a drawn curve and a counter tied to a `ValueTracker`. |
| 0:36–1:10 | A textbook's page scan and index explain the difference before the video returns to database rows and pointers. | Use two equal panels with the same target. Advance a page counter on the left. Reveal the entry and its page chips on the right. Reuse the layout for a sorted index and the rows it points to. |
| 1:28–2:33 | The B-tree grows one layer at a time, then a single lookup moves from the separators to a leaf and finally a table row. | Arrange root, internal nodes, and leaves in aligned rows. Keep the search key pinned. Show one comparison beside the active edge, dim rejected branches, and highlight the row only when the leaf pointer reaches it. |
| 2:35–2:55 | A hash can route one exact key to a bucket, while a range has no corresponding ordered route in that drawing. | Use three fixed groups for input, function, and buckets. Move the input through the function, highlight one cell, then switch the input to a range and explain the missing order with a label. |
| 2:56–4:08 | The same SQL stays on screen as the video compares separate and composite indexes, then illustrates column order with a phone book. | Anchor the SQL above the changing panels. Animate each path under it. Keep the query variants aligned for comparison and use a check, label, or strikethrough on the relevant case. |
| 4:20–5:33 | The covering example removes a lookup step. The clustered example reorders the same row tiles and highlights an adjacent range. | Hold the left and right layouts fixed for the path comparison. Dim the skipped table step while leaving its outline visible. Reposition the existing row tiles by key, then select the contiguous range. |
| 5:36–6:27 | An insert fans out to index updates. Storage bars and a final two-part summary make the cost visible. | Reveal the branches in order and count the visible updates. Use a common baseline for the storage bars. End on the read/write trade-off with enough time to read both sides. |

The reusable pattern is **show the problem → reveal the structure → trace one real example → hold the consequence**. Match that progression to the user's narration. Use the reference's restraint and timing with an original layout, labels, and data.

## Render, look, revise

1. Use `write_script` with a `.py` filename and complete Manim Community source. For an existing file, call `read_script` and supply its `version` as `base_version`. Custom scenes require **Allow AI apps to write and run Python** in Studio's **AI apps** settings.
2. Queue `render_scene` with the file, class name, saved `version`, and `quality="l"`. Poll `get_scene_render` while it is queued or rendering. On a failure, read the returned logs, fix the source, and render the updated version.
3. On success, call `inspect_scene_render` and look at the contact sheet. Check the opening, changes in focus, and the held result. Inspect text contrast, edge padding, arrow endpoints, alignment, and whether the viewer can see the intended action at each sampled time. Watch playback in Author mode when checking motion between samples or exact narration sync.
4. Revise any frame that fails the check, then render at `quality="h"` for 1080p or the requested quality. Return the Author mode output location, source filename, and clip duration or narration beat for each clip. Use `make_many` when each row repeats the same installed template. Write separate scenes when the shots need different structures or motion.

## Work together in Design Studio

Open **Design Studio** from the Manim Studio sidebar. Agent writes and renders appear in its activity list. Open a shot from that list to edit its Python and watch the preview update as new renders finish. Share the `design_url` from `get_scene_render` when handing a shot back to the user.

Expose a few design choices the user is likely to iterate on. Put each in a top-level constant with a double-quoted string and a `# studio:` label. Six-digit hex colors get a color picker. The panel edits the same Python source, so read the latest version before the next agent change. Use the constants in the scene and give editable headings enough room to grow.

```python
TITLE = "Follow the index"  # studio: Headline
ACCENT = "#8BE2B4"  # studio: Lookup color
```

**Try Index lookup** opens an editable starter in the app. It keeps the query and table in place, traces one branch, and holds on the fetched row.

## Example shot

The following short clip traces one matching branch through a simplified index. The title and key stay visible as the focus moves, and the end frame holds the match for a cut.

```python
from manim import FadeIn, LaggedStart, Line, RoundedRectangle, Scene, Text, VGroup


class Clip01IndexLookup(Scene):
    def construct(self):
        self.camera.background_color = "#111820"
        ink, muted, edge, active = "#F0F4F6", "#A2B1BE", "#647788", "#7DE0B9"

        def node(label, position):
            box = RoundedRectangle(width=2.55, height=0.75, corner_radius=0.10,
                                   stroke_width=2, stroke_color=edge,
                                   fill_color="#1D2933", fill_opacity=1)
            text = Text(label, font_size=25, color=ink).move_to(box)
            return VGroup(box, text).move_to(position)

        title = Text("Find key 42", font_size=46, color=ink).move_to([0, 3, 0])
        root = node("30     60", [0, 1.35, 0])
        leaves = [node("10     20", [-3.2, -1.05, 0]),
                  node("35   42   51", [0, -1.05, 0]),
                  node("68     81", [3.2, -1.05, 0])]
        links = [Line(root.get_bottom(), leaf.get_top(), buff=0.06,
                      color=edge, stroke_width=2).set_z_index(-1) for leaf in leaves]
        reason = Text("30 ≤ 42 < 60", font_size=24, color=muted).move_to([1.6, 0.12, 0])
        result = Text("Key 42 found", font_size=32, color=active).move_to([0, -2.60, 0])

        self.play(FadeIn(title), FadeIn(root), run_time=0.65)
        self.play(LaggedStart(*(FadeIn(VGroup(link, leaf)) for link, leaf in zip(links, leaves)),
                              lag_ratio=0.16), run_time=0.9)
        self.wait(0.35)
        self.play(links[1].animate.set_stroke(active, width=4),
                  leaves[1][0].animate.set_stroke(active, width=3),
                  VGroup(links[0], links[2], leaves[0], leaves[2]).animate.set_opacity(0.36),
                  FadeIn(reason), run_time=0.65)
        self.play(FadeIn(result), run_time=0.45)
        self.wait(1.25)
```
