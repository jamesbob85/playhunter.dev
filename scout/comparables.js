// Scout — Comparables library
(async () => {
  const data = await fetch('./data/comparables.json').then(r => r.json());
  const all = data.comparables || [];
  const filters = { outcome: '', cluster: '' };

  document.querySelectorAll('.filter-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.filter;
      const v = btn.dataset.value;
      filters[k] = v;
      document.querySelectorAll(`.filter-chip[data-filter="${k}"]`).forEach(c =>
        c.classList.toggle('active', c.dataset.value === v));
      render();
    });
  });

  function render() {
    let list = all.slice();
    if (filters.outcome) list = list.filter(c => c.outcome === filters.outcome);
    if (filters.cluster) list = list.filter(c =>
      c.primary_cluster === filters.cluster || (c.secondary_clusters || []).includes(filters.cluster));

    document.getElementById('comp-count').textContent = `${list.length} of ${all.length}`;
    document.getElementById('comp-grid').innerHTML = list.map(c => {
      const peakStr = c.peak_ccu ? `${(c.peak_ccu/1000).toFixed(0)}K peak CCU` : '—';
      const revStr = c.lifetime_revenue_usd
        ? (c.lifetime_revenue_usd >= 1e9
            ? `$${(c.lifetime_revenue_usd/1e9).toFixed(2)}B`
            : `$${(c.lifetime_revenue_usd/1e6).toFixed(0)}M`)
        : '—';
      return `
        <article class="comp-card" data-outcome="${c.outcome}">
          <header class="comp-card-head">
            <h3 class="comp-name">${escapeHtml(c.name)}</h3>
            <span class="comp-year">${c.year}</span>
          </header>
          <div class="comp-stats">
            <span class="comp-stat"><span class="cs-k">Peak</span><span class="cs-v">${peakStr}</span></span>
            <span class="comp-stat"><span class="cs-k">Lifetime rev</span><span class="cs-v">${revStr}</span></span>
            <span class="comp-stat"><span class="cs-k">Team</span><span class="cs-v">${c.team_size || '—'}</span></span>
            <span class="comp-stat"><span class="cs-k">Outcome</span><span class="cs-v outcome-tag" data-outcome="${c.outcome}">${c.outcome}</span></span>
          </div>
          <div class="comp-arc">${escapeHtml(c.stage_arc)}</div>
          <div class="comp-clusters">
            ${[c.primary_cluster, ...(c.secondary_clusters || [])].filter(Boolean).map(cl =>
              `<span class="meta-tag">${escapeHtml(cl)}</span>`).join('')}
          </div>
          <p class="comp-narrative">${escapeHtml(c.narrative)}</p>
          <div class="comp-lesson">
            <span class="comp-lesson-label">Key lesson</span>
            <p>${escapeHtml(c.key_lesson)}</p>
          </div>
          ${(c.signal_signature || []).length ? `
            <div class="comp-signature">
              <span class="comp-signature-label">Signal signature</span>
              <ul>${c.signal_signature.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
            </div>` : ''}
          <div class="comp-tags">
            ${(c.tags || []).map(t => `<span class="comp-tag">${escapeHtml(t)}</span>`).join('')}
          </div>
        </article>
      `;
    }).join('');
  }

  render();
})();

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
