/* District Prosperity Index dashboard.
 *
 * Loads data/dashboard.json (written by scripts/export_site.py) and draws every
 * section from it. There is no server and no build step: plain DOM and SVG.
 * Two filters, year and state, scope the whole page; every draw function reads
 * them from `S` and is re-run by render().
 */
(() => {
  'use strict';

  // ---------------------------------------------------------------- helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const SVG_NS = 'http://www.w3.org/2000/svg';

  /** Create an HTML element. `text` sets textContent; `on*` adds a listener. */
  function h(tag, attrs = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null || value === false) continue;
      if (key === 'text') node.textContent = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    node.append(...kids.filter((k) => k != null));
    return node;
  }

  /** Create an SVG element. */
  function s(tag, attrs = {}, text) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text != null) node.textContent = text;
    return node;
  }

  const DASH = '–';
  const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmt = (value, formatter) => (value == null ? DASH : formatter.format(value));

  /** Large counts in Indian units: 1 lakh = 100,000 and 1 crore = 10,000,000. */
  function indianCount(n) {
    if (n == null) return DASH;
    if (Math.abs(n) >= 1e7) return `${nf1.format(n / 1e7)} crore`;
    if (Math.abs(n) >= 1e5) return `${nf1.format(n / 1e5)} lakh`;
    return nf0.format(n);
  }

  /** Money that is already in crore rupees. */
  function rupeesCrore(cr) {
    if (cr == null) return DASH;
    if (cr >= 1e5) return `₹${nf2.format(cr / 1e5)} lakh crore`;
    return `₹${nf0.format(cr)} crore`;
  }

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthLabel = (ym) => `${MONTHS[+ym.slice(5) - 1]} ${ym.slice(0, 4)}`;
  const mean = (list) => (list.length ? list.reduce((a, b) => a + b, 0) / list.length : null);

  /** Round axis values: 0, step, 2*step ... up to the first value above `max`. */
  function niceTicks(max, intervals = 4) {
    const raw = max / intervals;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const norm = raw / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
    const ticks = [];
    for (let v = 0; v < max + step * 0.999; v += step) ticks.push(+v.toPrecision(12));
    return ticks;
  }

  // ---------------------------------------------------------------- tooltip
  const tip = $('#tip');

  function showTip(lines, x, y) {
    tip.replaceChildren(h('strong', { text: lines[0] }),
      ...lines.slice(1).map((line) => h('span', { text: line })));
    tip.hidden = false;
    const box = tip.getBoundingClientRect();
    let left = x + 14;
    let top = y - box.height - 12;
    if (left + box.width > window.innerWidth - 8) left = x - box.width - 14;
    if (left < 8) left = 8;
    if (top < 8) top = y + 16;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }

  function hideTip() { tip.hidden = true; }

  /** Show the same tooltip on hover and on keyboard focus. */
  function attachTip(node, lines) {
    node.addEventListener('pointermove', (e) => showTip(lines, e.clientX, e.clientY));
    node.addEventListener('pointerleave', hideTip);
    node.addEventListener('focus', () => {
      const box = node.getBoundingClientRect();
      showTip(lines, box.left + Math.min(box.width, 320), box.top);
    });
    node.addEventListener('blur', hideTip);
  }

  // ---------------------------------------------------------------- line chart
  /**
   * Draw a single-series line chart into `host` and keep it sized to its width.
   * opt: { values, label, xTicks:[{i,label}], yTick(v), tip(i) -> [title, ...lines],
   *        band:[i0,i1], area, markers, endLabel, height }
   */
  function lineChart(host, opt) {
    host._opt = opt;
    if (!host._observer) {
      host._observer = new ResizeObserver(() => drawLine(host));
      host._observer.observe(host);
    }
    drawLine(host);
  }

  function drawLine(host) {
    const o = host._opt;
    if (!o || !host.clientWidth) return;
    const W = Math.max(host.clientWidth, 260);
    const H = o.height || 260;
    const m = { l: 46, r: 18, t: 20, b: 28 };
    const vals = o.values;
    const n = vals.length;
    const present = vals.filter((v) => v != null);
    const ticks = niceTicks(Math.max(...present, 1e-9));
    const top = ticks[ticks.length - 1];
    const innerW = W - m.l - m.r;
    const innerH = H - m.t - m.b;
    const X = (i) => m.l + (n > 1 ? i / (n - 1) : 0.5) * innerW;
    const Y = (v) => m.t + (1 - v / top) * innerH;

    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', tabindex: 0, 'aria-label': o.label });

    if (o.band) {
      const half = innerW / Math.max(n - 1, 1) / 2;
      const x0 = Math.max(X(o.band[0]) - half, m.l);
      const x1 = Math.min(X(o.band[1]) + half, m.l + innerW);
      svg.append(s('rect', { class: 'band', x: x0, y: m.t, width: x1 - x0, height: innerH }));
    }
    for (const t of ticks) {
      svg.append(s('line', { class: t === 0 ? 'base-line' : 'grid-line', x1: m.l, x2: m.l + innerW, y1: Y(t), y2: Y(t) }));
      svg.append(s('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end' }, o.yTick(t)));
    }
    for (const t of o.xTicks) {
      svg.append(s('text', { x: X(t.i), y: H - 8, 'text-anchor': 'middle' }, t.label));
    }

    // Split the line wherever a value is missing.
    const runs = [];
    let run = [];
    vals.forEach((v, i) => {
      if (v == null) { if (run.length) runs.push(run); run = []; } else run.push(i);
    });
    if (run.length) runs.push(run);
    for (const idx of runs) {
      const d = idx.map((i, k) => `${k ? 'L' : 'M'}${X(i).toFixed(1)},${Y(vals[i]).toFixed(1)}`).join('');
      if (o.area && idx.length > 1) {
        svg.append(s('path', { class: 'area', d: `${d}L${X(idx[idx.length - 1]).toFixed(1)},${Y(0)}L${X(idx[0]).toFixed(1)},${Y(0)}Z` }));
      }
      svg.append(s('path', { class: 'line', d }));
    }
    if (o.markers) {
      vals.forEach((v, i) => { if (v != null) svg.append(s('circle', { class: 'dot', cx: X(i), cy: Y(v), r: 4 })); });
    }
    if (o.endLabel && present.length) {
      const last = vals.reduce((acc, v, i) => (v != null ? i : acc), 0);
      svg.append(s('circle', { class: 'dot', cx: X(last), cy: Y(vals[last]), r: 4 }));
      svg.append(s('text', { class: 'end-label', x: X(last), y: Y(vals[last]) - 10, 'text-anchor': 'end' }, o.endLabel));
    }

    // Hover layer: a crosshair that snaps to the nearest point.
    const cross = s('line', { class: 'crosshair', y1: m.t, y2: m.t + innerH, visibility: 'hidden' });
    const dot = s('circle', { class: 'dot', r: 5, visibility: 'hidden' });
    svg.append(cross, dot);
    let current = -1;
    const clear = () => {
      current = -1;
      cross.setAttribute('visibility', 'hidden');
      dot.setAttribute('visibility', 'hidden');
      hideTip();
    };
    const select = (i) => {
      i = Math.min(n - 1, Math.max(0, i));
      if (vals[i] == null) { clear(); return; }
      current = i;
      cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i));
      dot.setAttribute('cx', X(i)); dot.setAttribute('cy', Y(vals[i]));
      cross.setAttribute('visibility', 'visible');
      dot.setAttribute('visibility', 'visible');
      const box = svg.getBoundingClientRect();
      showTip(o.tip(i), box.left + X(i), box.top + Y(vals[i]));
    };
    svg.addEventListener('pointermove', (e) => {
      const box = svg.getBoundingClientRect();
      select(Math.round(((e.clientX - box.left - m.l) / innerW) * (n - 1)));
    });
    svg.addEventListener('pointerleave', clear);
    svg.addEventListener('focus', () => select(n - 1));
    svg.addEventListener('blur', clear);
    svg.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      select((current < 0 ? n - 1 : current) + (e.key === 'ArrowLeft' ? -1 : 1));
    });

    host.replaceChildren(svg);
  }

  // ---------------------------------------------------------------- bar list
  /**
   * Horizontal bars as plain HTML rows: name, bar, value at the bar tip.
   * rows: [{ name, sub, value, label, cls, tip:[...], onClick, selected }]
   */
  function barList(host, rows, max, emptyText) {
    if (!rows.length) {
      host.replaceChildren(h('p', { class: 'empty', text: emptyText || 'Nothing to show.' }));
      return;
    }
    host.replaceChildren(...rows.map((row) => {
      const share = max > 0 ? Math.abs(row.value) / max : 0;
      const bar = h('span', { class: `bar ${row.cls || ''}` });
      bar.style.width = `calc((100% - 56px) * ${share.toFixed(4)})`;
      const node = h(row.onClick ? 'button' : 'div', {
        class: `bar-row${row.selected ? ' is-selected' : ''}`,
        type: row.onClick ? 'button' : null,
        'aria-pressed': row.onClick && row.selected != null ? String(row.selected) : null,
        onclick: row.onClick,
      },
        h('span', { class: 'bar-name' }, row.name, row.sub ? h('small', { text: `  ${row.sub}` }) : null),
        h('span', { class: 'bar-track' }, bar, h('span', { class: 'bar-value', text: row.label })));
      if (row.tip) attachTip(node, row.tip);
      return node;
    }));
  }

  /** Fill a table from a header list and rows of cells ({text, num} or strings). */
  function fillTable(table, headers, rows) {
    const cell = (tag, c) => {
      const spec = typeof c === 'object' && c !== null && !(c instanceof Node) ? c : { text: c };
      const node = h(tag, { class: [spec.num ? 'num' : '', spec.opt ? 'opt' : ''].join(' ').trim() || null });
      if (spec.node) node.append(spec.node); else node.textContent = spec.text;
      return node;
    };
    table.replaceChildren(
      h('thead', {}, h('tr', {}, ...headers.map((c) => cell('th', c)))),
      h('tbody', {}, ...rows.map((r) => h('tr', {}, ...r.map((c) => cell('td', c))))));
  }

  function tile(label, value, note) {
    return h('div', { class: 'tile' },
      h('p', { class: 'tile-label', text: label }),
      h('p', { class: 'tile-value', text: value }),
      note ? h('p', { class: 'tile-note' }, ...(Array.isArray(note) ? note : [note])) : null);
  }

  /** A signed change with an arrow, coloured by direction (up is good). */
  function delta(value, text) {
    if (value == null) return h('span', { text: DASH });
    if (value === 0) return h('span', { text: 'No change' });
    return h('span', { class: value > 0 ? 'delta-up' : 'delta-down', text: `${value > 0 ? '▲' : '▼'} ${text}` });
  }

  // ---------------------------------------------------------------- state
  let D;            // the loaded dashboard.json
  let YEARS;        // [2021, ...]
  const S = { yi: 0, state: '', q: '', sort: { key: 'rank', dir: 1 }, page: 0 };
  const PAGE_SIZE = 25;

  const scoped = () => D.districts.filter((d) => !S.state || d.state === S.state);
  const rankChange = (d, yi) => (yi > 0 && d.rank[yi] != null && d.rank[yi - 1] != null ? d.rank[yi - 1] - d.rank[yi] : null);
  const scopeName = () => S.state || 'All India';

  function setState(patch) {
    Object.assign(S, patch);
    S.page = 0;
    render();
  }

  // ---------------------------------------------------------------- sections
  function renderFilters() {
    $('#year-buttons').replaceChildren(...YEARS.map((year, i) =>
      h('button', { type: 'button', 'aria-pressed': String(i === S.yi), text: year, onclick: () => setState({ yi: i }) })));
    $('#state-select').value = S.state;
    document.querySelectorAll('[data-scope]').forEach((n) => { n.textContent = `${YEARS[S.yi]} · ${scopeName()}`; });
    document.querySelectorAll('[data-year-scope]').forEach((n) => { n.textContent = YEARS[S.yi]; });
  }

  /** Monthly UPI totals for the current state filter. */
  function upiSeries() {
    const sources = S.state ? [D.upi.by_state[S.state]].filter(Boolean) : Object.values(D.upi.by_state);
    const sum = (field) => D.upi.months.map((_, i) => sources.reduce((acc, st) => acc + (st[field][i] || 0), 0));
    return { value: sum('value_cr'), txns: sum('txns') };
  }

  function yearTotals(series) {
    return YEARS.map((year) => {
      let value = 0; let txns = 0;
      D.upi.months.forEach((ym, i) => {
        if (+ym.slice(0, 4) === year) { value += series.value[i]; txns += series.txns[i]; }
      });
      return { year, value, txns };
    });
  }

  function renderOverview() {
    const yi = S.yi;
    const list = scoped().filter((d) => d.dpi[yi] != null);
    const avg = mean(list.map((d) => d.dpi[yi]));
    const prevAvg = yi > 0 ? mean(scoped().filter((d) => d.dpi[yi - 1] != null).map((d) => d.dpi[yi - 1])) : null;
    const best = list.reduce((a, b) => (a && a.dpi[yi] >= b.dpi[yi] ? a : b), null);
    const series = upiSeries();
    const totals = yearTotals(series);
    const upiNow = totals[yi].value;
    const upiPrev = yi > 0 ? totals[yi - 1].value : null;
    const vsPrev = ` vs ${YEARS[yi - 1]}`;

    $('#tiles').replaceChildren(
      tile('Districts scored', nf0.format(list.length),
        S.state ? `in ${S.state}` : `across ${D.meta.states} states and union territories`),
      tile('Average score', fmt(avg, nf1),
        prevAvg == null ? 'out of 100' : [delta(+(avg - prevAvg).toFixed(1), nf1.format(Math.abs(avg - prevAvg))), vsPrev]),
      tile(`UPI value in ${YEARS[yi]}`, rupeesCrore(upiNow),
        upiPrev ? [delta(upiNow - upiPrev, `${nf0.format(Math.abs((upiNow / upiPrev - 1) * 100))}%`), vsPrev] : 'total for the year'),
      tile('Highest-scoring district', best ? best.name : DASH,
        best ? `Score ${nf1.format(best.dpi[yi])}${S.state ? '' : ` · ${best.state}`}` : null));

    const months = D.upi.months;
    const yearIdx = months.map((ym, i) => (+ym.slice(0, 4) === YEARS[yi] ? i : -1)).filter((i) => i >= 0);
    const peak = Math.max(...series.value);
    $('#upi-title').textContent = `Monthly UPI transaction value, ${scopeName()}`;
    lineChart($('#upi-chart'), {
      values: series.value,
      label: `Line chart of monthly UPI transaction value for ${scopeName()}, ${monthLabel(months[0])} to ${monthLabel(months[months.length - 1])}. Use the left and right arrow keys to read values.`,
      area: true,
      band: yearIdx.length ? [yearIdx[0], yearIdx[yearIdx.length - 1]] : null,
      xTicks: months.map((ym, i) => ({ i, label: ym.slice(0, 4), jan: ym.endsWith('-01') })).filter((t) => t.jan),
      yTick: (v) => (v && peak >= 10000 ? `${nf0.format(v / 1000)}K` : nf0.format(v)),
      endLabel: `₹${nf0.format(series.value[series.value.length - 1])} Cr`,
      tip: (i) => [monthLabel(months[i]), rupeesCrore(series.value[i]), `${indianCount(series.txns[i])} transactions`],
    });
    fillTable($('#upi-table'), ['Year', { text: 'UPI value', num: true }, { text: 'Transactions', num: true }],
      totals.map((t) => [String(t.year), { text: rupeesCrore(t.value), num: true }, { text: indianCount(t.txns), num: true }]));
  }

  const COLUMNS = [
    { key: 'rank', label: 'Rank', num: true, get: (d, yi) => d.rank[yi], show: (v) => fmt(v, nf0) },
    { key: 'name', label: 'District', get: (d) => d.name },
    { key: 'state', label: 'State', get: (d) => d.state },
    { key: 'dpi', label: 'Score', num: true, get: (d, yi) => d.dpi[yi] },
    { key: 'change', label: 'Rank change', num: true, get: rankChange },
    { key: 'upi', label: 'UPI ₹ per person', num: true, opt: true, get: (d, yi) => d.upi[yi], show: (v) => fmt(v, nf0) },
    { key: 'bb', label: 'Broadband per 100', num: true, opt: true, get: (d, yi) => d.bb[yi], show: (v) => fmt(v, nf1) },
    { key: 'gst', label: 'GST per 1,000', num: true, opt: true, get: (d, yi) => d.gst[yi], show: (v) => fmt(v, nf1) },
    { key: 'egov', label: 'e-Gov per person', num: true, opt: true, get: (d, yi) => d.egov[yi], show: (v) => fmt(v, nf2) },
    { key: 'lit', label: 'Literacy %', num: true, opt: true, get: (d) => d.lit, show: (v) => fmt(v, nf1) },
  ];

  function renderRankings() {
    const yi = S.yi;
    const col = COLUMNS.find((c) => c.key === S.sort.key);
    const q = S.q.trim().toLowerCase();
    const rows = scoped().filter((d) => !q || d.search.includes(q));
    rows.sort((a, b) => {
      const va = col.get(a, yi); const vb = col.get(b, yi);
      if (va == null && vb == null) return (a.rank[yi] || 0) - (b.rank[yi] || 0);
      if (va == null) return 1;       // missing values always go last
      if (vb == null) return -1;
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return cmp ? cmp * S.sort.dir : (a.rank[yi] || 0) - (b.rank[yi] || 0);
    });

    $('#rank-head').replaceChildren(...COLUMNS.map((c) => {
      const active = c.key === S.sort.key;
      return h('th', {
        class: [c.num ? 'num' : '', c.opt ? 'opt' : ''].join(' ').trim() || null,
        'aria-sort': active ? (S.sort.dir > 0 ? 'ascending' : 'descending') : 'none',
      }, h('button', {
        type: 'button',
        onclick: () => {
          const firstDir = ['rank', 'name', 'state'].includes(c.key) ? 1 : -1;
          setState({ sort: { key: c.key, dir: active ? -S.sort.dir : firstDir } });
        },
      }, c.label, h('span', { class: 'arrow', 'aria-hidden': 'true', text: active ? (S.sort.dir > 0 ? '▲' : '▼') : '' })));
    }));

    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    S.page = Math.min(S.page, pages - 1);
    const start = S.page * PAGE_SIZE;
    const visible = rows.slice(start, start + PAGE_SIZE);

    $('#rank-body').replaceChildren(...visible.map((d) => {
      const cells = COLUMNS.map((c) => {
        const v = c.get(d, yi);
        const td = h('td', { class: [c.num ? 'num' : '', c.opt ? 'opt' : ''].join(' ').trim() || null });
        if (c.key === 'name') {
          td.append(h('button', { type: 'button', class: 'link-btn', text: d.name, 'aria-haspopup': 'dialog' }));
        } else if (c.key === 'dpi') {
          const meter = h('span', { class: 'meter', 'aria-hidden': 'true' }, h('i'));
          meter.firstChild.style.width = `${Math.max(0, Math.min(100, v || 0))}%`;
          td.append(h('span', { class: 'score-cell' }, meter, h('span', { text: fmt(v, nf1) })));
        } else if (c.key === 'change') {
          td.append(v == null ? DASH : v === 0 ? '0' : delta(v, nf0.format(Math.abs(v))));
        } else {
          td.textContent = c.show ? c.show(v) : v;
        }
        return td;
      });
      return h('tr', { onclick: () => openDistrict(d) }, ...cells);
    }));
    if (!visible.length) {
      $('#rank-body').append(h('tr', {}, h('td', { colspan: COLUMNS.length, text: 'No district matches that search.' })));
    }

    $('#rank-count').textContent = `${nf0.format(rows.length)} ${rows.length === 1 ? 'district' : 'districts'}${q ? ` matching "${S.q.trim()}"` : ''}`;
    $('#page-info').textContent = rows.length
      ? `${nf0.format(start + 1)}–${nf0.format(start + visible.length)} of ${nf0.format(rows.length)}` : '';
    $('#prev-page').disabled = S.page === 0;
    $('#next-page').disabled = S.page >= pages - 1;
  }

  function renderStates() {
    const yi = S.yi;
    const groups = new Map();
    for (const d of D.districts) {
      if (d.dpi[yi] == null) continue;
      if (!groups.has(d.state)) groups.set(d.state, []);
      groups.get(d.state).push(d.dpi[yi]);
    }
    const stats = [...groups].map(([state, scores]) => ({
      state, n: scores.length, avg: mean(scores), best: Math.max(...scores), worst: Math.min(...scores),
    })).sort((a, b) => b.avg - a.avg);
    const max = Math.max(...stats.map((x) => x.avg));

    barList($('#state-bars'), stats.map((x) => ({
      name: x.state,
      value: x.avg,
      label: nf1.format(x.avg),
      cls: S.state && S.state !== x.state ? 'is-dim' : '',
      selected: S.state === x.state,
      tip: [x.state, `Average ${nf1.format(x.avg)} across ${x.n} ${x.n === 1 ? 'district' : 'districts'}`,
        `Highest ${nf1.format(x.best)} · Lowest ${nf1.format(x.worst)}`],
      onClick: () => setState({ state: S.state === x.state ? '' : x.state }),
    })), max);

    const num = (v) => ({ text: nf1.format(v), num: true });
    fillTable($('#state-table'),
      ['State or UT', { text: 'Districts', num: true }, { text: 'Average', num: true }, { text: 'Highest', num: true }, { text: 'Lowest', num: true }],
      stats.map((x) => [x.state, { text: String(x.n), num: true }, num(x.avg), num(x.best), num(x.worst)]));
  }

  function renderMovers() {
    const yi = S.yi;
    const note = $('#movers-note');
    const cols = $('#movers-cols');
    if (yi === 0) {
      $('#movers-scope').textContent = String(YEARS[0]);
      note.textContent = `${YEARS[0]} is the first year in the data, so there is no earlier rank to compare with. Pick a later year.`;
      note.hidden = false; cols.hidden = true;
      return;
    }
    note.hidden = true; cols.hidden = false;
    $('#movers-scope').textContent = `${YEARS[yi - 1]} to ${YEARS[yi]} · ${scopeName()}`;

    const moved = scoped().map((d) => ({ d, change: rankChange(d, yi) })).filter((x) => x.change);
    const gainers = moved.filter((x) => x.change > 0).sort((a, b) => b.change - a.change).slice(0, 10);
    const losers = moved.filter((x) => x.change < 0).sort((a, b) => a.change - b.change).slice(0, 10);
    const max = Math.max(1, ...gainers.concat(losers).map((x) => Math.abs(x.change)));
    const row = (x, cls) => ({
      name: x.d.name,
      sub: S.state ? '' : x.d.state,
      value: x.change,
      label: `${x.change > 0 ? '+' : '−'}${nf0.format(Math.abs(x.change))}`,
      cls,
      tip: [`${x.d.name}, ${x.d.state}`, `Rank ${x.d.rank[yi - 1]} in ${YEARS[yi - 1]} → ${x.d.rank[yi]} in ${YEARS[yi]}`,
        `Score ${fmt(x.d.dpi[yi - 1], nf1)} → ${fmt(x.d.dpi[yi], nf1)}`],
      onClick: () => openDistrict(x.d),
    });
    barList($('#gainers'), gainers.map((x) => row(x, '')), max, 'No district climbed.');
    barList($('#losers'), losers.map((x) => row(x, 'is-loss')), max, 'No district fell.');
  }

  function renderQuality() {
    const a = D.audit;
    const total = (key) => a.reduce((acc, r) => acc + (r[key] || 0), 0);
    const before = total('errors_before');
    const fixed = before - total('errors_after');
    $('#quality-tiles').replaceChildren(
      tile('Rows read', nf0.format(total('rows_in')), `from ${a.length} source files`),
      tile('Rows loaded', nf0.format(total('rows_loaded')), 'after removing duplicates and bad rows'),
      tile('Error rows fixed', nf0.format(fixed), before ? `${nf0.format((fixed / before) * 100)}% of the errors detected` : null));
    const num = (v) => ({ text: fmt(v, nf0), num: true });
    fillTable($('#audit-table'),
      ['Source file', { text: 'Rows read', num: true }, { text: 'Rows loaded', num: true },
        { text: 'Error rows before', num: true }, { text: 'Error rows after', num: true }],
      a.map((r) => [r.source, num(r.rows_in), num(r.rows_loaded), num(r.errors_before), num(r.errors_after)]));
  }

  function renderMethod() {
    const pct = (w) => `${Math.round(w * 100)}%`;
    const bar = $('#weights');
    bar.setAttribute('aria-label', `Indicator weights: ${D.indicators.map((x) => `${x.label} ${pct(x.weight)}`).join(', ')}`);
    bar.replaceChildren(...D.indicators.map((x, i) => {
      const part = h('span', { class: `c${i + 1}${i === 3 ? ' dark-ink' : ''}`, text: pct(x.weight) });
      part.style.flex = `${x.weight} 0 0`;
      attachTip(part, [x.label, `${pct(x.weight)} of the score`, `Measured as ${x.unit}`]);
      return part;
    }));
    $('#weights-legend').replaceChildren(...D.indicators.map((x, i) =>
      h('li', {}, h('i', { class: `c${i + 1}` }), x.label)));
    fillTable($('#weights-table'), ['Indicator', 'Measured as', { text: 'Weight', num: true }],
      D.indicators.map((x) => [x.label, x.unit, { text: pct(x.weight), num: true }]));
  }

  // ---------------------------------------------------------------- district dialog
  const dialog = $('#district-dialog');

  function openDistrict(d) {
    const yi = S.yi;
    hideTip();
    $('#dlg-title').textContent = d.name;
    $('#dlg-sub').textContent = `${d.state} · figures for ${YEARS[yi]}`;
    $('#dlg-tiles').replaceChildren(
      tile('Score', fmt(d.dpi[yi], nf1)),
      tile('National rank', fmt(d.rank[yi], nf0)),
      tile('State rank', fmt(d.srank[yi], nf0)),
      tile('Population', indianCount(d.pop)),
      tile('Literacy', d.lit == null ? DASH : `${nf1.format(d.lit)}%`),
      tile('Urban share', d.urban == null ? DASH : `${nf1.format(d.urban)}%`));
    const num = (v, f) => ({ text: fmt(v, f), num: true });
    fillTable($('#dlg-table'),
      ['Year', { text: 'Score', num: true }, { text: 'National rank', num: true }, { text: 'State rank', num: true },
        { text: 'UPI ₹ per person', num: true }, { text: 'Broadband per 100', num: true },
        { text: 'GST per 1,000', num: true }, { text: 'e-Gov per person', num: true }],
      YEARS.map((year, i) => [String(year), num(d.dpi[i], nf1), num(d.rank[i], nf0), num(d.srank[i], nf0),
        num(d.upi[i], nf0), num(d.bb[i], nf1), num(d.gst[i], nf1), num(d.egov[i], nf2)]));

    dialog.showModal();
    dialog.append(tip);   // a modal dialog covers the page, so the tooltip must live inside it
    lineChart($('#dlg-chart'), {
      values: d.dpi,
      height: 200,
      markers: true,
      label: `Line chart of the score for ${d.name}, ${YEARS[0]} to ${YEARS[YEARS.length - 1]}. The table below lists every value.`,
      xTicks: YEARS.map((year, i) => ({ i, label: String(year) })),
      yTick: (v) => nf0.format(v),
      tip: (i) => [String(YEARS[i]), `Score ${fmt(d.dpi[i], nf1)}`, `National rank ${fmt(d.rank[i], nf0)}`],
    });
  }

  dialog.addEventListener('close', () => { hideTip(); document.body.append(tip); });
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });   // click on the backdrop

  // ---------------------------------------------------------------- start
  function render() {
    hideTip();
    renderFilters();
    renderOverview();
    renderRankings();
    renderStates();
    renderMovers();
  }

  async function start() {
    const status = $('#status');
    try {
      const response = await fetch('data/dashboard.json');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      D = await response.json();
    } catch (err) {
      status.textContent = 'Could not load data/dashboard.json. Run ./run_pipeline.sh to create it, then reload.';
      console.error(err);
      return;
    }
    YEARS = D.meta.years;
    S.yi = YEARS.length - 1;
    D.districts.forEach((d) => { d.search = `${d.name} ${d.state}`.toLowerCase(); });

    const select = $('#state-select');
    [...new Set(D.districts.map((d) => d.state))].sort()
      .forEach((name) => select.append(h('option', { value: name, text: name })));
    select.addEventListener('change', () => setState({ state: select.value }));
    $('#search').addEventListener('input', (e) => { S.q = e.target.value; S.page = 0; renderRankings(); });
    $('#prev-page').addEventListener('click', () => { S.page -= 1; renderRankings(); });
    $('#next-page').addEventListener('click', () => { S.page += 1; renderRankings(); });

    $('#generated').textContent = `Data generated ${D.meta.generated_at}.`;
    status.hidden = true;
    $('#app').hidden = false;
    renderQuality();
    renderMethod();
    render();
  }

  start();
})();
