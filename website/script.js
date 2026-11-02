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
    picture.append(image); caption.textContent = title; small.textContent = type; arrow.textContent = '↗'; arrow.setAttribute('aria-hidden', 'true'); caption.append(arrow); card.append(picture, caption); return card;
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

// Scroll position is the animation clock: reversing the scroll reverses the effect.
const story = $('#scroll-story');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const chapters = [
  ['Pick a shader.', 'A starting point for something yours.', 'Warp / a little curiosity'],
  ['Make it yours.', 'Your color. Your texture. Your motion.', 'Warp / your own direction'],
  ['Keep the effect.', 'PNG or WebM. Ready for your next idea.', 'Warp / ready to take with you'],
];
let storyMount;
let scrollFrame = 0;
let currentChapter = -1;
function storyUniforms(progress) {
  const start = ['#e8eadf', '#547f83', '#8ebfc0', '#b4bac9'].map(engine.getShaderColorFromString);
  const finish = ['#fce8c6', '#3f2d67', '#a88dbb', '#e2ac95'].map(engine.getShaderColorFromString);
  const colors = start.map((color, index) => color.map((channel, c) => channel + (finish[index][c] - channel) * progress));
  return { u_fit: 0, u_scale: 0.65 + progress * 0.9, u_rotation: progress * 35, u_originX: 0.5, u_originY: 0.5, u_offsetX: 0, u_offsetY: 0, u_worldWidth: 0, u_worldHeight: 0,
    u_colors: colors, u_colorsCount: 4, u_proportion: 0.45, u_softness: 0.95, u_distortion: 0.05 + progress * 0.8,
    u_swirl: 0.15 + progress * 0.85, u_swirlIterations: 10, u_shapeScale: 0.17 + progress * 0.25, u_shape: 0, u_noiseTexture: engine.getShaderNoiseTexture() };
}
function renderStory(progress, explicit = false) {
  progress = Math.min(1, Math.max(0, progress));
  const chapter = progress < 0.33 ? 0 : progress < 0.72 ? 1 : 2;
  if (chapter !== currentChapter) {
    currentChapter = chapter;
    $('#scrub-title').textContent = chapters[chapter][0]; $('#scrub-copy').textContent = chapters[chapter][1]; $('#scrub-badge').textContent = chapters[chapter][2];
    $('#scrub-step').textContent = `0${chapter + 1} / 03`;
    document.querySelectorAll('[data-chapter]').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.chapter) === chapter)));
  }
  $('#scrub-progress').value = progress;
  if (!reducedMotion || explicit) {
    story.style.setProperty('--scrub-scale', String(0.88 + Math.sin(progress * Math.PI) * 0.12));
    story.style.setProperty('--scrub-rotate', `${-2 + progress * 4}deg`);
    storyMount?.setUniforms(storyUniforms(progress));
    storyMount?.setFrame(progress * 18_000);
  }
}
function updateStory() {
  scrollFrame = 0;
  if (reducedMotion) return;
  const box = story.getBoundingClientRect();
  if (box.top > innerHeight || box.bottom < 0) return;
  renderStory(-box.top / Math.max(1, box.height - innerHeight));
}
function scheduleStory() { if (!scrollFrame) scrollFrame = requestAnimationFrame(updateStory); }
function initStory() {
  if (usable) {
    try { storyMount = new engine.ShaderMount($('#scrub-canvas'), engine.warpFragmentShader, storyUniforms(0), { preserveDrawingBuffer: true }, 0, 0, 1, 1_500_000); }
    catch { $('#scrub-canvas').querySelector('canvas')?.remove(); }
  }
  if (reducedMotion) renderStory(0, true); else scheduleStory();
}
document.querySelectorAll('[data-chapter]').forEach((button) => button.addEventListener('click', () => {
  const progress = Number(button.dataset.chapter) / 2;
  if (reducedMotion) renderStory(progress, true);
  else { const box = story.getBoundingClientRect(); window.scrollTo({ top: scrollY + box.top + progress * (box.height - innerHeight), behavior: 'smooth' }); }
}));
addEventListener('scroll', scheduleStory, { passive: true }); addEventListener('resize', scheduleStory, { passive: true });
addEventListener('pagehide', () => { cancelAnimationFrame(scrollFrame); storyMount?.dispose(); storyMount = undefined; });
addEventListener('pageshow', (event) => { if (event.persisted) { $('#scrub-canvas').querySelectorAll('canvas').forEach((canvas) => canvas.remove()); initStory(); } });
initStory();
