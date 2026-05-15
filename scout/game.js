// Scout — Game Detail renderer
(async () => {
  const id = new URLSearchParams(location.search).get('id');
  if (!id) { document.getElementById('game-root').textContent = 'No game id.'; return; }
  const data = await fetch('./data/scout-data.json').then(r => r.json());
  const g = data.games[id];
  if (!g) { document.getElementById('game-root').textContent = `Unknown game ${id}.`; return; }
  document.title = `${g.name} · Scout`;

  const t = g.thesis || {};
  const up = g.score_delta >= 0;
  const root = document.getElementById('game-root');
  const stages = ["Announced", "Demo", "Wishlist", "Early Access", "Launched"];
  const currentStage = g.stage_label;
  const rs = g.real_signals || {};
  const igdb = g.igdb || {};
  const fam = g.family_states || {};

  const fmtRev = v => v >= 1_000_000_000 ? `$${(v/1_000_000_000).toFixed(2)}B` : v >= 1_000_000 ? `$${(v/1_000_000).toFixed(1)}M` : v >= 1000 ? `$${(v/1000).toFixed(0)}K` : `$${v}`;
  const fmtNum = v => v >= 1_000_000 ? `${(v/1_000_000).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(0)}K` : `${v}`;

  root.innerHTML = `
    <header class="hero">
      <div class="hero-img" style="background-image: url(${g.header_image || ''})"></div>
      <div class="hero-head">
        <h1 class="hero-title">${escapeHtml(g.name)}</h1>
        <div class="hero-sub">
          <span class="stage-pill" data-stage="${g.stage_label}">${g.stage_label}</span>
          <span class="sep">·</span>
          <span>${escapeHtml(g.price || 'TBD')}</span>
          <span class="sep">·</span>
          <span>${escapeHtml(g.studio || 'Unknown')}</span>
          ${g.release_date ? `<span class="sep">·</span><span>${escapeHtml(g.release_date)}</span>` : ''}
          ${g.is_mature_phenom ? `<span class="sep">·</span><span class="mature-tag">Mature phenom — score dampened</span>` : ''}
        </div>
      </div>
    </header>

    <section class="score-block">
      <div class="score-stat">
        <span class="stat-label">Breakout Score</span>
        <div class="stat-value">${g.score} <span class="stat-delta ${up ? '' : 'down'}">${signed(g.score_delta)}</span></div>
      </div>
      <div class="score-stat">
        <span class="stat-label">Confidence</span>
        <div class="stat-value">${g.confidence}</div>
        <div class="family-dots" aria-label="Signal families firing">
          ${['attention','intent','performance','community','press'].map(f => `
            <span class="fam-dot ${fam[f] ? 'on' : ''}" title="${f}${fam[f] ? ' — firing' : ''}">
              <span class="dot"></span>
              <span class="lbl">${f}</span>
            </span>
          `).join('')}
        </div>
      </div>
      <div class="score-stat">
        <span class="stat-label">Scale</span>
        <div class="stat-value"><span class="scale-pill" data-scale="${g.scale}">${g.scale}</span></div>
        <div class="stat-detail">projected peak CCU ${formatBand(g.scale_band)}</div>
      </div>
    </section>

    <div class="meta-strip">
      <span class="meta-strip-label">Meta</span>
      <span class="meta-mod" data-mod="${g.meta_modifier}">${g.meta_modifier === 'tailwind' ? 'Tailwind ↑' : g.meta_modifier === 'headwind' ? 'Headwind ↓' : 'Neutral'}</span>
      ${(g.meta_clusters || []).map(c => `<span class="meta-tag">${escapeHtml(c)}</span>`).join('')}
    </div>

    <section class="cards-row">
      ${renderGenreFingerprint(g)}
      ${renderRealMetrics(g, rs, igdb)}
      ${renderAudienceOverlap(g)}
    </section>

    <section class="timeline">
      <div class="timeline-track">
        ${stages.map((s, i) => `
          ${i ? `<div class="tl-connector"></div>` : ''}
          <div class="tl-node ${stages.indexOf(currentStage) >= i ? 'active' : ''}">
            <div class="dot"></div>
            <div class="stage-name">${s}</div>
            ${s === currentStage ? '<div class="stage-date">you are here</div>' : ''}
          </div>
        `).join('')}
      </div>
    </section>

    ${t.the_read ? `
      <section class="section">
        <h3>The Read</h3>
        <ul class="read-bullets">
          ${t.the_read.map(b => `<li>${escapeHtml(b)}</li>`).join('')}
        </ul>
      </section>` : ''}

    ${t.against_consensus ? `
      <section class="section against">
        <h3>Against Consensus</h3>
        <p class="paragraph">${escapeHtml(t.against_consensus)}</p>
      </section>` : ''}

    ${t.comparable ? `
      <section class="section">
        <h3>Comparable</h3>
        <p class="paragraph">${escapeHtml(t.comparable)}</p>
      </section>` : ''}

    ${t.what_would_change_my_mind ? `
      <section class="section">
        <h3>What would change my mind</h3>
        <p class="paragraph">${escapeHtml(t.what_would_change_my_mind)}</p>
      </section>` : ''}

    ${(t.risks && t.risks.length) ? `
      <section class="section">
        <h3>Risks</h3>
        <ul class="risks">
          ${t.risks.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
        </ul>
      </section>` : ''}

    ${(g.nearest_comparables && g.nearest_comparables.length) ? `
      <section class="section">
        <h3>Nearest comparables</h3>
        <div class="nearest-comp-list">
          ${g.nearest_comparables.map(nc => `
            <a class="nearest-comp" href="./comparables.html">
              <div>
                <div class="nc-name">${escapeHtml(nc.name)} <span style="color: var(--fg-3); font-size: 12px;">(${nc.year})</span></div>
                <div class="nc-meta">${escapeHtml(nc.stage_arc || '')} · ${escapeHtml(nc.primary_cluster || '')} · <span class="outcome-tag" data-outcome="${nc.outcome}">${nc.outcome}</span></div>
              </div>
              <span class="nc-similarity">similarity ${nc.similarity}</span>
            </a>
          `).join('')}
        </div>
      </section>` : ''}

    <section class="section">
      <h3>Top signals this week</h3>
      <div class="signals">
        ${(g.signals || []).slice(0, 5).map(s => `
          <div class="signal-row">
            <div class="signal-name">
              ${escapeHtml(s.name)}
              ${s.real ? '<span class="real-pip" title="Live data">●</span>' : '<span class="synth-pip" title="Synthesized">○</span>'}
            </div>
            <div class="signal-bar"><div class="signal-bar-fill" style="width: ${Math.round(s.magnitude * 100)}%"></div></div>
            <div class="signal-value">${escapeHtml(s.value_label)}</div>
          </div>
        `).join('')}
      </div>
      <div class="data-source-key">
        <span class="real-pip">●</span> live data
        <span class="synth-pip">○</span> synthesized (replaced once snapshot history accumulates)
      </div>
    </section>

    <div class="actions">
      <button class="action-btn">Full signal history</button>
      <button class="action-btn">Comparables overlay</button>
      <button class="action-btn">Studio track record</button>
    </div>
  `;

  function renderGenreFingerprint(g) {
    const tags = (g.tags || []).slice(0, 10);
    if (!tags.length) return '';
    const modes = (g.igdb?.game_modes || []);
    const persp = (g.igdb?.player_perspectives || []);
    return `
      <div class="vcard">
        <div class="vcard-label">Genre fingerprint</div>
        <div class="tag-cloud">
          ${tags.map((t, i) => `<span class="tag-chip" data-weight="${Math.min(3, 3 - Math.floor(i / 4))}">${escapeHtml(t)}</span>`).join('')}
        </div>
        ${(modes.length || persp.length) ? `
          <div class="vcard-row">
            ${modes.length ? `<div class="vcard-pair"><span class="k">Modes</span><span class="v">${modes.map(escapeHtml).join(' · ')}</span></div>` : ''}
            ${persp.length ? `<div class="vcard-pair"><span class="k">Perspective</span><span class="v">${persp.map(escapeHtml).join(' · ')}</span></div>` : ''}
          </div>` : ''}
      </div>
    `;
  }

  function renderRealMetrics(g, rs, igdb) {
    const items = [];
    if (rs.revenue) items.push({k: 'Revenue (lifetime)', v: fmtRev(rs.revenue)});
    if (rs.owners) items.push({k: 'Owners', v: fmtNum(rs.owners)});
    if (rs.followers) items.push({k: 'Steam followers', v: fmtNum(rs.followers)});
    if (rs.wishlists) items.push({k: 'Wishlists', v: fmtNum(rs.wishlists)});
    if (rs.reviews_total) items.push({k: 'Reviews', v: `${fmtNum(rs.reviews_total)}` + (rs.review_ratio ? ` <span class="muted">(${Math.round(rs.review_ratio*100)}%)</span>` : '')});
    if (rs.twitch_viewers !== undefined) items.push({k: 'Twitch live', v: `${fmtNum(rs.twitch_viewers)} viewers · ${rs.twitch_streams} streams`});
    if (rs.avg_playtime) items.push({k: 'Avg playtime', v: `${rs.avg_playtime.toFixed(1)} h`});
    if (igdb.hypes) items.push({k: 'IGDB hypes', v: `${igdb.hypes}`});
    if (igdb.aggregated_rating) items.push({k: 'Critic score', v: `${Math.round(igdb.aggregated_rating)} <span class="muted">(${igdb.aggregated_rating_count} sources)</span>`});

    if (!items.length) return '';
    return `
      <div class="vcard">
        <div class="vcard-label">Real numbers</div>
        <div class="metric-grid">
          ${items.map(i => `<div class="metric"><span class="m-k">${i.k}</span><span class="m-v">${i.v}</span></div>`).join('')}
        </div>
      </div>
    `;
  }

  function renderAudienceOverlap(g) {
    const overlap = g.audience_overlap || [];
    const similar = g.igdb?.similar || [];
    if (!overlap.length && !similar.length) return '';
    return `
      <div class="vcard">
        <div class="vcard-label">Audience overlap</div>
        ${overlap.length ? `
          <div class="overlap-list">
            ${overlap.slice(0, 5).map(o => `
              <div class="overlap-row">
                <span class="o-name">${escapeHtml(o.name || '')}</span>
                <span class="o-bar"><span class="o-bar-fill" style="width: ${Math.min(100, Math.round((o.link || 0) * 100))}%"></span></span>
                <span class="o-pct">${Math.round((o.link || 0) * 100)}%</span>
              </div>
            `).join('')}
          </div>` : ''}
        ${similar.length ? `
          <div class="vcard-row" style="padding-top: 8px;">
            <div class="vcard-pair">
              <span class="k">IGDB similar</span>
              <span class="v">${similar.slice(0, 4).map(s => escapeHtml(s.name)).join(' · ')}</span>
            </div>
          </div>` : ''}
      </div>
    `;
  }
})();

function formatBand(band) {
  if (!Array.isArray(band)) return '—';
  const [min, max] = band;
  return `${(min/1000).toFixed(0)}–${(max/1000).toFixed(0)}K`;
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
