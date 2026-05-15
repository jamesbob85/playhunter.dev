// Scout — Daily Brief renderer
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  window._scoutData = data;

  // Dateline
  const dt = new Date(data.generated_at);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const pad = n => String(n).padStart(2, '0');
  document.getElementById('dateline').textContent =
    `${days[dt.getUTCDay()]} ${dt.getUTCDate()} ${months[dt.getUTCMonth()]} ${dt.getUTCFullYear()} · refreshed ${pad(dt.getUTCHours())}:${pad(dt.getUTCMinutes())} UTC`;

  // The Read — cadence-aware
  renderTheRead('daily');

  // Movers
  renderMovers(data.movers);

  document.getElementById('universe-count').textContent = data.universe_count;

  // Picks
  renderPicks('#pick-conviction .pick-list', data.high_conviction);
  renderPicks('#pick-wild .pick-list', data.wild_bets);

  // Meta heating/cooling with titles
  renderClusters('#meta-heating', data.meta.heating, 'up');
  renderClusters('#meta-cooling', data.meta.cooling, 'down');

  if (!data.meta.cooling.length) {
    document.getElementById('meta-cooling').innerHTML =
      `<li class="cluster-empty">Nothing cooling this week.</li>`;
  }
  document.querySelector('#weekly-piece .weekly-title').textContent = data.meta.weekly_piece_title;

  // Cadence toggle
  document.querySelectorAll('.cad').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.cad').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const w = btn.dataset.cad;
      document.getElementById('movers-window').textContent = (
        w === 'daily' ? '· last 24h' :
        w === 'weekly' ? '· last 7d' :
        '· last 30d'
      );
      renderTheRead(w);
    });
  });
})();

function renderTheRead(cadence) {
  const data = window._scoutData;
  const readMap = data.the_read_by_cadence || {};
  const text = readMap[cadence] || data.the_read;
  const el = document.getElementById('the-read');
  el.style.opacity = '0';
  setTimeout(() => {
    el.textContent = text;
    el.style.opacity = '1';
  }, 80);
}

function renderMovers(movers) {
  const body = document.querySelector('#movers-table tbody');
  body.innerHTML = movers.map(m => {
    const up = m.delta >= 0;
    return `
      <tr data-id="${m.id}">
        <td class="col-delta"><span class="delta ${up ? 'up' : 'down'}">${up ? '▲' : '▼'}${Math.abs(m.delta)}</span></td>
        <td class="col-name"><span class="name-text">${escapeHtml(m.name)}</span></td>
        <td class="col-score"><span class="score"><span class="num">${m.score}</span><span class="delta-inline delta ${up ? 'up' : 'down'}">${signed(m.delta)}</span></span></td>
        <td class="col-scale"><span class="scale-pill" data-scale="${m.scale}">${m.scale}</span></td>
        <td class="col-stage"><span class="stage-pill" data-stage="${m.stage}">${m.stage}</span></td>
        <td class="col-conf"><span class="conf-pill" data-conf="${m.confidence}">${m.confidence}</span></td>
        <td class="col-arrow">→</td>
      </tr>
    `;
  }).join('');
  body.addEventListener('click', e => {
    const tr = e.target.closest('tr');
    if (tr?.dataset.id) location.href = `./game.html?id=${tr.dataset.id}`;
  });
}

function renderPicks(selector, picks) {
  const root = document.querySelector(selector);
  if (!picks.length) {
    root.innerHTML = `<div class="pick-empty">No picks meet the threshold in this cadence.</div>`;
    return;
  }
  root.innerHTML = picks.map(p => {
    const up = p.delta >= 0;
    return `
      <a class="pick" href="./game.html?id=${p.id}">
        <div class="pick-img" style="background-image: url(${p.header_image || ''})"></div>
        <div class="pick-body">
          <div class="pick-headline">
            <span class="pick-name">${escapeHtml(p.name)}</span>
            <span class="pick-tags">
              <span class="score"><span class="num">${p.score}</span><span class="delta-inline delta ${up ? 'up' : 'down'}">${signed(p.delta)}</span></span>
              <span class="scale-pill" data-scale="${p.scale}">${p.scale}</span>
              <span class="stage-pill" data-stage="${p.stage}">${p.stage}</span>
            </span>
          </div>
          <p class="pick-quote">"${escapeHtml(p.pull_quote || '')}"</p>
        </div>
      </a>
    `;
  }).join('');
}

function renderClusters(selector, clusters, dir) {
  const root = document.querySelector(selector);
  if (!clusters.length) {
    root.innerHTML = '';
    return;
  }
  root.innerHTML = clusters.map(c => {
    const sign = c.delta_pct >= 0 ? '+' : '';
    return `
      <li class="cluster-row">
        <div class="cluster-headline">
          <span class="cluster-name">${escapeHtml(c.name)}</span>
          <span class="cluster-delta ${dir === 'up' ? 'up' : 'down'}">${sign}${c.delta_pct.toFixed(1)}%</span>
        </div>
        ${c.titles && c.titles.length ? `
          <div class="cluster-titles">
            ${c.titles.map(t => `
              <a class="ctitle" href="./game.html?id=${t.id}" title="${escapeHtml(t.name)} · score ${t.score} ${signed(t.delta)}">
                <span class="ct-name">${escapeHtml(t.name)}</span>
                <span class="ct-delta delta ${t.delta >= 0 ? 'up' : 'down'}">${signed(t.delta)}</span>
              </a>
            `).join('')}
          </div>` : ''}
      </li>
    `;
  }).join('');
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function signed(n) {
  return (n > 0 ? '+' : (n < 0 ? '−' : '')) + Math.abs(n);
}
