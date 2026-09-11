/* Inline SVG icon sprite. Injected into <body> on load so the mockups work
   straight from the filesystem (no fetch, no CORS). */
(function () {
  var P = {
    play:        '<path d="M7 4.5v15l13-7.5-13-7.5Z"/>',
    stop:        '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
    list:        '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    shield:      '<path d="M12 3.5 5 6.5v5.2c0 4.3 2.9 7.6 7 8.8 4.1-1.2 7-4.5 7-8.8V6.5l-7-3Z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    terminal:    '<path d="M5 6h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z"/><path d="m7.5 10 2 2-2 2M12.5 14h4"/>',
    settings:    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 2.6 15a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.5-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9.7 4a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 20.9 11a2 2 0 1 1 0 4Z"/>',
    sun:         '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon:        '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"/>',
    search:      '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    chevron:     '<path d="m6 9 6 6 6-6"/>',
    check:       '<path d="m5 12.5 4.5 4.5L19 7"/>',
    alert:       '<path d="M12 4.5 2.8 20h18.4L12 4.5Z"/><path d="M12 10v4.5M12 17.4h.01"/>',
    x:           '<path d="M6 6l12 12M18 6 6 18"/>',
    info:        '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
    folder:      '<path d="M3 7.5A2 2 0 0 1 5 5.5h3.6l1.8 2.2H19a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/>',
    link:        '<path d="M10 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1 1"/><path d="M14 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1-1"/>',
    file:        '<path d="M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5l-5-5Z"/><path d="M14 3.5v5h5"/>',
    download:    '<path d="M12 4v11M7.5 11l4.5 4.5 4.5-4.5"/><path d="M4.5 19.5h15"/>',
    upload:      '<path d="M12 20V9M7.5 13.5 12 9l4.5 4.5"/><path d="M4.5 4.5h15"/>',
    film:        '<rect x="3" y="4.5" width="18" height="15" rx="2"/><path d="M8 4.5v15M16 4.5v15M3 12h18M3 8.2h5M3 15.8h5M16 8.2h5M16 15.8h5"/>',
    globe:       '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.3 3.6 5.2 3.6 8.5s-1.2 6.2-3.6 8.5c-2.4-2.3-3.6-5.2-3.6-8.5S9.6 5.8 12 3.5Z"/>',
    cpu:         '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3.5v3M14 3.5v3M10 17.5v3M14 17.5v3M3.5 10h3M3.5 14h3M17.5 10h3M17.5 14h3"/>',
    layers:      '<path d="m12 3.5 8.5 4.5L12 12.5 3.5 8 12 3.5Z"/><path d="m4.5 12.5 7.5 4 7.5-4"/>',
    sparkle:     '<path d="M12 4v6M12 14v6M4 12h6M14 12h6M6.8 6.8l3 3M14.2 14.2l3 3M17.2 6.8l-3 3M9.8 14.2l-3 3"/>',
    clock:       '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    history:     '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 5v4h4"/><path d="M12 8v4.4l3 1.8"/>',
    wave:        '<path d="M4 12h2l1.6-4.5L10 16l2.2-9L14.5 12H20"/>',
    zap:         '<path d="M13.5 3 5.5 13.5h5L10 21l8-10.5h-5L13.5 3Z"/>',
    copy:        '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5v-2a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/>',
    external:    '<path d="M14 4.5h5.5V10"/><path d="M19.5 4.5 11 13"/><path d="M18 14v4.5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4.5"/>',
    plus:        '<path d="M12 5v14M5 12h14"/>',
    refresh:     '<path d="M20 11a8 8 0 0 0-13.7-5.2L3.5 8.5"/><path d="M4 13a8 8 0 0 0 13.7 5.2l2.8-2.7"/><path d="M3.5 4.5v4h4M20.5 19.5v-4h-4"/>',
    filter:      '<path d="M4 6h16l-6 7v5l-4 2v-7L4 6Z"/>',
    eye:         '<path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.6"/>',
    save:        '<path d="M5 5h11l3 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/><path d="M8 5v5h6V5M8 21v-6h8v6"/>',
    keyboard:    '<rect x="3" y="6.5" width="18" height="11" rx="2"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 13.5h9"/>',
    arrow:       '<path d="M5 12h13M13 7l5 5-5 5"/>',
    enter:       '<path d="M19 5v7a3 3 0 0 1-3 3H6"/><path d="m9.5 11.5-3.5 3.5 3.5 3.5"/>',
    more:        '<circle cx="6" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18" cy="12" r="1.3"/>',
    scissors:    '<circle cx="6.5" cy="6.5" r="2.5"/><circle cx="6.5" cy="17.5" r="2.5"/><path d="M8.7 8.3 20 18M8.7 15.7 20 6"/>',
    bookmark:    '<path d="M6.5 4.5h11v15l-5.5-3.6L6.5 19.5v-15Z"/>',
    gauges:      '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l3.5-5.5"/><circle cx="12" cy="18" r="1.4"/>',
    undo:        '<path d="M4 9.5h10.5a5 5 0 0 1 0 10H8"/><path d="M7.5 5.5 3.5 9.5l4 4"/>',
    split:       '<path d="M12 3.5v17"/><path d="M8 8 4.5 12 8 16M16 8l3.5 4-3.5 4"/>',
    tune:        '<path d="M4 7h10M18 7h2M4 12h4M12 12h8M4 17h12M20 17h0"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="17" r="2"/>'
  };

  var out = '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">';
  for (var k in P) {
    out += '<symbol id="i-' + k + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
           'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + P[k] + '</symbol>';
  }
  out += '</svg>';

  function inject() {
    var d = document.createElement('div');
    d.innerHTML = out;
    document.body.insertBefore(d.firstChild, document.body.firstChild);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
