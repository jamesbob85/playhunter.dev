// Scout — Explore: visual bubble map of the candidate universe.
(async () => {
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  const all = Object.values(data.games);

  const filters = { scale: '', stage: '', size: 'wishlists' };

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

  function getSize(g, key) {
    const rs = g.real_signals || {};
    if (key === 'wishlists') return rs.wishlists || 0;
    if (key === 'followers') return rs.followers || 0;
    if (key === 'hypes') return rs.igdb_hypes || 0;
    if (key === 'revenue') return rs.revenue || 0;
    return 0;
  }

  // X axis: lifecycle stage. Map each stage to a 0..1 position.
  // pre-launch (Announced) = 0.1; Demo/Wishlist = 0.25; Early Access = 0.5; just-launched = 0.7; Launched = 0.9
  function xPos(g) {
    const lc = g.lifecycle_class;
    const stage = g.stage_label;
    if (lc === 'pre-launch' || stage === 'Announced') return 0.10;
    if (stage === 'Demo' || stage === 'Wishlist') return 0.25;
    if (stage === 'Early Access') return 0.50;
    if (lc === 'just-launched') return 0.72;
    return 0.90;
  }

  function colorForScale(scale) {
    return {
      'Phenom': '#ff6a45',
      'Hit': '#f4b740',
      'Cult': '#4ed3b6',
      'Watch': '#6e6e7c',
      'Settled': '#3a3a48',
    }[scale] || '#6e6e7c';
  }

  function render() {
    let list = all.slice();
    if (filters.scale) list = list.filter(g => g.scale === filters.scale);
    if (filters.stage) list = list.filter(g => g.stage_label === filters.stage);
    // exclude broken-out unless explicitly requested
    list = list.filter(g => !g.is_broken_out || filters.scale === 'Settled');

    // SVG dimensions
    const W = 900, H = 520, padL = 60, padR = 30, padT = 24, padB = 60;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;

    // Compute size-scale (log-ish)
    const sizeVals = list.map(g => getSize(g, filters.size));
    const sMax = Math.max(1, ...sizeVals);
    const sMin = 0;
    const radiusOf = v => {
      if (!v || v <= 0) return 5;
      // log-scale radius 5..30
      const norm = Math.log10(1 + v) / Math.log10(1 + sMax);
      return 5 + norm * 25;
    };

    // Sort by size desc so big bubbles render first (small bubbles overlay on top)
    list.sort((a, b) => getSize(b, filters.size) - getSize(a, filters.size));

    const xOf = g => padL + xPos(g) * innerW + jitterFor(g.id, 0.06) * innerW;
    const yOf = g => padT + (1 - (g.score / 100)) * innerH;

    // Y-axis tick lines at 0/25/50/75/100
    const yTicks = [0, 25, 50, 75, 100].map(t => {
      const y = padT + (1 - t / 100) * innerH;
      return `
        <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--line)" stroke-width="0.5" stroke-dasharray="2 4"/>
        <text x="${padL - 8}" y="${y + 3}" text-anchor="end" class="ax-tick">${t}</text>
      `;
    }).join('');

    // X-axis stage labels
    const xTicks = [
      {p: 0.10, l: 'Announced'},
      {p: 0.25, l: 'Demo'},
      {p: 0.50, l: 'Early Access'},
      {p: 0.72, l: 'Just-launched'},
      {p: 0.90, l: 'Launched'},
    ].map(t => {
      const x = padL + t.p * innerW;
      return `
        <line x1="${x}" y1="${padT}" x2="${x}" y2="${H - padB}" stroke="var(--line)" stroke-width="0.5" stroke-dasharray="2 4"/>
        <text x="${x}" y="${H - padB + 18}" text-anchor="middle" class="ax-tick">${t.l}</text>
      `;
    }).join('');

    // Bubbles
    const circles = list.map(g => {
      const r = radiusOf(getSize(g, filters.size));
      const cx = xOf(g);
      const cy = yOf(g);
      const fill = colorForScale(g.scale);
      const stroke = g.confidence === 'High' ? fill : (g.confidence === 'Medium' ? fill : '#3a3a48');
      const opacity = g.confidence === 'Low' ? 0.42 : (g.confidence === 'Medium' ? 0.65 : 0.9);
      return `<circle class="bubble" data-id="${g.id}" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}" fill="${fill}" fill-opacity="${opacity}" stroke="${stroke}" stroke-width="${g.confidence === 'High' ? 2 : 1}"/>`;
    }).join('');

    // Axis titles
    const axisY = `<text x="${padL - 44}" y="${padT + innerH/2}" text-anchor="middle" transform="rotate(-90 ${padL - 44} ${padT + innerH/2})" class="ax-title">Breakout Score</text>`;
    const axisX = `<text x="${padL + innerW/2}" y="${H - 6}" text-anchor="middle" class="ax-title">Lifecycle stage</text>`;

    const svg = `
      <svg id="explore-svg" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
        ${yTicks}
        ${xTicks}
        ${axisY}
        ${axisX}
        ${circles}
      </svg>
    `;
    document.getElementById('explore-chart').innerHTML = svg;

    // Bubble hover + click
    const tip = document.getElementById('explore-tooltip');
    document.querySelectorAll('.bubble').forEach(b => {
      b.addEventListener('mouseenter', (e) => {
        const id = b.dataset.id;
        const g = data.games[id];
        if (!g) return;
        showTooltip(tip, e, g);
      });
      b.addEventListener('mousemove', (e) => positionTooltip(tip, e));
      b.addEventListener('mouseleave', () => { tip.hidden = true; });
      b.addEventListener('click', () => { location.href = `./game.html?id=${b.dataset.id}`; });
    });

    renderCallouts(list);
  }

  function showTooltip(tip, e, g) {
    const t = g.thesis || {};
    const rs = g.real_signals || {};
    tip.innerHTML = `
      ${g.header_image ? `<div class="tip-img" style="background-image:url(${g.header_image})"></div>` : ''}
      <div class="tip-body">
        <div class="tip-head">
          <span class="tip-name">${escapeHtml(g.name)}</span>
          <span class="tip-score">${g.score} <span class="tip-delta ${g.score_delta >= 0 ? 'up' : 'down'}">${signed(g.score_delta)}</span></span>
        </div>
        <div class="tip-tags">
          <span class="scale-pill" data-scale="${g.scale}">${g.scale}</span>
          <span class="stage-pill" data-stage="${g.stage_label}">${g.stage_label}</span>
          <span class="conf-pill" data-conf="${g.confidence}">${g.confidence}</span>
        </div>
        ${t.pull_quote ? `<p class="tip-quote">"${escapeHtml(t.pull_quote)}"</p>` : ''}
        <div class="tip-stats">
          ${rs.wishlists ? `<span>wishlists ${fmtNum(rs.wishlists)}</span>` : ''}
          ${rs.followers ? `<span>followers ${fmtNum(rs.followers)}</span>` : ''}
          ${rs.igdb_hypes ? `<span>hypes ${rs.igdb_hypes}</span>` : ''}
          ${rs.revenue ? `<span>rev ${fmtRev(rs.revenue)}</span>` : ''}
        </div>
      </div>
    `;
    tip.hidden = false;
    positionTooltip(tip, e);
  }

  function positionTooltip(tip, e) {
    const r = tip.getBoundingClientRect();
    const wrapR = document.querySelector('.explore-chart-container').getBoundingClientRect();
    let x = e.clientX - wrapR.left + 18;
    let y = e.clientY - wrapR.top + 18;
    if (x + r.width > wrapR.width) x = e.clientX - wrapR.left - r.width - 14;
    if (y + r.height > wrapR.height + 40) y = wrapR.height - r.height - 8;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  }

  function renderCallouts(list) {
    // Show 4-6 most interesting outliers as image cards under the chart
    const top = list
      .filter(g => !g.is_broken_out && g.score >= 50)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6);
    const root = document.getElementById('explore-callouts');
    if (!top.length) { root.innerHTML = ''; return; }
    root.innerHTML = `
      <h2 class="section-label">Top picks in current view</h2>
      <div class="callout-row">
        ${top.map(g => {
          const t = g.thesis || {};
          return `
            <a class="callout" href="./game.html?id=${g.id}">
              <div class="callout-img" style="background-image: url(${g.header_image || ''})"></div>
              <div class="callout-body">
                <div class="callout-head">
                  <span class="callout-name">${escapeHtml(g.name)}</span>
                  <span class="callout-score">${g.score}</span>
                </div>
                <div class="callout-tags">
                  <span class="scale-pill" data-scale="${g.scale}">${g.scale}</span>
                  <span class="stage-pill" data-stage="${g.stage_label}">${g.stage_label}</span>
                </div>
                ${t.pull_quote ? `<p class="callout-quote">"${escapeHtml(t.pull_quote)}"</p>` : ''}
              </div>
            </a>
          `;
        }).join('')}
      </div>
    `;
  }

  function jitterFor(id, magnitude) {
    // Deterministic small horizontal jitter so overlapping points spread out
    let h = 0;
    const s = String(id);
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xffffffff;
    return ((h & 0xffff) / 0xffff - 0.5) * magnitude;
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
