/* Mockup chrome: theme toggle, rail navigation, and small demo interactions.
   Pure presentation — no application logic. */
(function () {
  // ---- theme -------------------------------------------------------------
  var KEY = 'ta-mock-theme';
  try {
    if (localStorage.getItem(KEY) === 'light') document.body.classList.add('light');
  } catch (e) { /* file:// may block storage */ }

  function syncThemeIcons() {
    var light = document.body.classList.contains('light');
    document.querySelectorAll('[data-theme-icon]').forEach(function (el) {
      el.innerHTML = '<svg class="ico"><use href="#i-' + (light ? 'moon' : 'sun') + '"/></svg>';
    });
    document.querySelectorAll('[data-theme-label]').forEach(function (el) {
      el.textContent = light ? 'Light' : 'Dark';
    });
  }

  function toggleTheme() {
    document.body.classList.toggle('light');
    try {
      localStorage.setItem(KEY, document.body.classList.contains('light') ? 'light' : 'dark');
    } catch (e) { /* ignore */ }
    syncThemeIcons();
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-action]');
    if (!t) return;
    var a = t.getAttribute('data-action');
    if (a === 'theme') toggleTheme();
    if (a === 'seg') {
      var group = t.parentElement;
      group.querySelectorAll('button').forEach(function (b) { b.classList.remove('on'); });
      t.classList.add('on');
    }
    if (a === 'chip') {
      var bar = t.parentElement;
      bar.querySelectorAll('.filter-chip').forEach(function (b) { b.classList.remove('on'); });
      t.classList.add('on');
    }
    if (a === 'switch') t.classList.toggle('on');
    if (a === 'selectrow') {
      var tb = t.closest('tbody');
      if (tb) tb.querySelectorAll('tr').forEach(function (r) { r.classList.remove('sel'); });
      t.classList.add('sel');
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    syncThemeIcons();
    // Keyboard shortcut hint parity with the real app: Ctrl+K opens palette.
    document.addEventListener('keydown', function (e) {
      var ov = document.querySelector('.overlay');
      if (!ov) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        ov.style.display = ov.style.display === 'none' ? 'flex' : 'none';
      }
      if (e.key === 'Escape') ov.style.display = 'none';
    });
  });
})();
