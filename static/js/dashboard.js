// ══════════════════════════════════════════════════════════
//  dashboard.js — Dashboard (v5.60, ESM Faz 4e-2 TAMAM)
//
//  app.js'ten çıkarıldı (alt-adımlar):
//    4e-2a: Chart.js grafikleri (kategori pie, firma bar, aktivite bar, haftalık line)
//    4e-2b: BUGÜNÜN GÖREVLERİ task-list (filterTasks/setDashPage/renderDashboardTaskList)
//           + rutin özet (renderDashUpcoming)
//    4e-2c: renderDashboard orchestrator + KPI/trend (loadKpiTrends) + drill-down
//           (kpiJump/showTasksWith*/addTaskFromTasksView) + updateSupportNavBadge
//           + loadSlaKpi + firma şeridi (loadDirectorFirmsStrip/onFirmStripClick)
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//
//  Bağımlılıklar: _chartTheme/_cssVar/_centerTextPlugin/escapeHtml (utils import),
//  state (import), taskTiming/taskRow (tasks.js import — KANONİK satır-render).
//  Bare global (app.js klasik): Chart, FIRMS, showPage, onCatChange, onFirmUserChange
//  (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
import { _chartTheme, _cssVar, _centerTextPlugin, escapeHtml } from './utils.js';
import { state } from './state.js';
import { taskTiming, taskRow } from './tasks.js'; // KANONİK satır-render (ESM Faz 4e-1)
import { onClick } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — dashboard/topbar aksiyonları (inline onclick → data-click)
onClick('kpiJump',             el => kpiJump(el.dataset.kind));
onClick('filterTasks',        el => filterTasks(el.dataset.filter));
onClick('filterTasksByCat',   el => filterTasksByCat(el.dataset.cat));
onClick('showTasksWithCat',   el => showTasksWithCat(el.dataset.cat));
onClick('addTaskFromTasksView', () => addTaskFromTasksView());
onClick('setDashPage', el => setDashPage(+el.dataset.page)); // BUGÜNÜN GÖREVLERİ pager (generated)

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
          <button class="btn btn-outline btn-sm" ${prevDisabled} style="padding:3px 10px;font-size:11px" data-click="setDashPage" data-page="${state.dashPage-1}">‹ Önceki</button>
          <span style="font-size:11px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">
            ${state.dashPage+1} / ${pageCount}
          </span>
          <button class="btn btn-outline btn-sm" ${nextDisabled} style="padding:3px 10px;font-size:11px" data-click="setDashPage" data-page="${state.dashPage+1}">Sonraki ›</button>
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

// ── ESM Faz 4e-2c: Dashboard orchestrator + KPI/trend + SLA + firma şeridi ──
// ══════════════════════════════════════════════════════════
//  DASHBOARD RENDER
// ══════════════════════════════════════════════════════════
export function renderDashboard() {
  const now = new Date();
  const el = document.getElementById('dash-name');
  // v4.2 — başka kullanıcıyı görüntülüyorsak onun adını göster
  let displayName = (state.currentUser.full_name || '').split(' ')[0] || 'Hoş Geldiniz';
  if (state.selectedUserId) {
    const u = state.firmUsers.find(u => u.id === state.selectedUserId);
    if (u) displayName = `👁 ${u.full_name}`;
  }
  if (el) el.textContent = displayName;

  // Dinamik selamlama + tarih altyazısı
  const GUN_TR = ['Pazar','Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi'];
  const AY_TR  = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  const hr = now.getHours();
  const greet = (hr < 5) ? 'İyi geceler' : (hr < 12) ? 'Günaydın' : (hr < 18) ? 'İyi günler' : 'İyi akşamlar';
  const gEl = document.getElementById('dash-greeting');
  if (gEl) gEl.textContent = greet;

  // "Perşembe · 20 Nisan 2026 · Nisan ayında 11 gün kaldı"
  const gunAdi = GUN_TR[now.getDay()];
  const ayAdi  = AY_TR[now.getMonth()];
  const tarihStr = `${gunAdi} · ${now.getDate()} ${ayAdi} ${now.getFullYear()}`;
  // Ay sonuna kalan gün
  const ayLastDay = new Date(now.getFullYear(), now.getMonth()+1, 0).getDate();
  const kalanGun = ayLastDay - now.getDate();
  const aySonu = (kalanGun === 0)
    ? `${ayAdi} ayının son günü`
    : `${ayAdi} ayında ${kalanGun} gün kaldı`;
  const subEl = document.getElementById('dash-subtitle');
  if (subEl) subEl.textContent = `${tarihStr} · ${aySonu}`;

  const total   = state.tasks.length;
  const done    = state.tasks.filter(t => t.done).length;
  const pending = state.tasks.filter(t => !t.done).length;
  // v5.x — "Geciken" KANONİK taskTiming()'den (rutinlerde donmuş deadline değil
  // is_overdue; destek için SLA). Böylece KPI sayısı, alttaki "Geciken" grubuyla tutar.
  const late    = state.tasks.filter(t => taskTiming(t).group === 'overdue').length;
  const backups = state.tasks.filter(t => t.cat === 'backup').length;
  const rate    = total ? Math.round(done/total*100) : 0;

  // KPI kartları — dinamik güncelle (v5.0: backend'den gelen gerçek trend)
  const kpiEls = document.querySelectorAll('.kpi-value');
  const kpiSubs = document.querySelectorAll('.kpi-sub');

  if (kpiEls[0]) { kpiEls[0].textContent = total; if(kpiSubs[0]) kpiSubs[0].textContent = 'Bu dönem'; }
  if (kpiEls[1]) { kpiEls[1].textContent = done;  if(kpiSubs[1]) kpiSubs[1].textContent = `%${rate} oran`; }
  if (kpiEls[2]) { kpiEls[2].textContent = pending; if(kpiSubs[2]) kpiSubs[2].textContent = pending ? 'Aktif görev' : 'Tamamlandı'; }
  if (kpiEls[3]) { kpiEls[3].textContent = late; if(kpiSubs[3]) kpiSubs[3].textContent = late ? 'Müdahale gerek' : 'Temiz'; }
  if (kpiEls[4]) { kpiEls[4].textContent = backups; }

  // v5.0 — Gerçek trend backend'den gelir (asenkron — KPI yenilendikçe rozet eklenir)
  loadKpiTrends();

  state.dashPage = 0; // dashboard açılışında sayfayı sıfırla
  renderDashboardTaskList();
  renderDashUpcoming();
  renderBars();
  loadWeeklyTrend();
  // v4.7 — dinamik pie chart + firma dağılımı
  renderCategoryPie();
  renderFirmBars();
  // v4.5 — SLA KPI kartları
  loadSlaKpi();
  // v4.9 firma şeridi v5.0'da kaldırıldı — yerine /managed-firms sayfası geldi.
}

// v5.0 — Gerçek trend rozetleri (backend /api/dashboard/trends)
async function loadKpiTrends() {
  try {
    const url = '/api/dashboard/trends' + (state.selectedUserId ? `?user_id=${state.selectedUserId}` : '');
    const r = await fetch(url);
    if (!r.ok) return;
    const data = await r.json();
    const subs = document.querySelectorAll('.kpi-sub');
    const fmt = (n, suffix='') => {
      if (n === 0) return `<span class="kpi-trend flat">◆ değişim yok${suffix}</span>`;
      const cls = n > 0 ? 'up' : 'down';
      const arr = n > 0 ? '▲' : '▼';
      return `<span class="kpi-trend ${cls}">${arr} ${n>0?'+':''}${n}${suffix}</span>`;
    };
    // İyi/kötü algısı: total/done/rate için artı = iyi (yeşil); overdue için artı = kötü (kırmızı)
    const fmtInverse = (n, suffix='') => {
      if (n === 0) return `<span class="kpi-trend flat">◆ değişim yok${suffix}</span>`;
      const cls = n > 0 ? 'down' : 'up';   // overdue arttıysa kırmızı
      const arr = n > 0 ? '▲' : '▼';
      return `<span class="kpi-trend ${cls}">${arr} ${n>0?'+':''}${n}${suffix}</span>`;
    };
    const d = data.delta;
    if (subs[0]) subs[0].innerHTML = `Bu dönem ${fmt(d.total)}`;
    if (subs[1]) subs[1].innerHTML = `%${data.current.rate} oran ${fmt(d.rate, '%')}`;
    if (subs[3]) subs[3].innerHTML = `${data.current.overdue ? 'Müdahale gerek' : 'Temiz'} ${fmtInverse(d.overdue)}`;
  } catch(e) { /* sessiz başarısızlık — rozet yoksa metin kalır */ }
}

// v5.2 — KPI kartı tıklaması → her zaman ilgili sayfa+filtre kombinasyonuna geçiş
export function kpiJump(kind) {
  if (kind === 'backup') { showPage('backups'); return; }
  if (!['overdue','done','open','all'].includes(kind)) return;
  // v5.4 — race yok: showPage loadTasks().then içinde uygular
  showPage('tasks', { statusKind: kind });
}

// v5.2 — Sidebar "Destek Talepleri" + pie legend için (v5.4: showPage delege)
export function showTasksWithCat(cat) {
  showPage('tasks', { cat: cat, activeNav: cat === 'support' ? 'support' : 'tasks' });
}

// v5.2 — Pie chart / Firma bar drill-down (v5.4: showPage delege)
function showTasksWithFirm(firm) {
  showPage('tasks', { firm: firm });
}

// v5.6 — Tasks sayfası "ekle" butonu: aktif moda göre kategori (task vs support).
export function addTaskFromTasksView() {
  const btn = document.getElementById('tasks-add-btn');
  const cat = (btn && btn.dataset.cat === 'support') ? 'support' : 'task';
  showPage('add');
  const catEl = document.getElementById('new-cat');
  if (catEl) { catEl.value = cat; onCatChange(); }
}

// v5.2 — Açık destek talebi sayısını sidebar nav badge'ine yansıt
export function updateSupportNavBadge() {
  const badge = document.getElementById('support-nav-badge');
  if (!badge) return;
  const cnt = state.tasks.filter(t => t.cat === 'support' && !t.done).length;
  if (cnt > 0) {
    badge.textContent = String(cnt);
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }
}

// v4.5 — SLA KPI kartlarını yükler
async function loadSlaKpi() {
  const row = document.getElementById('sla-kpi-row');
  if (!row) return;
  try {
    const now = new Date();
    const q = new URLSearchParams();
    q.set('month', now.getMonth() + 1); q.set('year', now.getFullYear());
    if (state.selectedUserId) q.set('user_id', state.selectedUserId);
    const r = await fetch('/api/sla/stats?' + q.toString());
    if (!r.ok) { row.style.display = 'none'; return; }
    const s = await r.json();
    if (!s.total) { row.style.display = 'none'; return; }
    row.style.display = '';
    // Compliance
    const comp = s.compliance_pct;
    const compEl = document.getElementById('sla-kpi-compliance');
    compEl.textContent = `%${comp}`;
    compEl.style.color = comp >= 90 ? 'var(--green)' : comp >= 70 ? 'var(--gold)' : 'var(--danger)';
    document.getElementById('sla-kpi-compliance-sub').textContent =
      s.resolved ? `${s.resolved_on_time}/${s.resolved} zamanında` : 'Çözülen ticket yok';
    // Breached
    document.getElementById('sla-kpi-breached').textContent = s.breached;
    document.getElementById('sla-kpi-breached-sub').textContent =
      s.breached ? 'Müdahale gerek' : 'İhlal yok';
    // Avg resolution
    const avg = s.avg_resolution_hours;
    const avgEl = document.getElementById('sla-kpi-avg');
    if (avg > 0) {
      avgEl.textContent = avg >= 24 ? `${Math.round(avg/24*10)/10}g` : `${Math.round(avg*10)/10}s`;
    } else {
      avgEl.textContent = '—';
    }
    document.getElementById('sla-kpi-avg-sub').textContent =
      s.resolved ? `${s.resolved} ticket üzerinden` : 'Destek talepleri';
    // Open
    document.getElementById('sla-kpi-open').textContent = s.open;
    // v5.13 — SLA iş-saati bazlıysa alt-satırda çalışma penceresini göster
    const bh = s.business_hours;
    if (bh && bh.enabled) {
      const wh = `${String(bh.work_start).padStart(2,'0')}:00-${String(bh.work_end).padStart(2,'0')}:00`;
      document.getElementById('sla-kpi-open-sub').textContent = `${s.total} talep · İş saati ${bh.work_days_label} ${wh}`;
    } else {
      document.getElementById('sla-kpi-open-sub').textContent = `Toplam ${s.total} talep` + (bh && !bh.enabled ? ' · SLA 7/24' : '');
    }
  } catch (e) {
    console.warn('[sla] kpi yüklenemedi', e);
    row.style.display = 'none';
  }
}

// v5.0 — Yönetilen Firmalar Şeridi (IT Müdürü dashboard'ında)
// NOT: Şerit v5.0'da dashboard'dan kaldırıldı (yerine /managed-firms sayfası).
// Fonksiyon şu an çağrılmıyor ama HTML/DOM geri gelebilir diye korunuyor.
// Backend: /api/dashboard/firm-summary (super_admin tüm firmaları, it_director managed_firms'ı görür)
async function loadDirectorFirmsStrip() {
  const stripEl = document.getElementById('director-firms-strip');
  if (!stripEl) return;
  const lvl = (state.currentUser && state.currentUser.permission_level) || 'junior';
  // Yetki kapısı — diğer roller için gizli kalır
  if (lvl !== 'super_admin' && lvl !== 'it_director') {
    stripEl.style.display = 'none';
    return;
  }
  try {
    const r = await fetch('/api/dashboard/firm-summary');
    if (!r.ok) { stripEl.style.display = 'none'; return; }
    const data = await r.json();
    // Levent kararı: 1 veya 0 firma yönetiliyorsa şerit gizli (gürültü ekleme)
    if (!Array.isArray(data) || data.length <= 1) {
      stripEl.style.display = 'none';
      return;
    }
    // Levent kararı: ilk 9 kart (slice tavanı, sınırsız scroll değil)
    const firms = data.slice(0, 9);
    const track = document.getElementById('firm-strip-track');
    const countEl = document.getElementById('firm-strip-count');
    if (countEl) countEl.textContent = (data.length > 9 ? `${firms.length}/${data.length}` : `${data.length}`) + ' firma';
    track.innerHTML = firms.map(f => {
      const rateClass = f.rate >= 70 ? 'r-good' : (f.rate >= 40 ? 'r-warn' : (f.rate > 0 ? 'r-bad' : 'r-none'));
      const themeClass = f.slug === 'inventist' ? 'fc-inv' : (f.slug === 'assos' ? 'fc-assos' : '');
      const slaTag = f.sla_breach > 0 ? `<div class="firm-card-sla" title="Açık SLA ihlali">${f.sla_breach} SLA</div>` : '';
      const aria = `${f.name}: ${f.total} görev, ${f.done} tamamlandı, ${f.overdue} gecikmiş, %${f.rate} oran`;
      const slugAttr = escapeHtml(f.slug || '');
      return `
        <div class="firm-card ${themeClass}" role="listitem" tabindex="0"
             data-firm-slug="${slugAttr}"
             onclick="onFirmStripClick('${slugAttr}', this)"
             onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();onFirmStripClick('${slugAttr}', this)}"
             aria-label="${escapeHtml(aria)}">
          ${slaTag}
          <div class="firm-card-top">
            <div class="firm-card-name">${escapeHtml(f.name || f.slug)}</div>
            <div class="firm-card-rate ${rateClass}">${f.total > 0 ? '%' + f.rate : '—'}</div>
          </div>
          <div class="firm-card-progress"><div class="firm-card-progress-fill ${rateClass}" style="width:${f.total > 0 ? f.rate : 0}%"></div></div>
          <div class="firm-card-stats">
            <span>${f.total} görev</span>
            ${f.overdue > 0 ? `<span class="ov">${f.overdue} geciken</span>` : ''}
          </div>
        </div>
      `;
    }).join('');
    stripEl.style.display = 'block';
  } catch (e) {
    console.warn('[firm-strip] yüklenemedi', e);
    stripEl.style.display = 'none';
  }
}

// v5.0 Q3-A — Karta tıklayınca firm-user-filter dropdown o firmanın ilk
// kullanıcısına auto-set olur, dashboard tek-kullanıcı mantığıyla yeniden yüklenir.
export function onFirmStripClick(firmSlug, cardEl) {
  // Aktif kart vurgusu (single-select)
  document.querySelectorAll('#firm-strip-track .firm-card').forEach(c => c.classList.remove('active'));
  if (cardEl) cardEl.classList.add('active');

  if (!firmSlug) return;
  // state.firmUsers (initFirmUserFilter'da yüklenir) içinden bu firma'nın ilk
  // kullanıcısını bul. Self ise filtreyi temizle (kendim).
  const sel = document.getElementById('firm-user-filter');
  if (!sel) return;
  const candidates = (state.firmUsers || []).filter(u => (u.firm || '') === firmSlug);
  // Önce kendim olmayanı seç (varsa); yoksa kendim
  let pick = candidates.find(u => u.id !== state.currentUser.id) || candidates[0];
  if (pick && pick.id !== state.currentUser.id) {
    sel.value = String(pick.id);
  } else {
    sel.value = ''; // Kendim
  }
  onFirmUserChange();
}
