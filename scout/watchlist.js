// Scout — Watchlist
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  const games = Object.values(data.games);

  const breaking = games.filter(g =>
    !g.is_mature_phenom
    && g.confidence === 'High'
    && g.scale !== 'Watch'
    && g.score >= 55
  ).sort((a, b) => b.score - a.score);

  const wild = games.filter(g =>
    !g.is_mature_phenom
    && !breaking.includes(g)
    && (g.score_delta >= 12 || g.confidence === 'Medium')
    && g.score >= 30
  ).sort((a, b) => b.score_delta - a.score_delta);

  const mature = games.filter(g => g.is_mature_phenom)
    .sort((a, b) => (b.real_signals?.revenue || 0) - (a.real_signals?.revenue || 0));

  renderTier('grid-breaking', breaking, 'count-breaking');
  renderTier('grid-wild', wild, 'count-wild');
  renderTier('grid-mature', mature, 'count-mature');

  function renderTier(gridId, list, countId) {
    document.getElementById(countId).textContent = `${list.length} ${list.length === 1 ? 'title' : 'titles'}`;
    const grid = document.getElementById(gridId);
    if (!list.length) {
      grid.innerHTML = `<div class="pick-empty" style="grid-column: 1 / -1;">No titles in this tier this period.</div>`;
      return;
    }
    grid.innerHTML = list.map(g => {
      const t = g.thesis || {};
      const up = g.score_delta >= 0;
      const rs = g.real_signals || {};
      const stats = [];
      if (rs.followers) stats.push({ k: 'Followers', v: fmtNum(rs.followers) });
      if (rs.revenue) stats.push({ k: 'Revenue', v: fmtRev(rs.revenue) });
      if (rs.twitch_viewers) stats.push({ k: 'Twitch live', v: fmtNum(rs.twitch_viewers) });
      if (rs.igdb_hypes) stats.push({ k: 'Hypes', v: rs.igdb_hypes });
      return `
        <a class="wcard" href="./game.html?id=${g.id}">
          <div class="wcard-img" style="background-image: url(${g.header_image || ''})"></div>
          <div class="wcard-body">
            <div class="wcard-headline">
              <span class="wcard-name">${escapeHtml(g.name)}</span>
              <span class="wcard-tags">
                <span class="score"><span class="num">${g.score}</span><span class="delta-inline delta ${up ? 'up' : 'down'}">${signed(g.score_delta)}</span></span>
                <span class="scale-pill" data-scale="${g.scale}">${g.scale}</span>
                <span class="stage-pill" data-stage="${g.stage_label}">${g.stage_label}</span>
                <span class="conf-pill" data-conf="${g.confidence}">${g.confidence}</span>
              </span>
            </div>
            ${t.pull_quote ? `<p class="wcard-quote">"${escapeHtml(t.pull_quote)}"</p>` : ''}
            ${stats.length ? `
              <div class="wcard-bar">
                ${stats.slice(0, 4).map(s => `<span class="stat-pair"><span class="k">${s.k}</span><span class="v">${s.v}</span></span>`).join('')}
              </div>` : ''}
          </div>
        </a>
      `;
    }).join('');
  }
})();

function fmtRev(v) {
  if (!v) return '';
  return v >= 1e9 ? `$${(v/1e9).toFixed(2)}B` : v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : `$${(v/1e3).toFixed(0)}K`;
}
function fmtNum(v) {
  if (!v) return '';
  return v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : `${v}`;
}
function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function signed(n) { return (n > 0 ? '+' : (n < 0 ? '−' : '')) + Math.abs(n); }
