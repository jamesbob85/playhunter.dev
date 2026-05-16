// Scout — visual conviction primitives. Pure SVG, no dependencies.

// ── Confidence Radar ──────────────────────────────────────────────────
// axes: [{label, magnitude}] — magnitude 0..1
function renderRadar(axes, opts) {
  opts = opts || {};
  const w = opts.width || 200;
  const h = opts.height || 200;
  const cx = w / 2, cy = h / 2;
  const radius = Math.min(cx, cy) - 26;
  const n = axes.length;
  const angle = i => (Math.PI * 2 * i / n) - Math.PI / 2;

  // Polygon points based on magnitudes
  const points = axes.map((a, i) => {
    const r = radius * (a.magnitude || 0);
    return [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))];
  });

  // Reference rings at 25/50/75/100%
  const rings = [0.25, 0.5, 0.75, 1.0].map(t => {
    const pts = axes.map((_, i) => {
      const r = radius * t;
      return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
    }).join(' ');
    return `<polygon points="${pts}" fill="none" stroke="var(--line)" stroke-width="1"/>`;
  }).join('');

  // Spoke lines + labels
  const spokes = axes.map((a, i) => {
    const x = cx + radius * Math.cos(angle(i));
    const y = cy + radius * Math.sin(angle(i));
    const lx = cx + (radius + 14) * Math.cos(angle(i));
    const ly = cy + (radius + 14) * Math.sin(angle(i)) + 3;
    const labelClass = (a.magnitude || 0) > 0.55 ? 'rd-axis-on' : 'rd-axis';
    return `
      <line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--line)" stroke-width="1"/>
      <text x="${lx}" y="${ly}" text-anchor="middle" class="${labelClass}">${a.label}</text>
    `;
  }).join('');

  // Filled polygon (the actual values)
  const polyPts = points.map(p => p.join(',')).join(' ');
  const dots = points.map((p, i) => {
    const on = (axes[i].magnitude || 0) > 0.55;
    return `<circle cx="${p[0]}" cy="${p[1]}" r="${on ? 3.5 : 2.5}" fill="${on ? 'var(--ok)' : 'var(--fg-3)'}"/>`;
  }).join('');

  return `
    <svg class="radar" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      ${rings}
      ${spokes}
      <polygon points="${polyPts}" fill="rgba(108,212,154,0.18)" stroke="var(--ok)" stroke-width="1.5"/>
      ${dots}
    </svg>
  `;
}

// ── Sparkline ──────────────────────────────────────────────────────────
function renderSparkline(values, opts) {
  opts = opts || {};
  const w = opts.width || 80;
  const h = opts.height || 22;
  if (!values || values.length < 2) {
    return `<svg class="sparkline" width="${w}" height="${h}"></svg>`;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = (max - min) || 1;
  const stepX = w / (values.length - 1);
  const pts = values.map((v, i) => `${(i * stepX).toFixed(1)},${(h - ((v - min) / range) * (h - 4) - 2).toFixed(1)}`).join(' ');
  const last = values[values.length - 1];
  const prev = values[0];
  const up = last >= prev;
  return `
    <svg class="sparkline" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      <polyline points="${pts}" fill="none" stroke="${up ? 'var(--ok)' : 'var(--warn)'}" stroke-width="1.5"/>
    </svg>
  `;
}

// ── Multi-line normalized arc chart ───────────────────────────────────
// datasets: [{label, color, values: [{t, v}]}]
// Each dataset is normalized to its own [0..1] range; X axis is shared timestamps.
function renderArcChart(datasets, opts) {
  opts = opts || {};
  const w = opts.width || 600;
  const h = opts.height || 200;
  const padL = 20, padR = 16, padT = 16, padB = 32;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  // Collect all timestamps across datasets to find global X range
  const allTs = [];
  datasets.forEach(d => (d.values || []).forEach(p => allTs.push(p.t)));
  if (!allTs.length) {
    return `<div class="arc-empty">No arc data yet — tracking begins as snapshots accumulate.</div>`;
  }
  const tMin = Math.min(...allTs), tMax = Math.max(...allTs);
  const tRange = (tMax - tMin) || 1;

  const xOf = t => padL + ((t - tMin) / tRange) * innerW;
  const yOf = (v, vMin, vMax) => padT + (1 - ((v - vMin) / ((vMax - vMin) || 1))) * innerH;

  // Render each dataset as a polyline, normalized to its own min/max
  const lines = datasets.map((d, idx) => {
    const vs = (d.values || []).filter(p => p.v != null);
    if (!vs.length) return '';
    const vMin = Math.min(...vs.map(p => p.v));
    const vMax = Math.max(...vs.map(p => p.v));
    const pts = vs.map(p => `${xOf(p.t).toFixed(1)},${yOf(p.v, vMin, vMax).toFixed(1)}`).join(' ');
    const last = vs[vs.length - 1];
    return `
      <polyline points="${pts}" fill="none" stroke="${d.color}" stroke-width="${d.dashed ? 1.4 : 2}" ${d.dashed ? 'stroke-dasharray="3 3"' : ''} opacity="${d.dashed ? 0.7 : 1}"/>
      <circle cx="${xOf(last.t)}" cy="${yOf(last.v, vMin, vMax)}" r="3" fill="${d.color}"/>
    `;
  }).join('');

  // X-axis tick marks (start, mid, end)
  const ticks = [0, 0.5, 1].map(p => {
    const t = tMin + (tMax - tMin) * p;
    const x = xOf(t);
    const dt = new Date(t * 1000);
    const label = `${dt.getUTCMonth() + 1}/${dt.getUTCDate()}`;
    return `
      <line x1="${x}" y1="${padT}" x2="${x}" y2="${h - padB}" stroke="var(--line)" stroke-width="0.5" stroke-dasharray="2 3"/>
      <text x="${x}" y="${h - padB + 14}" text-anchor="middle" class="ax-tick">${label}</text>
    `;
  }).join('');

  // Legend
  const legend = datasets.map(d => {
    const last = (d.values || []).filter(p => p.v != null).slice(-1)[0];
    const lastFmt = last ? fmtBig(last.v) : '—';
    return `
      <span class="leg-item">
        <span class="leg-swatch" style="background:${d.color}"></span>
        <span class="leg-label">${d.label}</span>
        <span class="leg-value">${lastFmt}</span>
      </span>
    `;
  }).join('');

  return `
    <div class="arc-wrap">
      <svg class="arc-chart" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
        ${ticks}
        ${lines}
      </svg>
      <div class="arc-legend">${legend}</div>
    </div>
  `;
}

// ── Sentiment shift ───────────────────────────────────────────────────
function renderSentimentShift(currentScore, priorScore) {
  if (currentScore == null) return '';
  if (priorScore == null) {
    return `<span class="sentiment-flat">${Math.round(currentScore)}%</span>`;
  }
  const diff = currentScore - priorScore;
  const dir = diff > 1 ? 'up' : diff < -1 ? 'down' : 'flat';
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '→';
  return `
    <span class="sentiment-shift" data-dir="${dir}">
      <span class="ss-arrow">${arrow}</span>
      <span class="ss-current">${Math.round(currentScore)}%</span>
      <span class="ss-diff">${diff > 0 ? '+' : ''}${diff.toFixed(1)}</span>
    </span>
  `;
}

// ── Helpers ────────────────────────────────────────────────────────────
function fmtBig(v) {
  if (v == null) return '—';
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${Math.round(v)}`;
}

// Export for game.js
window.scoutCharts = {
  renderRadar,
  renderSparkline,
  renderArcChart,
  renderSentimentShift,
  fmtBig,
};
