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
      <div class="score-stat score-stat-radar">
        <span class="stat-label">Confidence</span>
        <div class="stat-value">${g.confidence} <span class="conf-fam-count">${g.confidence_families}/5</span></div>
        ${scoutCharts.renderRadar([
          {label: 'attention', magnitude: famMag(g, 'attention')},
          {label: 'intent', magnitude: famMag(g, 'intent')},
          {label: 'performance', magnitude: famMag(g, 'performance')},
          {label: 'community', magnitude: famMag(g, 'community')},
          {label: 'press', magnitude: famMag(g, 'press')},
        ], {width: 180, height: 160})}
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

    <section class="section">
      <h3>Signal arc — last ${(g.signal_arc || []).length || '?'} days</h3>
      ${renderSignalArcSection(g)}
    </section>

    ${(g.nearest_comparables && g.nearest_comparables.length) ? `
      <section class="section">
        <h3>Nearest comparables</h3>
        <div class="nearest-comp-list">
          ${g.nearest_comparables.map(nc => `
            <div class="nearest-comp-wrap">
              <a class="nearest-comp" href="./comparables.html">
                <div>
                  <div class="nc-name">${escapeHtml(nc.name)} <span style="color: var(--fg-3); font-size: 12px;">(${nc.year})</span></div>
                  <div class="nc-meta">${escapeHtml(nc.stage_arc || '')} · ${escapeHtml(nc.primary_cluster || '')} · <span class="outcome-tag" data-outcome="${nc.outcome}">${nc.outcome}</span></div>
                </div>
                <span class="nc-similarity">similarity ${nc.similarity}</span>
              </a>
              ${nc.arc && nc.arc.length >= 3 ? renderComparableOverlay(g, nc) : ''}
            </div>
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
    const arc = g.signal_arc || [];
    const sparkVals = field => {
      const vs = arc.map(p => p[field]).filter(v => v != null && !isNaN(v));
      return vs.length >= 3 ? vs : null;
    };
    const sparkFor = field => {
      const vs = sparkVals(field);
      return vs ? scoutCharts.renderSparkline(vs, {width: 64, height: 18}) : '';
    };
    if (rs.revenue) items.push({k: 'Revenue (lifetime)', v: fmtRev(rs.revenue), spark: sparkFor('revenue')});
    if (rs.owners) items.push({k: 'Owners', v: fmtNum(rs.owners), spark: ''});
    if (rs.followers) items.push({k: 'Steam followers', v: fmtNum(rs.followers), spark: sparkFor('followers')});
    if (rs.wishlists) items.push({k: 'Wishlists', v: fmtNum(rs.wishlists), spark: sparkFor('wishlists')});
    if (rs.reviews_total) {
      // Sentiment shift if we have history
      const scoreVals = sparkVals('score');
      const shiftMarkup = scoreVals && scoreVals.length >= 2
        ? scoutCharts.renderSentimentShift(scoreVals[scoreVals.length - 1], scoreVals[0])
        : (rs.review_ratio ? `<span class="muted">(${Math.round(rs.review_ratio*100)}%)</span>` : '');
      items.push({k: 'Reviews', v: `${fmtNum(rs.reviews_total)} ${shiftMarkup}`, spark: sparkFor('reviews')});
    }
    if (rs.twitch_viewers !== undefined) items.push({k: 'Twitch live', v: `${fmtNum(rs.twitch_viewers)} viewers · ${rs.twitch_streams} streams`, spark: ''});
    if (rs.avg_playtime) items.push({k: 'Avg playtime', v: `${rs.avg_playtime.toFixed(1)} h`, spark: ''});
    if (igdb.hypes) items.push({k: 'IGDB hypes', v: `${igdb.hypes}`, spark: ''});
    if (igdb.aggregated_rating) items.push({k: 'Critic score', v: `${Math.round(igdb.aggregated_rating)} <span class="muted">(${igdb.aggregated_rating_count} sources)</span>`, spark: ''});

    if (!items.length) return '';
    return `
      <div class="vcard">
        <div class="vcard-label">Real numbers</div>
        <div class="metric-grid">
          ${items.map(i => `
            <div class="metric">
              <span class="m-k">${i.k}</span>
              <span class="m-v">${i.v}</span>
              ${i.spark || ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  function famMag(g, fam) {
    const sig = (g.signals || []).find(s => s.family === fam);
    if (sig) return sig.magnitude || 0;
    // Fallback to firing-state if signal not in list
    return (g.family_states || {})[fam] ? 0.7 : 0.25;
  }

  function renderSignalArcSection(g) {
    const arc = g.signal_arc || [];
    if (arc.length < 2) {
      return `<div class="arc-empty">Tracking begins as snapshot history accumulates. Currently ${arc.length} point${arc.length === 1 ? '' : 's'} on file.</div>`;
    }
    // Build datasets from what's available
    const buildSeries = field => arc.map(p => ({t: p.ts, v: p[field]})).filter(p => p.v != null);
    const datasets = [];
    const wishVals = buildSeries('wishlists');
    if (wishVals.length >= 2) datasets.push({label: 'Wishlists', color: '#88c0ff', values: wishVals});
    const followerVals = buildSeries('followers');
    if (followerVals.length >= 2) datasets.push({label: 'Followers', color: '#4ed3b6', values: followerVals});
    const playerVals = buildSeries('players');
    if (playerVals.length >= 2) datasets.push({label: 'Concurrent', color: '#f4b740', values: playerVals});
    const revVals = buildSeries('revenue');
    if (revVals.length >= 2) datasets.push({label: 'Revenue', color: '#ff6a45', values: revVals});
    if (!datasets.length) {
      return `<div class="arc-empty">No multi-point series available yet.</div>`;
    }
    return scoutCharts.renderArcChart(datasets, {width: 760, height: 220});
  }

  function renderComparableOverlay(g, nc) {
    const gArc = g.signal_arc || [];
    const ncArc = nc.arc || [];
    // Pick the best shared field — usually wishlists for pre-launch, players for launched.
    const fields = g.stage === 'Launched' || g.stage === 'EA'
      ? ['players', 'revenue', 'wishlists', 'followers']
      : ['wishlists', 'followers'];
    let field = null;
    for (const f of fields) {
      const a = gArc.filter(p => p[f] != null);
      const b = ncArc.filter(p => p[f] != null);
      if (a.length >= 2 && b.length >= 2) { field = f; break; }
    }
    if (!field) return '';
    const gSeries = gArc.map(p => ({t: p.ts, v: p[field]})).filter(p => p.v != null);
    const ncSeries = ncArc.map(p => ({t: p.ts, v: p[field]})).filter(p => p.v != null);
    if (!gSeries.length || !ncSeries.length) return '';

    // Normalise both series to a "days-since-first-point" X axis so they overlay properly
    const normalise = series => {
      const t0 = series[0].t;
      return series.map(p => ({t: (p.t - t0) / 86400, v: p.v}));
    };
    return `
      <div class="comp-overlay">
        <div class="comp-overlay-label">Overlay on ${escapeHtml(field)} — relative arc</div>
        ${scoutCharts.renderArcChart([
          {label: g.name, color: '#88c0ff', values: normalise(gSeries)},
          {label: nc.name, color: '#ff7a90', dashed: true, values: normalise(ncSeries)},
        ], {width: 600, height: 140})}
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
