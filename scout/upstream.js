// Scout — Upstream
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  const u = data.upstream || {};

  document.getElementById('up-roblox-list').innerHTML = (u.roblox || []).map(e => `
    <article class="up-row">
      <div class="up-row-head">
        <a class="up-row-name" href="${e.url || '#'}" target="_blank" rel="noopener">${escapeHtml(e.name || '')}</a>
        <span class="source-pill" data-source="roblox">Roblox</span>
      </div>
      <div class="up-row-signal">${escapeHtml(e.signal_label || '')}${e.min_age ? ` · age ${e.min_age}+` : ''}</div>
      <p class="up-row-why">${escapeHtml(e.why || '')}</p>
    </article>
  `).join('');

  document.getElementById('up-itch-list').innerHTML = (u.itch || []).map(e => `
    <article class="up-row">
      <div class="up-row-head">
        <a class="up-row-name" href="${e.url || '#'}" target="_blank" rel="noopener">${escapeHtml(e.name || '')} <span class="up-byline">by ${escapeHtml(e.author || '')}</span></a>
        <span class="source-pill" data-source="itch">itch.io</span>
      </div>
      <div class="up-row-signal">${escapeHtml(e.signal_label || '')}</div>
      ${e.desc ? `<p class="up-row-desc">${escapeHtml(e.desc)}</p>` : ''}
      <p class="up-row-why">${escapeHtml(e.why || '')}</p>
    </article>
  `).join('');
})();

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
