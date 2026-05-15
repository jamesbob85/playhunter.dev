// Scout — Meta
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  document.getElementById('meta-weekly-piece').textContent = data.meta.weekly_piece_title || '—';

  renderClusters('meta-heating-list', data.meta.heating, 'up');
  renderClusters('meta-cooling-list', data.meta.cooling, 'down');

  if (!data.meta.cooling.length) {
    document.getElementById('meta-cooling-list').innerHTML = `<p class="paragraph" style="color: var(--fg-3); font-style: italic;">Nothing cooling this week. Every tracked cluster is flat or positive.</p>`;
  }

  function renderClusters(rootId, clusters, dir) {
    const root = document.getElementById(rootId);
    if (!clusters.length) return;
    root.innerHTML = clusters.map(c => {
      const sign = c.delta_pct >= 0 ? '+' : '';
      return `
        <article class="cluster-card">
          <div class="cluster-card-head">
            <h3 class="cluster-card-title">${escapeHtml(c.name)}</h3>
            <span class="cluster-card-velocity ${dir}">${sign}${c.delta_pct.toFixed(1)}%</span>
          </div>
          <div class="cluster-meta">${c.count} ${c.count === 1 ? 'tracked title' : 'tracked titles'}</div>
          <div class="cluster-members">
            ${(c.titles || []).map(t => `
              <a class="cluster-member" href="./game.html?id=${t.id}">
                <span>${escapeHtml(t.name)}</span>
                <span class="cm-score">${t.score} <span class="delta ${t.delta >= 0 ? 'up' : 'down'}">${signed(t.delta)}</span></span>
              </a>
            `).join('')}
          </div>
        </article>
      `;
    }).join('');
  }
})();

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function signed(n) { return (n > 0 ? '+' : (n < 0 ? '−' : '')) + Math.abs(n); }
