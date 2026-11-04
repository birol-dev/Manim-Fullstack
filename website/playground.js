import { imageEffects, imageUniforms, natureSource } from './image-effects.js?v=20261104';
const $ = (selector) => document.querySelector(selector);
const natureImage = new Image();
natureImage.src = natureSource;
const requested = new URLSearchParams(location.search).get('effect');
let effect = Object.hasOwn(imageEffects, requested) ? requested : 'glass';
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let paused = motionPreference.matches;
let mount;
let engine;
let usable = false;
let active = true;
function playback() {
  const moving = usable && effect === 'water';
  mount?.setSpeed(paused || document.hidden || !active || !moving ? 0 : Number($('#speed').value));
  $('#pause-shader').textContent = paused ? '▶' : 'Ⅱ';
  $('#pause-shader').setAttribute('aria-label', paused ? 'Play preview' : 'Pause preview');
  $('#pause-shader').disabled = !moving;
  $('#speed').disabled = !moving;
  $('#preview-status').textContent = !usable ? 'Rendered example' : moving && !paused && Number($('#speed').value) > 0 ? 'Live preview' : 'Live image filter';
}
const uniforms = () => imageUniforms(engine, natureImage, effect, Number($('#strength').value), Number($('#scale').value));
function showEffect() {
  mount?.dispose(); mount = undefined;
  const host = $('#shader-canvas');
  host.querySelectorAll('canvas').forEach((canvas) => canvas.remove());
  const selected = imageEffects[effect];
  host.style.backgroundImage = `url('assets/shaders/nature-${selected.file}.webp')`;
  host.setAttribute('aria-label', `The forest river transformed by ${selected.name}`);
  $('#comparison-effect-label').textContent = selected.name;
  $('#effect-caption').textContent = `${String(Object.keys(imageEffects).indexOf(effect) + 1).padStart(2, '0')} / ${selected.name}`;
  document.querySelectorAll('[data-effect]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.effect === effect)));
  if (usable) {
    try { mount = new engine.ShaderMount(host, engine[selected.shader], uniforms(), {preserveDrawingBuffer: true}, 0, 1400, 1, 1_500_000, ['u_image']); }
    catch { usable = false; host.querySelector('canvas')?.remove(); }
  }
  $('#shader-fallback').hidden = usable;
  ['save-shader', 'strength', 'scale'].forEach((id) => { $(`#${id}`).disabled = !usable; });
  playback();
}
document.querySelectorAll('[data-effect]').forEach((button) => button.addEventListener('click', () => { effect = button.dataset.effect; showEffect(); }));
$('#compare').addEventListener('input', () => {
  const value = Number($('#compare').value);
  $('#image-comparison').style.setProperty('--original-share', `${value}%`);
  $('#compare').setAttribute('aria-valuetext', `${value}% original image`);
  $('.comparison-label-original').hidden = value < 12;
  $('#comparison-effect-label').hidden = value > 85;
});
for (const id of ['strength', 'scale']) $(`#${id}`).addEventListener('input', () => {
  $(`#${id}-value`).textContent = `${Math.round(Number($(`#${id}`).value) * 100)}%`;
  mount?.setUniforms(uniforms());
});
$('#speed').addEventListener('input', () => { $('#speed-value').textContent = `${Math.round(Number($('#speed').value) * 100)}%`; playback(); });
$('#pause-shader').addEventListener('click', () => { paused = !paused; playback(); });
$('#reset-filter').addEventListener('click', () => {
  for (const [id, value] of [['strength', '0.65'], ['scale', '1'], ['speed', '0.5'], ['compare', '35']]) { $(`#${id}`).value = value; $(`#${id}`).dispatchEvent(new Event('input')); }
  paused = motionPreference.matches; playback();
});
$('#save-shader').addEventListener('click', () => {
  try {
    mount?.canvasElement.toBlob((blob) => {
      if (!blob) { $('#download-status').textContent = 'Could not save that frame. Please try again.'; return; }
      const download = URL.createObjectURL(blob), anchor = document.createElement('a');
      anchor.href = download; anchor.download = `manim-studio-nature-${imageEffects[effect].file}.png`;
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(download), 60_000);
      $('#download-status').textContent = 'Your PNG download has started.';
    }, 'image/png');
  } catch { $('#download-status').textContent = 'Could not save this image. Please try again.'; }
});
motionPreference.addEventListener('change', () => { paused = motionPreference.matches; playback(); });
document.addEventListener('visibilitychange', playback);
const observer = new IntersectionObserver(([entry]) => { active = entry.isIntersecting; playback(); });
observer.observe($('#playground'));
window.addEventListener('pagehide', () => { mount?.dispose(); mount = undefined; observer.disconnect(); });
window.addEventListener('pageshow', (event) => { if (event.persisted) { observer.observe($('#playground')); showEffect(); } });
try {
  engine = await import('./assets/shader-engine.js?v=20261104');
  await Promise.all([engine.getShaderNoiseTexture().decode(), natureImage.decode()]);
  const probe = document.createElement('canvas'), gl = probe.getContext('webgl2');
  usable = !!gl; gl?.getExtension('WEBGL_lose_context')?.loseContext();
} catch { usable = false; }
showEffect();
