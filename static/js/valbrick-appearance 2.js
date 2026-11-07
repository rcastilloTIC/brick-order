/* Preference stays in this browser; no server/database migration. */
(function () {
  'use strict';
  var KEY = 'valbrick.appearance.v1';
  function valid(v) { return v === 'light' || v === 'dark' || v === 'auto'; }
  function stored() { try { var v = localStorage.getItem(KEY); return valid(v) ? v : 'auto'; } catch (_) { return 'auto'; } }
  function effective(pref) { return pref === 'auto' ? ((window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark') : pref; }
  function apply(pref) {
    document.documentElement.setAttribute('data-vb-theme', effective(pref));
    document.documentElement.setAttribute('data-bs-theme', effective(pref));
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', effective(pref) === 'light' ? '#ffffff' : '#111825');
    var select = document.getElementById('vb-appearance-select');
    if (select) select.value = pref;
  }
  var pref = stored();
  apply(pref);
  document.addEventListener('DOMContentLoaded', function () {
    apply(pref);
    var select = document.getElementById('vb-appearance-select');
    if (select) select.addEventListener('change', function () {
      if (!valid(select.value)) return;
      pref = select.value;
      try { localStorage.setItem(KEY, pref); } catch (_) {}
      apply(pref);
    });
  });
  if (window.matchMedia) {
    var media = window.matchMedia('(prefers-color-scheme: light)');
    var update = function () { if (pref === 'auto') apply(pref); };
    if (media.addEventListener) media.addEventListener('change', update);
    else if (media.addListener) media.addListener(update);
  }
})();
