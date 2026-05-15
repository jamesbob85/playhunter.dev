// Scout — Universe
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  const all = Object.values(data.games);
  const filters = { stage: '', scale: '' };
  let sortKey = 'score';
  let sortDir = 'desc';

  document.querySelectorAll('.filter-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.filter;
      const v = btn.dataset.value;
      filters[k] = v;
      document.querySelectorAll(`.filter-chip[data-filter="${k}"]`).forEach(c => c.classList.toggle('active', c.dataset.value === v));
      render();
    });
  });

  document.querySelectorAll('.uni-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.sort;
      if (sortKey === k) {
        sortDir = sortDir === 'desc' ? 'asc' : 'desc';
      } else {
        sortKey = k;
        sortDir = (k === 'name' || k === 'stage' || k === 'scale' || k === 'confidence') ? 'asc' : 'desc';
      }
      document.querySelectorAll('.uni-table th').forEach(t => {
        t.classList.toggle('active-sort', t.dataset.sort === k);
        t.classList.toggle('asc', t.dataset.sort === k && sortDir === 'asc');
      });
      render();
    });
  });

  function render() {
    let list = all.slice();
    if (filters.stage) list = list.filter(g => g.stage_label === filters.stage);
    if (filters.scale) list = list.filter(g => g.scale === filters.scale);

    const scaleOrder = { 'Phenom': 5, 'Hit': 4, 'Cult': 3, 'Watch': 2, 'Settled': 1 };
    const stageOrder = { 'Announced': 1, 'Demo': 2, 'Wishlist': 3, 'Early Access': 4, 'Launched': 5 };
    const confOrder = { 'High': 3, 'Medium': 2, 'Low': 1 };

    const keyOf = g => {
      if (sortKey === 'score') return g.score;
      if (sortKey === 'delta') return g.score_delta;
      if (sortKey === 'name') return (g.name || '').toLowerCase();
      if (sortKey === 'scale') return scaleOrder[g.scale] || 0;
      if (sortKey === 'stage') return stageOrder[g.stage_label] || 0;
      if (sortKey === 'confidence') return confOrder[g.confidence] || 0;
      return 0;
    };
    list.sort((a, b) => {
      const va = keyOf(a), vb = keyOf(b);
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    document.getElementById('uni-count').textContent = `${list.length} of ${all.length}`;
    const tbody = document.querySelector('#uni-table tbody');
    tbody.innerHTML = list.map(g => {
      const up = g.score_delta >= 0;
      const tags = (g.tags || []).slice(0, 3).join(' · ');
      return `
        <tr data-id="${g.id}">
          <td><span class="score"><span class="num">${g.score}</span></span></td>
          <td><span class="delta ${up ? 'up' : 'down'}">${signed(g.score_delta)}</span></td>
          <td>
            <div class="uni-name">${escapeHtml(g.name)}</div>
            ${g.studio ? `<div class="uni-studio">${escapeHtml(g.studio)}</div>` : ''}
          </td>
          <td><span class="scale-pill" data-scale="${g.scale}">${g.scale}</span></td>
          <td><span class="stage-pill" data-stage="${g.stage_label}">${g.stage_label}</span></td>
          <td><span class="conf-pill" data-conf="${g.confidence}">${g.confidence}</span></td>
          <td><span class="uni-genre-mini">${escapeHtml((g.meta_clusters || [])[0] || '—')}</span></td>
          <td><span class="uni-genre-mini">${escapeHtml(tags || '—')}</span></td>
        </tr>
      `;
    }).join('');
    tbody.addEventListener('click', e => {
      const tr = e.target.closest('tr');
      if (tr?.dataset.id) location.href = `./game.html?id=${tr.dataset.id}`;
    }, { once: true });
  }

  render();
})();

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function signed(n) { return (n > 0 ? '+' : (n < 0 ? '−' : '')) + Math.abs(n); }
