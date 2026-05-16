// Scout — Universe as an image-led tile grid.
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  const all = Object.values(data.games);
  const filters = { stage: '', scale: '', sort: 'score' };

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

  function sortKey(g, key) {
    const rs = g.real_signals || {};
    if (key === 'score') return g.score;
    if (key === 'delta') return g.score_delta;
    if (key === 'wishlists') return rs.wishlists || 0;
    if (key === 'hypes') return rs.igdb_hypes || 0;
    if (key === 'revenue') return rs.revenue || 0;
    return g.score;
  }

  function render() {
    let list = all.slice();
    if (filters.stage) list = list.filter(g => g.stage_label === filters.stage);
    if (filters.scale) list = list.filter(g => g.scale === filters.scale);
    list.sort((a, b) => sortKey(b, filters.sort) - sortKey(a, filters.sort));

    document.getElementById('uni-count').textContent = `${list.length} of ${all.length}`;
    const root = document.getElementById('uni-grid');
    root.innerHTML = list.map(g => {
      const t = g.thesis || {};
      const rs = g.real_signals || {};
      const up = g.score_delta >= 0;
      // pick a key metric to show on tile
      let metric = '';
      if (g.stage === 'Announced' && rs.wishlists) metric = `${fmtNum(rs.wishlists)} wishlists`;
      else if (rs.igdb_hypes && g.stage === 'Announced') metric = `${rs.igdb_hypes} hypes`;
      else if (rs.revenue) metric = `${fmtRev(rs.revenue)} revenue`;
      else if (rs.followers) metric = `${fmtNum(rs.followers)} followers`;
      else if (rs.igdb_hypes) metric = `${rs.igdb_hypes} hypes`;

      return `
        <a class="utile" href="./game.html?id=${g.id}">
          <div class="utile-img" style="background-image: url(${g.header_image || ''})">
            <div class="utile-overlay">
              <div class="utile-score-row">
                <span class="utile-score">${g.score}</span>
                <span class="utile-delta delta ${up ? 'up' : 'down'}">${signed(g.score_delta)}</span>
              </div>
              <div class="utile-pills">
                <span class="scale-pill" data-scale="${g.scale}">${g.scale}</span>
                <span class="stage-pill" data-stage="${g.stage_label}">${g.stage_label}</span>
              </div>
            </div>
          </div>
          <div class="utile-body">
            <div class="utile-name">${escapeHtml(g.name)}</div>
            ${g.studio ? `<div class="utile-studio">${escapeHtml(g.studio)}</div>` : ''}
            ${metric ? `<div class="utile-metric">${metric}</div>` : ''}
            ${t.pull_quote ? `<p class="utile-quote">"${escapeHtml(t.pull_quote.slice(0, 110))}${t.pull_quote.length > 110 ? '…' : ''}"</p>` : ''}
          </div>
        </a>
      `;
    }).join('');
  }

  function fmtNum(v) {
    if (!v) return '0';
    if (v >= 1e6) return `${(v/1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v/1e3).toFixed(0)}K`;
    return `${v}`;
  }
  function fmtRev(v) {
    if (!v) return '$0';
    if (v >= 1e9) return `$${(v/1e9).toFixed(1)}B`;
    if (v >= 1e6) return `$${(v/1e6).toFixed(0)}M`;
    if (v >= 1e3) return `$${(v/1e3).toFixed(0)}K`;
    return `$${v}`;
  }
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  }
  function signed(n) { return (n > 0 ? '+' : (n < 0 ? '−' : '')) + Math.abs(n); }

  render();
})();
