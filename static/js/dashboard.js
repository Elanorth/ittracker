// ══════════════════════════════════════════════════════════
//  dashboard.js — Dashboard (v5.59, ESM Faz 4e-2a + 4e-2b)
//
//  app.js'ten çıkarılıyor:
//    4e-2a: Chart.js grafikleri (kategori pie, firma bar, aktivite bar, haftalık line)
//    4e-2b: BUGÜNÜN GÖREVLERİ task-list (filterTasks/setDashPage/renderDashboardTaskList)
//           + rutin özet (renderDashUpcoming)
//  Kalan (4e-2c): renderDashboard/KPI/loadSlaKpi/firma-şeridi.
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//
//  Bağımlılıklar: _chartTheme/_cssVar/_centerTextPlugin/escapeHtml (utils import),
//  state (import), taskTiming/taskRow (tasks.js import — KANONİK satır-render).
//  Chart (global, chart.js <script>), FIRMS/showTasksWithCat/showTasksWithFirm
//  app.js klasik → bare global (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
import { _chartTheme, _cssVar, _centerTextPlugin, escapeHtml } from './utils.js';
import { state } from './state.js';
import { taskTiming, taskRow } from './tasks.js'; // KANONİK satır-render (ESM Faz 4e-1)

// Chart nesneleri modül-local (yalnız aşağıdaki render fonksiyonları kullanır).
let _catChart = null, _firmChart = null, _activityChart = null, _weeklyChart = null;
function _destroyDashCharts() {
  [_catChart, _firmChart, _activityChart, _weeklyChart].forEach(c => { try { c && c.destroy(); } catch (e) {} });
  _catChart = _firmChart = _activityChart = _weeklyChart = null;
}

const _CAT_META = {
  routine: { label: 'Rutin', v: '--accent' }, support: { label: 'Destek', v: '--accent3' },
  infra: { label: 'Altyapı', v: '--accent2' }, backup: { label: 'Backup', v: '--gold' },
  project: { label: 'Proje', v: '--green' }, other: { label: 'Diğer', v: '--surface3' }
};

export function renderCategoryPie() {
  const wrap = document.getElementById('dash-pie-wrap');
  if (!wrap || typeof Chart === 'undefined') return;
  const counts = {};
  state.tasks.forEach(t => { const k = (t.cat && _CAT_META[t.cat]) ? t.cat : 'other'; counts[k] = (counts[k] || 0) + 1; });
  const total = state.tasks.length;
  const rate = total ? Math.round(state.tasks.filter(t => t.done).length / total * 100) : 0;
  if (!total) { if (_catChart) { _catChart.destroy(); _catChart = null; } wrap.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:12px;padding:30px 0">Henüz görev yok</div>'; return; }
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const cats = entries.map(([c]) => c);
  wrap.innerHTML = '<div style="position:relative;height:190px"><canvas id="cat-canvas"></canvas></div>';
  const th = _chartTheme();
  if (_catChart) _catChart.destroy();
  _catChart = new Chart(document.getElementById('cat-canvas'), {
    type: 'doughnut',
    data: {
      labels: entries.map(([c]) => _CAT_META[c].label),
      datasets: [{ data: entries.map(([, n]) => n), backgroundColor: entries.map(([c]) => _cssVar(_CAT_META[c].v)), borderWidth: 0, hoverOffset: 6 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '66%',
      onClick: (e, els) => { if (els.length) showTasksWithCat(cats[els[0].index]); },
      plugins: {
        legend: { position: 'right', labels: { color: th.muted, boxWidth: 10, font: { size: 11 } }, onClick: (e, item) => showTasksWithCat(cats[item.index]) },
        tooltip: { callbacks: { label: (c) => ` ${c.label}: ${c.parsed} (${Math.round(c.parsed / total * 100)}%)` } },
        centerText: { text: rate + '%', sub: 'tamamlandı' }
      }
    },
    plugins: [_centerTextPlugin]
  });
}

// v4.7→v5.33 — FİRMA DAĞILIMI: Chart.js yatay bar (tıkla → firma görevleri)
export function renderFirmBars() {
  const el = document.getElementById('dash-firm-bars');
  if (!el || typeof Chart === 'undefined') return;
  const firmMap = {};
  state.tasks.forEach(t => { const f = (t.firm && String(t.firm).trim()) || '—'; firmMap[f] = (firmMap[f] || 0) + 1; });
  const sorted = Object.entries(firmMap).sort((a, b) => b[1] - a[1]).slice(0, 6);
  if (!sorted.length) { if (_firmChart) { _firmChart.destroy(); _firmChart = null; } el.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px 0">Henüz görev yok</div>'; return; }
  const names = sorted.map(([n]) => (FIRMS[n] && FIRMS[n].label) || n);
  const rawNames = sorted.map(([n]) => n);
  const palette = ['--accent', '--gold', '--accent3', '--accent2', '--green', '--surface3'];
  el.innerHTML = '<div style="position:relative;height:' + Math.max(120, sorted.length * 34) + 'px"><canvas id="firm-canvas"></canvas></div>';
  const th = _chartTheme();
  if (_firmChart) _firmChart.destroy();
  _firmChart = new Chart(document.getElementById('firm-canvas'), {
    type: 'bar',
    data: { labels: names, datasets: [{ data: sorted.map(([, n]) => n), backgroundColor: sorted.map((_, i) => _cssVar(palette[i % palette.length])), borderRadius: 4, barThickness: 18 }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      onClick: (e, els) => { if (els.length) showTasksWithFirm(rawNames[els[0].index]); },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${c.parsed.x} görev` } } },
      scales: {
        x: { beginAtZero: true, ticks: { color: th.muted, precision: 0 }, grid: { color: th.grid } },
        y: { ticks: { color: th.text, font: { size: 11 } }, grid: { display: false } }
      }
    }
  });
}

export function renderBars() {
  // Son 5 gün: o gün AÇILAN (gri) vs o gün TAMAMLANAN (renkli) görev sayısı.
  // Eski sürüm yalnızca startDate'e bakıyordu — rutinler sadece oluşturuldukları
  // gün göründüğü için grafik yanıltıcıydı. Tamamlanma artık completed_at'ten
  // bağımsız sayılır (rutinlerde to_dict occurrence completed_at'ini döner).
  const barEl = document.getElementById('bar-chart');
  if (!barEl || typeof Chart === 'undefined') return;
  const days = [];
  for (let i = 4; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    const ds = d.toISOString().split('T')[0];
    const created   = state.tasks.filter(t => t.startDate === ds).length;
    const completed = state.tasks.filter(t => t.completed_at && t.completed_at.substring(0, 10) === ds).length;
    days.push({ label: ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][d.getDay()], c: created, d: completed });
  }
  // v5.33 — inline-bar yerine Chart.js gruplu bar (açılan vs tamamlanan)
  const lblEl = document.getElementById('bar-chart-labels');
  if (lblEl) lblEl.innerHTML = '';  // eski etiket satırı Chart.js ekseninde
  barEl.innerHTML = '<div style="position:relative;height:150px"><canvas id="activity-canvas"></canvas></div>';
  const th = _chartTheme();
  if (_activityChart) _activityChart.destroy();
  _activityChart = new Chart(document.getElementById('activity-canvas'), {
    type: 'bar',
    data: {
      labels: days.map(d => d.label),
      datasets: [
        { label: 'Açılan', data: days.map(d => d.c), backgroundColor: _cssVar('--surface3'), borderRadius: 4 },
        { label: 'Tamamlanan', data: days.map(d => d.d), backgroundColor: _cssVar('--accent'), borderRadius: 4 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: th.muted, boxWidth: 10, font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: th.muted }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { color: th.muted, precision: 0 }, grid: { color: th.grid } }
      }
    }
  });
}

// v5.35 — HAFTALIK AKIŞ: açılan vs çözülen görev (Chart.js line)
// v5.36 — periyot seçici (8/12/26 hafta) + net akış özeti
let _weeklyWeeks = 8;
export function setWeeklyPeriod(weeks, btnEl) {
  if (weeks === _weeklyWeeks) return;
  _weeklyWeeks = weeks;
  document.querySelectorAll('#weekly-period-tabs .tab').forEach(t => {
    const isActive = t === btnEl;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  loadWeeklyTrend();
}
export async function loadWeeklyTrend() {
  const cv = document.getElementById('weekly-trend-chart');
  if (!cv || typeof Chart === 'undefined') return;
  try {
    const uParam = state.selectedUserId ? 'user_id=' + state.selectedUserId + '&' : '';
    const res = await fetch('/api/dashboard/weekly-trends?' + uParam + 'weeks=' + _weeklyWeeks);
    if (!res.ok) return;
    const d = await res.json();
    const th = _chartTheme();
    try { _weeklyChart && _weeklyChart.destroy(); } catch (e) {}
    _weeklyChart = new Chart(cv.getContext('2d'), {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [
          { label: 'Açılan', data: d.opened, borderColor: _cssVar('--accent3'), backgroundColor: 'transparent', tension: 0.3, pointRadius: 3, borderWidth: 2 },
          { label: 'Çözülen', data: d.resolved, borderColor: _cssVar('--green'), backgroundColor: 'transparent', tension: 0.3, pointRadius: 3, borderWidth: 2 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: th.text, boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: th.muted, font: { size: 10 } }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: th.muted, precision: 0, font: { size: 10 } }, grid: { color: th.grid } }
        }
      }
    });
    // Net akış özeti: toplam açılan / çözülen / net (açılan − çözülen)
    const sum = a => (a || []).reduce((x, y) => x + y, 0);
    const opened = sum(d.opened), resolved = sum(d.resolved), net = opened - resolved;
    const netColor = net > 0 ? 'var(--danger)' : net < 0 ? 'var(--green)' : 'var(--text-muted)';
    const netLabel = net > 0 ? `+${net} biriken` : net < 0 ? `${net} eriyen` : '±0 dengede';
    const sm = document.getElementById('weekly-trend-summary');
    if (sm) {
      sm.innerHTML = `Son ${_weeklyWeeks} hafta · Açılan <b style="color:var(--text)">${opened}</b> · ` +
        `Çözülen <b style="color:var(--text)">${resolved}</b> · Net <b style="color:${netColor}">${netLabel}</b>`;
    }
  } catch (e) { /* sessiz */ }
}

// ── ESM Faz 4e-2b: Dashboard task-list (BUGÜNÜN GÖREVLERİ) + rutin özet ──
// ══════════════════════════════════════════════════════════
//  DASHBOARD TASK LIST (sayfalı, 5'er)
// ══════════════════════════════════════════════════════════
const DASH_PAGE_SIZE = 5;

export function filterTasks(f) {
  state.currentFilter = f;
  state.dashPage = 0; // filtre değiştiğinde ilk sayfaya dön
  // Yalnızca durum tabs'ını güncelle (kategori tabs'ı dokunulmasın)
  document.querySelectorAll('#tab-all, #tab-open, #tab-done').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+f)?.classList.add('active');
  renderDashboardTaskList();
}

// v5.2 — Dashboard "Bugünün Görevleri" kategori filtresi (durum filtresiyle birlikte çalışır)
export function filterTasksByCat(cat) {
  state.currentCategoryFilter = cat;
  state.dashPage = 0;
  document.querySelectorAll('#today-cat-tabs .tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`#today-cat-tabs .tab[data-cat="${cat}"]`)?.classList.add('active');
  renderDashboardTaskList();
}

export function setDashPage(p) {
  state.dashPage = Math.max(0, p);
  renderDashboardTaskList();
}

// v4.7 — akıllı gruplama: geciken → bugün → yarın → ileri → tarihsiz → bitmiş
const DASH_GROUP_META = {
  overdue    : { label:'Geciken',        icon:'🔴', color:'var(--danger)' },
  today      : { label:'Bugün',          icon:'⚡', color:'var(--gold)' },
  tomorrow   : { label:'Yarın',          icon:'📅', color:'var(--accent2)' },
  upcoming   : { label:'İleri Tarih',    icon:'⏭', color:'var(--accent3)' },
  no_deadline: { label:'Tarihsiz',       icon:'—',  color:'var(--text-muted)' },
  done       : { label:'Tamamlandı',     icon:'✓',  color:'var(--green)' }
};
const DASH_GROUP_ORDER = ['overdue','today','tomorrow','upcoming','no_deadline','done'];

// v5.6 — Gruplama + sıralama KANONİK taskTiming()'den (tek kaynak).
function _dashGroupKey(t) { return taskTiming(t).group; }
function _dashSortKey(t)  { return taskTiming(t).sortKey; }

export function renderDashboardTaskList() {
  const body = document.getElementById('task-list-body');
  if (!body) return;
  let list = state.tasks;
  // Durum filtresi
  if (state.currentFilter === 'open') list = list.filter(t => !t.done);
  if (state.currentFilter === 'done') list = list.filter(t => t.done);
  // v5.2 — Kategori filtresi (durum filtresiyle çakışmayacak şekilde sonra uygulanır)
  if (state.currentCategoryFilter) list = list.filter(t => t.cat === state.currentCategoryFilter);
  if (!list.length) {
    const emptyMsg = state.currentCategoryFilter
      ? `Bu kategoride görev yok`
      : 'Görev yok';
    body.innerHTML = `<div style="padding:16px;font-size:12px;color:var(--text-muted);text-align:center">${emptyMsg}</div>`;
    return;
  }

  // Gruplara göre sırala (group order + group içinde saat hassasiyetinde — destek için SLA kalan süresi)
  list = [...list].sort((a, b) => {
    const ka = DASH_GROUP_ORDER.indexOf(_dashGroupKey(a));
    const kb = DASH_GROUP_ORDER.indexOf(_dashGroupKey(b));
    if (ka !== kb) return ka - kb;
    return _dashSortKey(a) - _dashSortKey(b);
  });

  const total = list.length;
  const pageCount = Math.ceil(total / DASH_PAGE_SIZE);
  if (state.dashPage >= pageCount) state.dashPage = pageCount - 1;
  const start = state.dashPage * DASH_PAGE_SIZE;
  const slice = list.slice(start, start + DASH_PAGE_SIZE);

  // Grup başlıkları ekleyerek render et (grup değiştiğinde ya da sayfa ilkinde)
  let lastGroup = null;
  let html = slice.map(t => {
    const g = _dashGroupKey(t);
    let prefix = '';
    if (g !== lastGroup) {
      const m = DASH_GROUP_META[g];
      prefix = `<div style="font-size:9px;color:${m.color};font-weight:700;letter-spacing:1.1px;text-transform:uppercase;padding:8px 4px 4px;display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--border);margin-top:${lastGroup?'8px':'0'}"><span>${m.icon}</span><span>${m.label}</span></div>`;
      lastGroup = g;
    }
    return prefix + taskRow(t);
  }).join('');

  if (pageCount > 1) {
    const prevDisabled = state.dashPage === 0 ? 'disabled' : '';
    const nextDisabled = state.dashPage >= pageCount - 1 ? 'disabled' : '';
    html += `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 6px 2px;border-top:1px solid var(--border);margin-top:auto">
        <div style="font-size:10px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">
          ${start+1}–${Math.min(start+DASH_PAGE_SIZE, total)} / ${total}
        </div>
        <div style="display:flex;gap:6px;align-items:center">
          <button class="btn btn-outline btn-sm" ${prevDisabled} style="padding:3px 10px;font-size:11px" onclick="setDashPage(${state.dashPage-1})">‹ Önceki</button>
          <span style="font-size:11px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">
            ${state.dashPage+1} / ${pageCount}
          </span>
          <button class="btn btn-outline btn-sm" ${nextDisabled} style="padding:3px 10px;font-size:11px" onclick="setDashPage(${state.dashPage+1})">Sonraki ›</button>
        </div>
      </div>`;
  }
  body.innerHTML = html;
}

// Rutin görev özeti (dashboard sağ kolon "yaklaşan/geciken rutinler")
export function renderDashUpcoming() {
  // v5.x — KANONİK taskTiming(): rutin gecikmesi donmuş deadline'dan değil
  // is_overdue/overdue_periods'tan gelir. Geciken önce (sortKey), sonra bekleyenler.
  const upcoming = state.tasks
    .filter(t => t.cat === 'routine' && !t.done)
    .sort((a, b) => {
      const ta = taskTiming(a), tb = taskTiming(b);
      const ga = ta.group === 'overdue' ? 0 : 1, gb = tb.group === 'overdue' ? 0 : 1;
      if (ga !== gb) return ga - gb;
      return ta.sortKey - tb.sortKey;
    })
    .slice(0, 4);
  const cnt = document.getElementById('dash-sched-count'); if (cnt) cnt.textContent = upcoming.length;
  const el = document.getElementById('dash-upcoming-list'); if (!el) return;
  if (!upcoming.length) { el.innerHTML = '<div style="padding:12px 0;font-size:12px;color:var(--text-muted);text-align:center">Hepsi zamanında 🎉</div>'; return; }
  el.innerHTML = upcoming.map(t => {
    const ti = taskTiming(t);
    const cls = ti.badgeClass || 'ok';
    const txt = ti.badgeText || (t.current_period_label ? `${t.current_period_label} bekliyor` : 'Bekliyor');
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px">
      <div style="flex:1;min-width:0"><div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(t.title)}</div><div style="font-size:10px;color:var(--text-muted)">${t.period} · ${escapeHtml(t.team||'')}</div></div>
      <div class="dl-badge ${cls}" style="margin-left:8px;flex-shrink:0">${txt}</div>
    </div>`;
  }).join('');
}
