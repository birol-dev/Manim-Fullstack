import { imageEffects, imageUniforms, natureSource } from './image-effects.js';
const $ = (selector) => document.querySelector(selector);
const natureImage = new Image();
natureImage.src = natureSource;
let effect = 'glass';
let paused = matchMedia('(prefers-reduced-motion: reduce)').matches;
let mount;
let engine;
let usable = false;

function updatePlayback() {
  const speed = Number($('#speed').value);
  mount?.setSpeed(paused || effect !== 'water' ? 0 : speed);
  $('#pause-shader').textContent = paused ? '▶' : 'Ⅱ';
  $('#pause-shader').setAttribute('aria-label', paused ? 'Play preview' : 'Pause preview');
  $('#preview-status').textContent = !usable ? 'Example image' : paused ? 'Paused' : effect !== 'water' || speed === 0 ? 'Live filter' : 'Live preview';
  $('#speed').disabled = !usable || effect !== 'water';
  $('#pause-shader').disabled = !usable || effect !== 'water';
}

function uniforms() {
  return imageUniforms(engine, natureImage, effect, Number($('#strength').value), Number($('#scale').value));
}

function showEffect() {
  const host = $('#shader-canvas');
  mount?.dispose();
  mount = undefined;
  host.querySelectorAll('canvas').forEach((canvas) => canvas.remove());
  const selected = imageEffects[effect];
  host.style.backgroundImage = `url('assets/shaders/nature-${selected.file}.webp')`;
  host.setAttribute('aria-label', `Nature image transformed by ${selected.name}`);
  $('#comparison-effect-label').textContent = selected.name;
  $('#effect-caption').textContent = `${String(Object.keys(imageEffects).indexOf(effect) + 1).padStart(2, '0')} / ${selected.name}`;
  if (usable) {
    try {
      mount = new engine.ShaderMount(host, engine[selected.shader], uniforms(), { preserveDrawingBuffer: true }, paused || effect !== 'water' ? 0 : Number($('#speed').value), 1400, 1, 1_500_000, ['u_image']);
    } catch { usable = false; host.querySelector('canvas')?.remove(); }
  }
  $('#shader-fallback').hidden = usable;
  for (const id of ['save-shader', 'strength', 'scale']) $(`#${id}`).disabled = !usable;
  updatePlayback();
}

function chooseEffect(next) {
  if (!imageEffects[next]) return;
  effect = next;
  document.querySelectorAll('[data-effect]').forEach((item) => item.setAttribute('aria-pressed', String(item.dataset.effect === effect)));
  showEffect();
}
document.querySelectorAll('[data-effect]').forEach((button) => button.addEventListener('click', () => chooseEffect(button.dataset.effect)));
$('#template-grid').addEventListener('click', (event) => {
  const card = event.target.closest('[data-try-effect]');
  if (card) chooseEffect(card.dataset.tryEffect);
});
$('#compare').addEventListener('input', () => {
  $('#image-comparison').style.setProperty('--original-share', `${$('#compare').value}%`);
  $('#compare').setAttribute('aria-valuetext', `${$('#compare').value}% original image`);
  $('.comparison-label-original').hidden = Number($('#compare').value) < 12;
  $('#comparison-effect-label').hidden = Number($('#compare').value) > 85;
});
$('#strength').addEventListener('input', () => { $('#strength-value').textContent = `${Math.round(Number($('#strength').value) * 100)}%`; mount?.setUniforms(uniforms()); });
$('#speed').addEventListener('input', () => { $('#speed-value').textContent = `${Math.round(Number($('#speed').value) * 100)}%`; updatePlayback(); });
$('#scale').addEventListener('input', () => { $('#scale-value').textContent = `${Math.round(Number($('#scale').value) * 100)}%`; mount?.setUniforms(uniforms()); });
$('#pause-shader').addEventListener('click', () => { paused = !paused; updatePlayback(); });
$('#save-shader').addEventListener('click', () => {
  mount?.canvasElement.toBlob((blob) => {
    if (!blob) { $('#download-status').textContent = 'Could not save that frame. Please try again.'; return; }
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = `manim-studio-nature-${imageEffects[effect].file}.png`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    $('#download-status').textContent = 'Your PNG download has started.';
  }, 'image/png');
});
updatePlayback();
try {
  engine = await import('./assets/shader-engine.js');
  // The vanilla renderer expects texture images to have finished decoding.
  await Promise.all([engine.getShaderNoiseTexture().decode(), natureImage.decode()]);
  const probe = document.createElement('canvas'), gl = probe.getContext('webgl2');
  usable = !!gl; gl?.getExtension('WEBGL_lose_context')?.loseContext();
} catch { usable = false; }
showEffect();
window.addEventListener('pagehide', () => { mount?.dispose(); mount = undefined; });
window.addEventListener('pageshow', (event) => { if (event.persisted) showEffect(); });

const collections = {
  filters: [['nature-paper-texture', 'Paper Texture', 'paper'], ['nature-fluted-glass', 'Fluted Glass', 'glass'], ['nature-water', 'Water', 'water']],
  logos: [['heatmap', 'Heatmap', 'A flowing thermal glow'], ['liquid-metal', 'Liquid Metal', 'Your logo, cast in living chrome'], ['gem-smoke', 'Gem Smoke', 'Luminous color around your silhouette']],
  textures: [['grain-gradient', 'Grain Gradient', 'Color with a little character'], ['voronoi', 'Voronoi', 'Living cells and crystalline edges'], ['god-rays', 'God Rays', 'A little atmosphere. A lot of light.']],
};
document.querySelectorAll('[data-collection]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-collection]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  const isFilter = button.dataset.collection === 'filters';
  const cards = collections[button.dataset.collection].map(([id, title, target]) => {
    const card = document.createElement('a'), picture = document.createElement('div'), image = document.createElement('img'), caption = document.createElement('span'), arrow = document.createElement('b');
    card.className = 'template-card'; card.href = '#start';
    if (isFilter) { card.href = '#playground'; card.dataset.tryEffect = target; }
    image.src = `assets/shaders/${id}.webp`; image.alt = isFilter ? `The forest river transformed by ${title}` : `${title} shader preview`; image.width = 768; image.height = 432; image.loading = 'lazy';
    picture.append(image); caption.textContent = title; arrow.textContent = '↗'; arrow.setAttribute('aria-hidden', 'true'); caption.append(arrow); card.append(picture, caption); return card;
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
  ['Start with nature.', 'A forest, a river, a little morning light.', 'The original image'],
  ['Make it flow.', 'Scroll to turn a still image into living water.', 'Water / shaped by your scroll'],
  ['Keep the effect.', 'Same image. A completely new feeling.', 'Water / ready to take with you'],
];
let storyMount;
let scrollFrame = 0;
let currentChapter = -1;
function storyUniforms(progress) {
  return imageUniforms(engine, natureImage, 'water', Math.min(1, progress * 1.3), 1);
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
    story.style.setProperty('--scrub-mix', String(Math.min(1, progress * 3)));
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
    try { storyMount = new engine.ShaderMount($('#scrub-canvas'), engine.waterFragmentShader, storyUniforms(0), { preserveDrawingBuffer: true }, 0, 0, 1, 1_500_000, ['u_image']); }
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
