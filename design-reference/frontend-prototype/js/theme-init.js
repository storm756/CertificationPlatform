/* Runs before first paint (not deferred) so night mode never flashes. */
(function () {
  var t = null;
  try { t = JSON.parse(localStorage.getItem('csfr.theme')); } catch (e) { /* ignore */ }
  var d = document.documentElement;
  d.dataset.theme = t || (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  d.classList.add('js');
})();
