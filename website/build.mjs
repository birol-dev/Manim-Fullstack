/** Refresh bundled app assets. The resulting website is ordinary static HTML/CSS/JS. */
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { build } from '../frontend/node_modules/rolldown/dist/index.mjs';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
for (const dir of ['fonts', 'templates', 'licenses', 'shaders']) await mkdir(path.join(here, 'assets', dir), { recursive: true });
const copy = (source, destination) => copyFile(path.join(root, source), path.join(here, 'assets', destination));
await copy('frontend/node_modules/@fontsource-variable/newsreader/files/newsreader-latin-wght-normal.woff2', 'fonts/newsreader.woff2');
await copy('frontend/node_modules/@fontsource-variable/newsreader/files/newsreader-latin-wght-italic.woff2', 'fonts/newsreader-italic.woff2');
await copy('frontend/node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2', 'fonts/studio-sans.woff2');
await copy('frontend/node_modules/@fontsource-variable/newsreader/LICENSE', 'licenses/Newsreader-OFL.txt');
await copy('frontend/node_modules/@fontsource-variable/inter/LICENSE', 'licenses/Inter-OFL.txt');
await copy('frontend/node_modules/@paper-design/shaders/LICENSE', 'licenses/Paper-Shaders-LICENSE.txt');
await copy('frontend/node_modules/@paper-design/shaders/NOTICE', 'licenses/Paper-Shaders-NOTICE.txt');
// The nature filter previews are checked-in renders using image-effects.js uniforms.
await build({ input: path.join(here, 'engine-source.mjs'), output: { file: path.join(here, 'assets/shader-engine.js'), format: 'esm', minify: true } });
const bundle = path.join(here, 'assets/shader-engine.js');
await writeFile(bundle, (await readFile(bundle, 'utf8')).replace(/[\t ]+$/gm, ''));
await import('./pages.mjs');
console.log('Website assets refreshed. Serve website/ directly; no runtime build is needed.');
