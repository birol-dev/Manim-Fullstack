const $ = (selector) => document.querySelector(selector);
const palettes = {
  lilac: ['#e0eaff', '#474784', '#efa0b0', '#a58ecb'],
  ember: ['#fff0ce', '#3b1515', '#f77c55', '#c5996c'],
  lagoon: ['#d9f2e7', '#17465a', '#7cb7b6', '#b2d2a4'],
};
const names = { mesh: 'Mesh Gradient', warp: 'Warp', neuro: 'Neuro Noise' };
const images = { mesh: 'mesh-gradient', warp: 'warp', neuro: 'neuro-noise' };
let effect = 'mesh';
let paused = matchMedia('(prefers-reduced-motion: reduce)').matches;
let mount;
let engine;
let usable = false;

function updatePlayback() {
  const speed = Number($('#speed').value);
  mount?.setSpeed(paused ? 0 : speed);
  $('#pause-shader').textContent = paused ? '▶' : 'Ⅱ';
  $('#pause-shader').setAttribute('aria-label', paused ? 'Play preview' : 'Pause preview');
  $('#preview-status').textContent = !usable ? 'Example image' : paused || speed === 0 ? 'Paused' : 'Live preview';
}

function uniforms() {
  const colors = palettes[$('#palette').value].map(engine.getShaderColorFromString);
  const base = { u_fit: 1, u_scale: Number($('#scale').value), u_rotation: 0, u_offsetX: 0, u_offsetY: 0, u_originX: 0.5, u_originY: 0.5, u_worldWidth: 0, u_worldHeight: 0 };
  if (effect === 'mesh') return { ...base, u_colors: colors, u_colorsCount: colors.length, u_distortion: 0.8, u_swirl: 0.2, u_grainMixer: 0.04, u_grainOverlay: 0.03 };
  if (effect === 'warp') return { ...base, u_fit: 0, u_colors: colors, u_colorsCount: colors.length, u_proportion: 0.4, u_softness: 1, u_distortion: 0.25, u_swirl: 0.8, u_swirlIterations: 10, u_shapeScale: 0.2, u_shape: 0, u_noiseTexture: engine.getShaderNoiseTexture() };
  return { ...base, u_fit: 0, u_colorBack: colors[1], u_colorMid: colors[2], u_colorFront: colors[0], u_brightness: 0.05, u_contrast: 0.3 };
}

function swatches() {
  document.querySelectorAll('.palette-swatches i').forEach((node, index) => node.style.background = palettes[$('#palette').value][index]);
}

function showEffect() {
  const host = $('#shader-canvas');
  mount?.dispose();
  mount = undefined;
  host.querySelectorAll('canvas').forEach((canvas) => canvas.remove());
  host.style.backgroundImage = `url('assets/shaders/${images[effect]}.webp')`;
  host.setAttribute('aria-label', `${names[effect]} preview`);
  $('#effect-caption').textContent = `${String(Object.keys(names).indexOf(effect) + 1).padStart(2, '0')} / ${names[effect]}`;
  if (usable) {
    try {
      const shader = effect === 'mesh' ? engine.meshGradientFragmentShader : effect === 'warp' ? engine.warpFragmentShader : engine.neuroNoiseFragmentShader;
      mount = new engine.ShaderMount(host, shader, uniforms(), { preserveDrawingBuffer: true }, paused ? 0 : Number($('#speed').value), 1400, 1, 1_500_000);
    } catch { usable = false; host.querySelector('canvas')?.remove(); }
  }
  $('#shader-fallback').hidden = usable;
  for (const id of ['save-shader', 'pause-shader', 'speed', 'scale', 'palette']) $(`#${id}`).disabled = !usable;
  updatePlayback();
}

document.querySelectorAll('[data-effect]').forEach((button) => button.addEventListener('click', () => {
  effect = button.dataset.effect;
  document.querySelectorAll('[data-effect]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  showEffect();
}));
$('#palette').addEventListener('change', () => { swatches(); mount?.setUniforms(uniforms()); });
$('#speed').addEventListener('input', () => { $('#speed-value').textContent = `${Math.round(Number($('#speed').value) * 100)}%`; updatePlayback(); });
$('#scale').addEventListener('input', () => { $('#scale-value').textContent = `${Math.round(Number($('#scale').value) * 100)}%`; mount?.setUniforms(uniforms()); });
$('#pause-shader').addEventListener('click', () => { paused = !paused; updatePlayback(); });
$('#save-shader').addEventListener('click', () => {
  mount?.canvasElement.toBlob((blob) => {
    if (!blob) { $('#download-status').textContent = 'Could not save that frame. Please try again.'; return; }
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = `manim-studio-${images[effect]}.png`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    $('#download-status').textContent = 'Your PNG download has started.';
  }, 'image/png');
});
swatches(); updatePlayback();
try {
  engine = await import('./assets/shader-engine.js');
  // The vanilla renderer expects texture images to have finished decoding.
  await engine.getShaderNoiseTexture().decode();
  const probe = document.createElement('canvas'), gl = probe.getContext('webgl2');
  usable = !!gl; gl?.getExtension('WEBGL_lose_context')?.loseContext();
} catch { usable = false; }
showEffect();
window.addEventListener('pagehide', () => { mount?.dispose(); mount = undefined; });
window.addEventListener('pageshow', (event) => { if (event.persisted) showEffect(); });

const collections = {
  filters: [['paper-texture', 'Paper Texture', 'Folds, fibers, and beautiful imperfections'], ['fluted-glass', 'Fluted Glass', 'A new perspective through sculpted glass'], ['water', 'Water', 'Ripples, reflections, and dancing light']],
  logos: [['heatmap', 'Heatmap', 'A flowing thermal glow'], ['liquid-metal', 'Liquid Metal', 'Your logo, cast in living chrome'], ['gem-smoke', 'Gem Smoke', 'Luminous color around your silhouette']],
  textures: [['grain-gradient', 'Grain Gradient', 'Color with a little character'], ['voronoi', 'Voronoi', 'Living cells and crystalline edges'], ['god-rays', 'God Rays', 'A little atmosphere. A lot of light.']],
};
document.querySelectorAll('[data-collection]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-collection]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  const cards = collections[button.dataset.collection].map(([id, title, type]) => {
    const card = document.createElement('a'), picture = document.createElement('div'), image = document.createElement('img'), caption = document.createElement('span'), small = document.createElement('small'), arrow = document.createElement('b');
    card.className = 'template-card'; card.href = '#start';
    image.src = `assets/shaders/${id}.webp`; image.alt = `${title} shader preview`; image.width = 768; image.height = 432;
    picture.append(image); caption.textContent = title; small.textContent = type; arrow.textContent = '↗'; arrow.setAttribute('aria-hidden', 'true'); caption.append(small, arrow); card.append(picture, caption); return card;
  });
  $('#template-grid').replaceChildren(...cards);
}));

document.querySelectorAll('[data-platform]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-platform]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  const unix = button.dataset.platform === 'unix';
  $('#setup-commands').textContent = `git clone https://github.com/birol-dev/Manim-Fullstack.git\ncd Manim-Fullstack\n${unix ? 'python3' : 'python'} run.py`;
  $('#platform-note').textContent = unix ? 'macOS and Linux also need Cairo and Pango. Follow the setup guide below.' : 'The launcher prepares the app and opens it in your browser.';
}));
$('#copy-commands').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#setup-commands').textContent); $('#copy-status').textContent = 'Setup commands copied.'; $('#copy-commands').textContent = 'Copied ✓'; }
  catch { $('#copy-status').textContent = 'Select the commands above and copy them manually.'; $('#copy-commands').textContent = 'Select to copy'; }
  setTimeout(() => $('#copy-commands').textContent = 'Copy ⧉', 2500);
});
