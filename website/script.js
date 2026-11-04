// Shared interactions. Page navigation also works without JavaScript.
document.documentElement.classList.add('js');
const $ = (selector) => document.querySelector(selector);
const menu = $('.menu-toggle');
const closeMenu = () => menu?.setAttribute('aria-expanded', 'false');
menu?.addEventListener('click', () => menu.setAttribute('aria-expanded', String(menu.getAttribute('aria-expanded') !== 'true')));
document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') { closeMenu(); menu.focus(); } });
$('#main-navigation')?.addEventListener('click', closeMenu);
function filterGallery(buttonSelector, itemSelector, key, allLabel) {
  document.querySelectorAll(buttonSelector).forEach((button) => button.addEventListener('click', () => {
    document.querySelectorAll(buttonSelector).forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    const value = button.dataset[key];
    document.querySelectorAll(itemSelector).forEach((item) => { item.hidden = value !== allLabel && item.dataset[key.replace('Category', 'Family')] !== value; });
  }));
}
filterGallery('[data-template-category]', '[data-template-family]', 'templateCategory', 'All designs');
filterGallery('[data-filter-category]', '[data-filter-family]', 'filterCategory', 'All image filters');
document.querySelectorAll('[data-platform]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-platform]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  const unix = button.dataset.platform === 'unix';
  $('#setup-commands').textContent = `git clone https://github.com/birol-dev/Manim-Fullstack.git\ncd Manim-Fullstack\n${unix ? 'python3' : 'python'} run.py`;
  $('#platform-note').textContent = unix ? 'Install Cairo and Pango first; the full setup guide below has the commands for your OS.' : 'The launcher prepares the app and opens it in your browser.';
}));
$('#copy-commands')?.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#setup-commands').textContent); $('#copy-status').textContent = 'Setup commands copied.'; $('#copy-commands').textContent = 'Copied ✓'; }
  catch { $('#copy-status').textContent = 'Select the commands above and copy them manually.'; $('#copy-commands').textContent = 'Select to copy'; }
  setTimeout(() => { $('#copy-commands').textContent = 'Copy ⧉'; }, 2500);
});
if ($('#shader-canvas')) import('./playground.js?v=20261104');
