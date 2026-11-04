# Manim Studio website

Serve `website/` as the root on the existing static host. The seven checked-in
HTML pages work directly, without a framework, runtime build, or hosting changes.

Preview from the repository root:

```text
python -m http.server 8080 --bind 127.0.0.1 --directory website
```

## Pages and authoring

- `index.html`: overview of the complete local creative studio and a nature filter demo.
- `templates.html`: real gallery examples, editing, layouts, and export formats.
- `shaders.html`: all seven image filters with a working before/after playground.
- `workflows.html`: spreadsheet batches, a downloadable example, music, and sound.
- `author.html`: the Python scene editor, rendering, timeline, and assets.
- `ai.html`: compatible AI connections through MCP and how saved projects are shared.
- `get-started.html`: Windows releases, source setup, platform commands, and FAQs.

The header and footer link to real HTML pages in the same browser tab. Mobile
navigation has an accessible menu, Escape dismissal, and a no-JavaScript fallback.

Edit the content and shared layouts in `pages.mjs`, then run:

```text
node website/pages.mjs
```

This regenerates all seven HTML files and the sitemap, copies six real bundled
template posters, and writes the sample CSV. Commit the outputs with their source.
Shared styling lives in `style.css`; navigation, category filters, and source setup
controls live in `script.js`. Shader code loads only on the two playground pages.

`node website/build.mjs` additionally refreshes bundled fonts, licenses, and the
shader engine from installed frontend dependencies, then regenerates the pages.
All generated assets are checked in, so serving the site needs no dependencies.

## Image filters and artwork

The scenic background is the original generated `assets/alpine-dawn.webp`: an alpine
lake at dawn, reflective blue water, lilac mountains, and a small apricot glow.
`assets/nature-river.webp` is original generated editorial nature photography of
an emerald forest river, waterfall, mossy rocks, and misty alpine mountains. Its
generation prompt is preserved in `assets/nature-river.prompt.txt`.

Every displayed effect uses that forest photograph. The gallery shows Fluted Glass,
Lens Distortion, Water, Paper Texture, Halftone Dots, Halftone CMYK, and Image
Dithering. No abstract texture or logo-effect examples appear in the website UI.
The `assets/shaders/nature-*.webp` files are actual shader renders at 768 × 432,
strength 0.65, scale 1, frame 1400 ms, using the uniforms in `image-effects.js`.

`playground.js` provides real controls, PNG export, reset, and the before/after
slider. Non-WebGL browsers see the rendered examples with live controls disabled.
Motion respects reduced-motion preferences and stops when the playground is out
of view or the page is hidden. Back/forward cache restoration recreates the canvas.

All fonts, images, shader code, and template posters are local. See `BRAND.md` for
the refracted-light logo. Paper Shaders 0.0.82 is Apache 2.0; Newsreader and Inter
are under the SIL Open Font License. Licenses and notices are in `assets/licenses/`.
No user projects or uploads are included.
