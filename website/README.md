# Manim Studio website

The site lives entirely in `website/` and uses the existing static hosting setup.
Serve this directory as the site root. No framework, runtime build, package file,
hosting manifest, domain change, or environment variables are required.

Local preview: `python -m http.server 8080 --directory website` from the repository root.

All fonts, artwork, shader previews, and shader code are local. The playground applies
Fluted Glass, Water, and Paper Texture to the same generated nature photograph.
An accessible before/after slider reveals the original. Strength, scale, Water
motion, pause, and PNG capture use real shader rendering. It falls back to actual
rendered examples without WebGL 2, and honors reduced motion. The
shader collection and platform-specific setup commands are interactive. The pinned
scroll showcase starts with the original nature photograph, then uses scroll
position as the Water shader clock and effect strength. Scrolling backwards
reverses the transformation. It has chapter buttons, a skip link, and a static reduced-motion
presentation. The site
focuses on making custom effects with the app's image filters, logo animations,
and generative textures. See BRAND.md for the refracted-light logo and variants.

`node website/build.mjs` optionally refreshes app-derived assets after frontend
dependencies are installed. The generated files are checked in, so static hosts
can serve this folder with their default configuration.

## Artwork and notices

`assets/alpine-dawn.webp` is original artwork generated with the built-in imagegen
tool. The direction was: a serene alpine lake at dawn, still reflective blue water,
layered lilac mountains, a small apricot glow, a rocky island, painterly gouache and
oil texture, spacious sky for white text; no trees, green hills, coastline, fences,
people, lettering, or UI. It replaces the first rejected coastal-valley illustration.
The reference influenced the open composition, serif typography, and translucent
product panel; the artwork, copy, layouts, and working demo are original.

`assets/nature-river.webp` is a second original image generated with the built-in
imagegen tool: editorial landscape photography of an emerald forest river,
waterfall, mossy rocks, and misty alpine mountains. Its exact generation prompt
is saved in `assets/nature-river.prompt.txt`. The generated PNG is preserved in
Codex's generated-images folder; this optimized WebP is the source used by the site.
`assets/shaders/nature-*.webp` are real Paper shader renders of that image, at
768 × 432, strength 0.65, scale 1, and frame 1400 ms. These are new assets; the
previous previews remain available. `image-effects.js` holds the shared uniforms
used for both the live demos and those rendered examples. The hero keeps a single
Get Studio action and briefly mentions video templates, batch creation, and sound.

The shader engine and original sample previews come from Paper Shaders 0.0.82 (Apache 2.0).
Fonts are Newsreader and Inter, both under the SIL Open Font License. Their license
and notice files are bundled in `assets/licenses/`. This website does not include
user projects or uploads.
