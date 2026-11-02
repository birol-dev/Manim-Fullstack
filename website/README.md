# Manim Studio website

The site lives entirely in `website/` and uses the existing static hosting setup.
Serve this directory as the site root. No framework, runtime build, package file,
hosting manifest, domain change, or environment variables are required.

Local preview: `python -m http.server 8080 --directory website` from the repository root.

All fonts, artwork, shader previews, and shader code are local. The playground has
three working effects, palettes, speed/scale controls, pause, and PNG capture. It
falls back to a sample image without WebGL 2, and honors reduced motion. The
shader collection and platform-specific setup commands are interactive. The pinned
scroll showcase uses scroll position as the shader clock, so scrolling backwards
reverses the effect. It has chapter buttons, a skip link, and a static reduced-motion
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

The shader engine and twelve previews come from Paper Shaders 0.0.82 (Apache 2.0).
Fonts are Newsreader and Inter, both under the SIL Open Font License. Their license
and notice files are bundled in `assets/licenses/`. This website does not include
user projects or uploads.
