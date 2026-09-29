'use strict';

/* 假设配色：最多 8 个“排除一条读数”的假设，颜色与假设条/图例一致 */
const PALETTE = [
  { solid: '#2563eb', fill: 'rgba(37,99,235,0.25)' },
  { solid: '#16a34a', fill: 'rgba(22,163,74,0.25)' },
  { solid: '#ea580c', fill: 'rgba(234,88,12,0.25)' },
  { solid: '#9333ea', fill: 'rgba(147,51,234,0.25)' },
  { solid: '#0891b2', fill: 'rgba(8,145,178,0.25)' },
  { solid: '#db2777', fill: 'rgba(219,39,119,0.25)' },
  { solid: '#a16207', fill: 'rgba(161,98,7,0.28)' },
  { solid: '#475569', fill: 'rgba(71,85,105,0.25)' },
];

const state = {
  result: null,
  focus: null,       // 聚焦查看的假设下标；null 表示全部叠加
  reqSeq: 0,
  timer: null,
};

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const keyOf = (x, y) => `${x},${y}`;

/* ---------------- 信标录入行 ---------------- */

const DEFAULT_BEACONS = [
  { id: 'A', x: 2, y: 2, dmin: 3, dmax: 5 },
  { id: 'B', x: 8, y: 1, dmin: 4, dmax: 6 },
  { id: 'C', x: 6, y: 8, dmin: 3, dmax: 5 },
];

function addBeaconRow(data) {
  const rows = $('#beacon-rows');
  const row = el('div', 'beacon-row');
  row.dataset.row = rows.children.length;

  const defs = [
    ['id', 'text', 'ID'],
    ['x', 'number', 'x'],
    ['y', 'number', 'y'],
    ['dmin', 'number', '下界'],
    ['dmax', 'number', '上界'],
  ];
  defs.forEach(([field, type, ph]) => {
    const input = el('input');
    input.type = type;
    input.dataset.field = field;
    input.placeholder = ph;
    if (type === 'number') {
      input.step = '1';
      if (field === 'x' || field === 'y') input.min = '0';
      else input.min = '0';
    }
    if (data && data[field] !== undefined) input.value = data[field];
    row.appendChild(input);
  });

  const removeBtn = el('button', 'btn-remove', '×');
  removeBtn.type = 'button';
  removeBtn.dataset.remove = '1';
  removeBtn.title = '删除该信标';
  row.appendChild(removeBtn);

  rows.appendChild(row);
  syncRowControls();
}

function reindexRows() {
  [...$('#beacon-rows').children].forEach((row, i) => { row.dataset.row = i; });
  syncRowControls();
}

function syncRowControls() {
  const count = $('#beacon-rows').children.length;
  $('#btn-add').disabled = count >= 8;
  [...$('#beacon-rows').querySelectorAll('[data-remove]')].forEach((btn) => {
    btn.disabled = count <= 3;
  });
}

/* ---------------- 读取表单与错误展示 ---------------- */

function collectPayload() {
  const beacons = [...$('#beacon-rows').children].map((row) => {
    const get = (field) => row.querySelector(`[data-field="${field}"]`).value;
    return {
      id: get('id'),
      x: get('x'),
      y: get('y'),
      dmin: get('dmin'),
      dmax: get('dmax'),
    };
  });
  return { n: $('#input-n').value, beacons };
}

function clearInvalidMarks() {
  document.querySelectorAll('input.invalid').forEach((i) => i.classList.remove('invalid'));
  document.querySelectorAll('.cell-error').forEach((p) => p.remove());
  document.querySelectorAll('[data-error]').forEach((p) => { p.hidden = true; p.textContent = ''; });
  const summary = $('#error-summary');
  summary.hidden = true;
  summary.querySelector('ul').replaceChildren();
}

function showErrors(errors) {
  clearInvalidMarks();
  const list = $('#error-summary').querySelector('ul');

  Object.entries(errors).forEach(([key, message]) => {
    const li = el('li', null, key === '_' ? message : `${errorTargetName(key)}：${message}`);
    list.appendChild(li);

    if (key === 'n') {
      $('#input-n').classList.add('invalid');
      const p = document.querySelector('[data-error="n"]');
      p.textContent = message;
      p.hidden = false;
    } else if (key === 'beacons') {
      const p = document.querySelector('[data-error="beacons"]');
      p.textContent = message;
      p.hidden = false;
    } else {
      const m = key.match(/^beacons\.(\d+)(?:\.(id|x|y|dmin|dmax))?$/);
      if (m) {
        const row = $('#beacon-rows').children[Number(m[1])];
        if (!row) return;
        if (m[2]) {
          row.querySelector(`[data-field="${m[2]}"]`).classList.add('invalid');
        }
        const p = el('p', 'cell-error', message);
        row.appendChild(p);
      }
    }
  });
  $('#error-summary').hidden = false;
}

function errorTargetName(key) {
  const m = key.match(/^beacons\.(\d+)(?:\.(id|x|y|dmin|dmax))?$/);
  if (!m) return '输入';
  const fieldNames = { id: 'ID', x: 'x 坐标', y: 'y 坐标', dmin: '距离下界', dmax: '距离上界' };
  const who = `第 ${Number(m[1]) + 1} 个信标`;
  return m[2] ? `${who}的${fieldNames[m[2]]}` : who;
}

/* ---------------- 计算调度（修改即作废旧结果） ---------------- */

function markStale() {
  state.focus = null;
  if (state.result) $('#stale-overlay').hidden = false;
}

function scheduleCompute() {
  markStale();
  clearTimeout(state.timer);
  state.timer = setTimeout(compute, 300);
}

async function compute() {
  const seq = ++state.reqSeq;
  const payload = collectPayload();

  if (state.result) $('#stale-overlay').hidden = false;

  let data;
  try {
    const resp = await fetch('/api/locate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    data = await resp.json();
    if (!resp.ok) throw { status: resp.status, body: data };
  } catch (err) {
    if (seq !== state.reqSeq) return; // 已有更新的请求，丢弃过期响应
    clearInvalidMarks();
    if (err && err.status === 422) {
      showErrors(err.body.detail || {});
      setBanner('error', '输入有误，已停止计算。请按左侧提示修正读数，修正后会自动重算。');
      state.result = null;
      renderEmptyBoard();
    } else {
      setBanner('error', `计算请求失败（${err && err.status ? err.status : '网络错误'}），请确认服务正在运行。`);
    }
    $('#stale-overlay').hidden = true;
    return;
  }

  if (seq !== state.reqSeq) return;
  clearInvalidMarks();
  state.result = data;
  state.focus = null;
  $('#stale-overlay').hidden = true;
  renderResult();
}

/* ---------------- 状态条与假设条 ---------------- */

function setBanner(kind, html) {
  const banner = $('#status-banner');
  banner.className = `banner banner-${kind}`;
  banner.innerHTML = html;
}

function hypothesisTitle(h) {
  if (h.excludedIndex === null || h.excludedIndex === undefined) {
    return '全部读数一致';
  }
  return `假设 H${h.excludedIndex + 1}：排除信标「${escapeHtml(h.excludedId)}」（第 ${h.excludedIndex + 1} 条读数）`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function renderBanner() {
  const { status, beacons, hypotheses } = state.result;
  if (status === 'located') {
    const h = hypotheses[0];
    setBanner(
      'ok',
      `定位成功：全部 <b>${beacons.length}</b> 条读数一致，共 <b>${h.pointCount}</b> 个网格点，` +
      `按四邻接构成 <b>${h.regionCount}</b> 个搜索区域。`,
    );
  } else if (status === 'ambiguous_excluded') {
    const totalPoints = hypotheses.reduce((s, h) => s + h.pointCount, 0);
    setBanner(
      'warn',
      `全部 <b>${beacons.length}</b> 条读数没有共同允许的点。依次排除一条读数后，` +
      `<b>${hypotheses.length}</b> 个假设成立（共尝试 ${beacons.length} 种排除），` +
      `合计 ${totalPoints} 个候选点。不同假设的区域只做颜色叠加，<b>绝不合并为同一片位置</b>；` +
      `点击下方假设条可单独查看。`,
    );
  } else {
    setBanner(
      'bad',
      `<b>无法定位。</b>全部读数不存在共同允许的网格点；` +
      `且分别排除任意一条读数后，其余读数仍然没有共同允许的点。`,
    );
  }
}

function renderHypBar() {
  const bar = $('#hyp-bar');
  bar.replaceChildren();
  const { status, hypotheses } = state.result;

  if (status === 'located') {
    const chip = el('div', 'hyp-card active');
    chip.style.setProperty('--hyp', PALETTE[0].solid);
    chip.innerHTML = `<div class="hyp-title">全部 ${state.result.beacons.length} 条读数一致</div>` +
      `<div class="hyp-sub">${hypotheses[0].regionCount} 个区域 · ${hypotheses[0].pointCount} 个点</div>`;
    chip.style.cursor = 'default';
    bar.appendChild(chip);
    return;
  }

  if (status !== 'ambiguous_excluded') return;

  hypotheses.forEach((h, i) => {
    const card = el('div', 'hyp-card' + (state.focus === i ? ' active' : ''));
    card.style.setProperty('--hyp', PALETTE[i].solid);

    const btn = el('button', 'hyp-select');
    btn.type = 'button';
    btn.style.all = 'unset';
    btn.style.cursor = 'pointer';
    btn.innerHTML =
      `<div class="hyp-title">排除「${escapeHtml(h.excludedId)}」· 假设 H${h.excludedIndex + 1}</div>` +
      `<div class="hyp-sub">${h.regionCount} 个区域 · ${h.pointCount} 个点</div>`;
    btn.addEventListener('click', () => {
      state.focus = state.focus === i ? null : i;
      renderResult();
    });
    card.appendChild(btn);

    const details = el('details', 'region-details');
    const summary = el('summary', null, `查看 ${h.regionCount} 个区域的点坐标`);
    details.appendChild(summary);
    h.regions.forEach((region, ri) => {
      const p = el('p', 'point-list');
      p.textContent = `区域 ${ri + 1}（${region.length} 点）：` +
        region.map((pt) => `(${pt.x},${pt.y})`).join('，');
      details.appendChild(p);
    });
    card.appendChild(details);

    bar.appendChild(card);
  });

  if (hypotheses.length > 1) {
    const clear = el('button', 'hyp-clear', state.focus === null ? '（当前：全部叠加）' : '显示全部叠加');
    clear.type = 'button';
    clear.disabled = state.focus === null;
    clear.addEventListener('click', () => { state.focus = null; renderResult(); });
    bar.appendChild(clear);
  }
}

/* ---------------- 网格绘制 ---------------- */

function renderEmptyBoard() {
  const board = $('#board');
  board.replaceChildren();
  $('#legend').replaceChildren();
  $('#hyp-bar').replaceChildren();
  $('#board-scroll').setAttribute('inert', '');
}

function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function conicSectorGradient(memberHyps) {
  /* 每个假设固定占据 360°/8 的扇区，保证同一颜色在各格位置一致 */
  const stops = memberHyps.map((hi) => {
    const start = hi * 45 + 2;
    const end = (hi + 1) * 45 - 2;
    return `${hexToRgba(PALETTE[hi].solid, 0.9)} ${start}deg ${end}deg`;
  });
  return `conic-gradient(from 0deg, ${stops.join(', ')})`;
}

function renderResult() {
  renderBanner();
  renderHypBar();
  renderBoard();
  renderLegend();
}

function renderBoard() {
  const { n, beacons, status, hypotheses } = state.result;
  const boardScroll = $('#board-scroll');
  boardScroll.removeAttribute('inert');

  const board = $('#board');
  board.replaceChildren();
  board.style.gridTemplateColumns = `24px repeat(${n + 1}, 28px)`;

  /* 本次要画的假设：located / 聚焦时只画一个；排除态默认全部叠加 */
  const focused = status === 'located' ? 0 : state.focus;
  const shownHyps = focused === null ? hypotheses.map((_, i) => i) : [focused];
  const outlineMode = focused !== null; // 单假设时给区域描边、加区域编号

  // cell -> [{hyp, region}]
  const membership = new Map();
  const hypPointSets = new Map();

  shownHyps.forEach((hi) => {
    const pointSet = new Set();
    hypotheses[hi].regions.forEach((region, ri) => {
      region.forEach((pt) => {
        pointSet.add(keyOf(pt.x, pt.y));
        if (!membership.has(keyOf(pt.x, pt.y))) membership.set(keyOf(pt.x, pt.y), []);
        membership.get(keyOf(pt.x, pt.y)).push({ hyp: hi, region: ri });
      });
    });
    hypPointSets.set(hi, pointSet);
  });

  // 顶行坐标（x 轴）
  const head = el('div', 'grid-row');
  head.appendChild(el('span', 'axis-corner'));
  for (let x = 0; x <= n; x++) head.appendChild(el('span', 'axis-x', String(x)));
  board.appendChild(head);

  const cellEls = {};
  for (let y = n; y >= 0; y--) {
    const row = el('div', 'grid-row');
    row.appendChild(el('span', 'axis-y', String(y)));
    for (let x = 0; x <= n; x++) {
      const cell = el('div', 'cell');
      cell.dataset.x = x;
      cell.dataset.y = y;
      cellEls[keyOf(x, y)] = cell;

      const members = membership.get(keyOf(x, y));
      if (members && members.length === 1) {
        const hi = members[0].hyp;
        cell.classList.add('covered');
        cell.style.setProperty('--cover', PALETTE[hi].fill);
        cell.title = `网格点 (${x},${y})\n${hypothesisTitle(hypotheses[hi])}\n区域 ${members[0].region + 1}`;
      } else if (members && members.length > 1) {
        cell.classList.add('multi');
        cell.style.setProperty('--multi-bg', conicSectorGradient(members.map((m) => m.hyp)));
        cell.title = `网格点 (${x},${y})\n同时属于：` +
          members.map((m) => `H${hypotheses[m.hyp].excludedIndex + 1}区域${m.region + 1}`).join('、') +
          '\n（不同假设叠加，未合并）';
      } else {
        cell.title = `网格点 (${x},${y})`;
      }

      row.appendChild(cell);
    }
    board.appendChild(row);
  }

  // 区域描边（四邻接边界）与区域编号，仅单假设视图
  if (outlineMode) {
    const hi = shownHyps[0];
    const pointSet = hypPointSets.get(hi);
    const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    const shadowBySide = {
      right: `inset -2px 0 0 ${PALETTE[hi].solid}`,
      left: `inset 2px 0 0 ${PALETTE[hi].solid}`,
      top: `inset 0 2px 0 ${PALETTE[hi].solid}`,
      bottom: `inset 0 -2px 0 ${PALETTE[hi].solid}`,
    };
    pointSet.forEach((k) => {
      const [x, y] = k.split(',').map(Number);
      const cell = cellEls[k];
      const shadows = [];
      if (!pointSet.has(keyOf(x + 1, y))) shadows.push(shadowBySide.right);
      if (!pointSet.has(keyOf(x - 1, y))) shadows.push(shadowBySide.left);
      if (!pointSet.has(keyOf(x, y + 1))) shadows.push(shadowBySide.top);
      if (!pointSet.has(keyOf(x, y - 1))) shadows.push(shadowBySide.bottom);
      if (shadows.length) {
        cell.classList.add('outlined');
        cell.style.setProperty('--shadows', shadows.join(', '));
      }
    });

    const h = hypotheses[hi];
    if (h.regionCount > 1) {
      h.regions.forEach((region, ri) => {
        const first = region[0]; // 后端已按最上、最左排序
        const badge = el('span', 'badge', String(ri + 1));
        badge.style.setProperty('--hyp', PALETTE[hi].solid);
        cellEls[keyOf(first.x, first.y)].appendChild(badge);
      });
    }
  }

  // 信标标记（最后绘制，压在区域之上）
  const excludedId = focused !== null && hypotheses[focused].excludedId !== undefined
    ? hypotheses[focused].excludedId : null;
  beacons.forEach((b) => {
    const cell = cellEls[keyOf(b.x, b.y)];
    if (!cell) return;
    const marker = el('div', 'beacon' + (b.id === excludedId ? ' excluded' : ''));
    const label = el('span', 'beacon-id', b.id);
    marker.appendChild(label);
    cell.appendChild(marker);

    const lines = [
      `信标「${b.id}」@ (${b.x},${b.y})，读数区间 [${b.dmin}, ${b.dmax}]`,
    ];
    if (b.id === excludedId) lines.push('（本假设中该读数被排除）');
    const membersHere = membership.get(keyOf(b.x, b.y));
    if (membersHere) {
      lines.push('同时是 ' + membersHere
        .map((m) => `H${hypotheses[m.hyp].excludedIndex + 1}区域${m.region + 1}`)
        .join('、') + ' 的候选点（未合并）');
    }
    cell.title = lines.join('\n');
  });
}

/* ---------------- 图例 ---------------- */

function renderLegend() {
  const legend = $('#legend');
  legend.replaceChildren();
  const { status, hypotheses } = state.result;

  const beaconKey = el('span', null);
  beaconKey.innerHTML = '<span class="beacon-key"></span>信标';
  legend.appendChild(beaconKey);

  if (status === 'located') {
    const item = el('span', null);
    item.innerHTML = `<span class="swatch" style="background:${PALETTE[0].fill}"></span>` +
      `候选搜索区域（全部读数一致，${hypotheses[0].regionCount} 个四邻接区域）`;
    legend.appendChild(item);
    return;
  }

  if (status === 'ambiguous_excluded') {
    if (state.focus === null) {
      hypotheses.forEach((h, i) => {
        const item = el('span', null);
        item.innerHTML = `<span class="swatch" style="background:${PALETTE[i].solid}"></span>` +
          `H${h.excludedIndex + 1}：排除「${escapeHtml(h.excludedId)}」`;
        legend.appendChild(item);
      });
      const overlap = el('span', null, '斜分色块 = 多假设候选点叠加（未合并）');
      legend.appendChild(overlap);
    } else {
      const h = hypotheses[state.focus];
      const item = el('span', null);
      item.innerHTML = `<span class="swatch" style="background:${PALETTE[state.focus].fill}"></span>` +
        `${hypothesisTitle(h)}（${h.regionCount} 个区域）`;
      legend.appendChild(item);
      const cross = el('span', null, '✕ 红叉 = 被排除读数的信标');
      legend.appendChild(cross);
    }
  }
}

/* ---------------- 事件绑定与初始化 ---------------- */

$('#btn-add').addEventListener('click', () => addBeaconRow());

$('#beacon-rows').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-remove]');
  if (!btn || btn.disabled) return;
  btn.closest('.beacon-row').remove();
  reindexRows();
  scheduleCompute();
});

document.addEventListener('input', (e) => {
  if (e.target.closest('#beacon-rows, #input-n')) scheduleCompute();
});

DEFAULT_BEACONS.forEach((b) => addBeaconRow(b));
renderEmptyBoard();
setBanner('info', '正在计算…');
compute();
