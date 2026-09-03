// ══════════════════════════════════════════════════════════
//  scheduled.js — Zamanlanmış görevler + Takvim (v5.62, ESM Faz 4f-2)
//
//  Rutin görev sayfası (KPI + periyot dağılımı + aktif/tamamlanan/gelecek liste)
//  ve aylık takvim görünümü. app.js'ten çıkarıldı.
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//
//  Bağımlılıklar: TODAY/escapeHtml/_routineOverdueLabel/_periodCompletionLabel
//  (utils import), firmChip (tasks import), state (import). setDateDisplay/
//  formatDateTR/showToast/buildNotifications app.js klasik → bare global
//  (app.js modül olunca import'a döner). Inline onclick: apiToggleTask/openEditTask.
// ══════════════════════════════════════════════════════════
import { TODAY, escapeHtml, _routineOverdueLabel, _periodCompletionLabel } from './utils.js';
import { firmChip, apiToggleTask, openEditTask } from './tasks.js';
import { state } from './state.js';
import { formatDateTR, setDateDisplay, showToast } from '../app.js';
import { setWeeklyPeriod } from './dashboard.js';
import { buildNotifications } from './notifications.js';
import { onClick, onChange } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — zamanlanmış görevler + takvim aksiyonları (inline onclick → data-click)
onClick('toggleSchedView',    el => toggleSchedView(el.dataset.view));
onChange('renderScheduledList', () => renderScheduledList()); // filtre select'leri
onClick('toggleAlarm', el => toggleAlarm(+el.dataset.id)); // satır alarm toggle (generated)
onClick('toggleSchedSection', el => toggleSchedSection(el.dataset.section));
onClick('setWeeklyPeriod',    el => setWeeklyPeriod(+el.dataset.weeks, el));
onClick('calNavMonth',        el => calNavMonth(+el.dataset.dir));
onClick('calGoToday',         () => calGoToday());

export function renderScheduledPage() {
  setDateDisplay('sched-date-day', 'sched-date-full');
  const routines = state.tasks.filter(t => t.cat === 'routine');

  // v5.1 — Kanonik gruplama: is_done (period_key bazlı) + is_overdue.
  // Donmuş next_due/last_completed yerine backend'in periyot-aware sinyalleri.
  const _done   = routines.filter(t => t.done);
  const overdue = routines.filter(t => !t.done && t.is_overdue).length;
  const dueSoon = routines.filter(t => !t.done && !t.is_overdue).length;  // bu periyot bekliyor
  const done    = _done.length;
  document.getElementById('sched-kpi-row').innerHTML = `
    <div class="kpi c-purple" style="animation-delay:.04s"><div class="kpi-icon">🔁</div><div class="kpi-label">Toplam Rutin</div><div class="kpi-value" style="color:var(--accent3)">${routines.length}</div><div class="kpi-sub">Zamanlanmış görev</div></div>
    <div class="kpi c-orange" style="animation-delay:.08s"><div class="kpi-icon">🔴</div><div class="kpi-label">Geciken</div><div class="kpi-value" style="color:var(--danger)">${overdue}</div><div class="kpi-sub">${overdue>0?'Dikkat gerekiyor':'Gecikme yok'}</div></div>
    <div class="kpi c-gold"   style="animation-delay:.12s"><div class="kpi-icon">⚡</div><div class="kpi-label">Bugün / Yakın</div><div class="kpi-value" style="color:var(--gold)">${dueSoon}</div><div class="kpi-sub">3 gün içinde bitmeli</div></div>
    <div class="kpi c-green"  style="animation-delay:.16s"><div class="kpi-icon">✅</div><div class="kpi-label">Tamamlanan</div><div class="kpi-value" style="color:var(--green)">${done}</div><div class="kpi-sub">Bu dönem</div></div>`;
  const periods = {Günlük:0,Haftalık:0,Aylık:0,Yıllık:0};
  routines.forEach(t => { if (periods[t.period] !== undefined) periods[t.period]++; });
  const maxP = Math.max(...Object.values(periods), 1);
  const pColors = {Günlük:'var(--accent3)',Haftalık:'var(--accent)',Aylık:'var(--gold)',Yıllık:'var(--accent2)'};
  document.getElementById('sched-period-dist').innerHTML = Object.entries(periods).map(([k,v]) => `
    <div class="progress-wrap" style="margin-bottom:10px">
      <div class="progress-label"><span>${k}</span><span style="color:${pColors[k]}">${v}</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${v/maxP*100}%;background:${pColors[k]}"></div></div>
    </div>`).join('');
  if (state.schedView === 'calendar') renderCalendar();
  else renderScheduledList();
}

export function renderScheduledList() {
  const periodF = document.getElementById('sf-period')?.value || '';
  const firmF   = document.getElementById('sf-firm')?.value   || '';

  const today = new Date(TODAY);
  const soon  = new Date(TODAY); soon.setDate(soon.getDate() + 7); // 7 gün içi = aktif

  // Tüm rutin görevleri al
  let all = state.tasks.filter(t => t.cat === 'routine');
  if (periodF) all = all.filter(t => t.period === periodF);
  if (firmF)   all = all.filter(t => t.firm   === firmF);

  // v5.1 — Kanonik gruplama: bu periyot için is_done (period_key bazlı).
  // done  = bu periyot tamamlanmış (t.done === true, backend is_done_now)
  // active = bu periyot bekliyor VEYA geçmiş periyotlar gecikmiş (t.done === false)
  // upcoming = rutin için kullanılmaz (her zaman aktif bir periyot vardır)
  const active   = [];
  const done     = [];
  const upcoming = [];

  all.forEach(t => {
    if (t.done) done.push(t);
    else        active.push(t);
  });

  // Sırala
  // v5.1 — Aktif sıralama: en çok gecikmiş (overdue_periods) en üstte, sonra bekleyenler
  active.sort((a,b) => (b.overdue_periods || 0) - (a.overdue_periods || 0));
  done.sort((a,b) => new Date(b.last_completed || 0) - new Date(a.last_completed || 0));

  // Sayaçlar
  document.getElementById('sched-count-label').textContent = `${active.length} aktif`;
  _setSchedBadge('active',   active.length,   active.some(t => t.is_overdue) ? 'danger' : 'normal');
  _setSchedBadge('done',     done.length,     'done');
  _setSchedBadge('upcoming', upcoming.length, 'upcoming');

  // ── AKTİF ──
  const activeBody = document.getElementById('sched-list-body');
  if (activeBody) {
    if (!active.length) {
      activeBody.innerHTML = '<div class="sched-section-empty">🎉 Bu dönemde tüm görevler tamamlandı veya henüz vakti gelmedi.</div>';
    } else {
      activeBody.innerHTML = active.map(t => _renderSchedRow(t)).join('');
    }
  }

  // ── TAMAMLANDI ──
  const doneBody = document.getElementById('sched-list-done');
  if (doneBody) {
    if (!done.length) {
      doneBody.innerHTML = '<div class="sched-section-empty">Henüz bu periyotta tamamlanan görev yok.</div>';
    } else {
      doneBody.innerHTML = done.map(t => {
        const lcDate = t.last_completed ? new Date(t.last_completed).toLocaleDateString('tr-TR',{day:'numeric',month:'long'}) : '—';
        const nextDate = t.next_due ? formatDateTR(t.next_due) : '—';
        return `<div class="sched-done-row">
          <div>
            <div class="sched-done-title">${escapeHtml(t.title)}</div>
            <div class="sched-done-meta">${firmChip(t.firm)} · ${escapeHtml(t.team||'')} · ${t.period||''}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
            <span class="last-done-chip">✓ ${lcDate}</span>
            <span style="font-size:9px;color:var(--text-dim)">Sonraki: ${nextDate}</span>
          </div>
        </div>`;
      }).join('');
    }
  }

  // ── GELECEK ──
  const upcomingBody = document.getElementById('sched-list-upcoming');
  if (upcomingBody) {
    if (!upcoming.length) {
      upcomingBody.innerHTML = '<div class="sched-section-empty">Yakın vadede bekleyen görev yok.</div>';
    } else {
      upcomingBody.innerHTML = upcoming.map(t => {
        const nd = t.next_due ? new Date(t.next_due) : null;
        const diffDays = nd ? Math.round((nd - new Date(TODAY)) / 86400000) : null;
        const opensIn = diffDays !== null
          ? (diffDays === 0 ? 'Bugün açılır' : diffDays === 1 ? 'Yarın açılır' : `${diffDays} gün sonra açılır`)
          : '—';
        const lcDate = t.last_completed ? new Date(t.last_completed).toLocaleDateString('tr-TR',{day:'numeric',month:'long'}) : null;
        return `<div class="sched-upcoming-row">
          <div>
            <div class="sched-upcoming-title">${escapeHtml(t.title)}</div>
            <div class="sched-upcoming-meta">${firmChip(t.firm)} · ${escapeHtml(t.team||'')} · ${t.period||''}
              ${lcDate ? `· <span style="color:var(--accent);font-size:9px">✓ Son: ${lcDate}</span>` : ''}
            </div>
          </div>
          <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
            <span class="opens-in-chip">📅 ${opensIn}</span>
            <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" data-click="openEditTask" data-id="${t.id}">&#9998;</button>
          </div>
        </div>`;
      }).join('');
    }
  }
}

function _setSchedBadge(section, count, type) {
  const el = document.getElementById('sched-badge-' + section);
  if (!el) return;
  el.textContent = count;
  el.style.display = count > 0 ? 'inline-flex' : 'none';
  if (type === 'danger') { el.style.background = 'var(--danger)'; el.style.color = '#fff'; }
  else if (type === 'done') { el.style.background = 'rgba(63,185,80,.2)'; el.style.color = 'var(--green)'; }
  else if (type === 'upcoming') { el.style.background = 'var(--surface3)'; el.style.color = 'var(--text-muted)'; }
  else { el.style.background = 'var(--accent)'; el.style.color = '#000'; }
}

export function toggleSchedSection(section) {
  const el = document.getElementById('sched-section-' + section);
  if (el) el.classList.toggle('collapsed');
}

function _renderSchedRow(t) {
  // v5.1 — Rutin görevler: kanonik is_overdue/overdue_periods (donmuş deadline yerine).
  // Diğer kategoriler (Tek Seferlik rutin dahil): eski deadline-bazlı mantık.
  let nrClass, nrText, rowClass;
  if (t.cat === 'routine' && t.period !== 'Tek Seferlik') {
    if (t.done) {
      nrClass = 'done';  nrText = t.current_period_label ? `${t.current_period_label} ✓` : 'Tamamlandı';  rowClass = '';
    } else if (t.is_overdue) {
      nrClass = 'overdue';  nrText = _routineOverdueLabel(t);  rowClass = 'row-overdue';
    } else {
      nrClass = 'today';  nrText = t.current_period_label ? `${t.current_period_label} bekliyor` : 'Bekliyor';  rowClass = 'row-due';
    }
  } else {
    const diff = t.deadline ? Math.round((new Date(t.deadline) - new Date(TODAY)) / 86400000) : null;
    nrClass = t.done ? 'done' : diff === null ? 'upcoming' : diff < 0 ? 'overdue' : diff === 0 ? 'today' : 'upcoming';
    nrText  = t.done ? 'Tamamlandı' : diff === null ? '—' : diff < 0 ? `${Math.abs(diff)}g gecikti` : diff === 0 ? 'BUGÜN' : diff === 1 ? 'Yarın' : formatDateTR(t.deadline);
    rowClass = t.done ? '' : diff !== null && diff < 0 ? 'row-overdue' : diff !== null && diff <= 1 ? 'row-due' : '';
  }
  const alarmOn  = t.alarm || false;
  const pColor = {Günlük:'var(--accent3)',Haftalık:'var(--accent)',Aylık:'var(--gold)',Yıllık:'var(--accent2)','Tek Seferlik':'var(--text-muted)'}[t.period]||'var(--text-muted)';
  const pBg    = {Günlük:'rgba(127,108,247,.15)',Haftalık:'rgba(0,229,192,.12)',Aylık:'rgba(244,185,66,.12)',Yıllık:'rgba(255,95,61,.12)','Tek Seferlik':'var(--surface2)'}[t.period]||'var(--surface2)';
  return `
  <div class="sched-row ${rowClass}" id="sr-${t.id}">
    <div class="cb ${t.done?'done':''}" role="checkbox" aria-checked="${t.done?'true':'false'}" aria-label="${t.done?'Geri al':'Tamamla'}: ${escapeHtml(t.title)}${_periodCompletionLabel(t) ? ' — ' + _periodCompletionLabel(t) : ''}" tabindex="0" data-click="apiToggleTask" data-id="${t.id}" title="${t.done?'Geri al':'Tamamlandı işaretle'}"></div>
    <div style="min-width:0">
      <div style="font-size:13px;font-weight:500;${t.done?'text-decoration:line-through;color:var(--text-muted)':''};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(t.title)}</div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:3px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        ${firmChip(t.firm)} <span>· ${escapeHtml(t.team||'')}</span>
        ${t.last_notified ? `<span title="Son bildirim: ${formatDateTR(t.last_notified.substring(0,10))}" style="color:var(--accent3);font-size:9px">📧 bildirildi</span>` : ''}
      </div>
    </div>
    <div>
      <div class="next-run-chip ${nrClass}">${nrText}</div>
      ${(() => {
        // v5.1 — Rutin: bir sonraki periyot tarihi (canlı); diğerleri: deadline (donuk değil)
        const showDate = (t.cat === 'routine' && t.period !== 'Tek Seferlik') ? t.next_period_date : t.deadline;
        return showDate ? `<div style="font-size:9px;color:var(--text-dim);margin-top:3px;font-family:'IBM Plex Mono',monospace">${formatDateTR(showDate)}</div>` : '';
      })()}
    </div>
    <div><span class="period-badge" style="background:${pBg};color:${pColor}">${t.period}</span></div>
    <div style="display:flex;flex-direction:column;gap:5px">
      <label class="alarm-toggle" data-click="toggleAlarm" data-id="${t.id}">
        <div class="alarm-switch ${alarmOn?'on':''}"></div>
        <span style="font-size:10px;color:var(--text-muted)">${alarmOn?'Açık':'Kapalı'}</span>
      </label>
      <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" data-click="openEditTask" data-id="${t.id}">&#9998; Düzenle</button>
    </div>
  </div>`;
}


export async function toggleAlarm(taskId) {
  const t = state.tasks.find(t => t.id === taskId); if (!t) return;
  const next = !t.alarm;
  t.alarm = next;
  renderScheduledList(); buildNotifications();
  try {
    const r = await fetch(`/api/tasks/${taskId}/alarm`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alarm_enabled: next })
    });
    if (!r.ok) throw new Error((await r.json()).error || 'Sunucu hatası');
    showToast('ok', next ? `🔔 Alarm açıldı` : `Alarm kapatıldı`);
  } catch(err) {
    // Başarısızsa geri al
    t.alarm = !next;
    renderScheduledList(); buildNotifications();
    showToast('err', `Alarm değiştirilemedi: ${err.message}`);
  }
}

// ══════════════════════════════════════════════════════════
//  TAKVİM
// ══════════════════════════════════════════════════════════
// schedView/calYear/calMonth → state.js (window.state, ESM Faz 2a)
export function toggleSchedView(view) {
  state.schedView = view;
  const listEl = document.getElementById('sched-list-view');
  const calEl  = document.getElementById('sched-cal-view');
  if (listEl) listEl.style.display = view === 'list' ? '' : 'none';
  if (calEl)  calEl.style.display  = view === 'calendar' ? '' : 'none';
  document.getElementById('sched-btn-list')?.classList.toggle('active', view === 'list');
  document.getElementById('sched-btn-cal')?.classList.toggle('active', view === 'calendar');
  if (view === 'calendar') renderCalendar();
}

function renderCalendar() {
  const routines = state.tasks.filter(t => t.cat === 'routine');
  const yr = state.calYear, mo = state.calMonth;
  const MONTHS_TR = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  const el = document.getElementById('cal-month-title');
  if (el) el.textContent = `${MONTHS_TR[mo]} ${yr}`;

  // Periyot filtresine göre filtrele (liste ile aynı filtreler)
  const periodF = document.getElementById('sf-period')?.value || '';
  const firmF   = document.getElementById('sf-firm')?.value   || '';
  let filtered = routines;
  if (periodF) filtered = filtered.filter(t => t.period === periodF);
  if (firmF)   filtered = filtered.filter(t => t.firm === firmF);

  // Görev tarih haritası: "YYYY-MM-DD" -> [{task, chipClass}]
  const taskMap = {};
  filtered.forEach(t => {
    // Her görevi deadline'ına yerleştir; yoksa next_due'ya
    const dateStr = t.deadline || t.next_due;
    if (!dateStr) return;
    if (!taskMap[dateStr]) taskMap[dateStr] = [];
    const diff = Math.round((new Date(dateStr) - new Date(TODAY)) / 86400000);
    const chipClass = t.done ? 'done' : diff < 0 ? 'overdue' : diff === 0 ? 'cal-today' : 'upcoming';
    taskMap[dateStr].push({ task: t, chipClass });
  });

  // Takvim ızgarası
  const firstDay  = new Date(yr, mo, 1);
  const lastDay   = new Date(yr, mo + 1, 0);
  const startDow  = (firstDay.getDay() + 6) % 7; // Pazartesi = 0
  const totalDays = lastDay.getDate();

  const cells = [];
  for (let i = startDow - 1; i >= 0; i--) {
    cells.push({ date: new Date(yr, mo, -i), otherMonth: true });
  }
  for (let d = 1; d <= totalDays; d++) {
    cells.push({ date: new Date(yr, mo, d), otherMonth: false });
  }
  const rem = cells.length % 7;
  if (rem > 0) {
    for (let i = 1; i <= 7 - rem; i++) {
      cells.push({ date: new Date(yr, mo + 1, i), otherMonth: true });
    }
  }

  const DOW = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
  let html = '<div class="cal-grid">';
  DOW.forEach(d => { html += `<div class="cal-dow">${d}</div>`; });

  cells.forEach(cell => {
    const ds = cell.date.toISOString().split('T')[0];
    const isToday = ds === TODAY;
    const dayTasks = taskMap[ds] || [];
    const cellCls = ['cal-cell',
      cell.otherMonth ? 'other-month' : '',
      isToday ? 'today' : '',
      dayTasks.length ? 'has-tasks' : ''
    ].filter(Boolean).join(' ');

    html += `<div class="${cellCls}">`;
    html += `<div class="cal-day-num">${cell.date.getDate()}</div>`;
    const MAX = 3;
    dayTasks.slice(0, MAX).forEach(({ task, chipClass }) => {
      html += `<div class="cal-task-chip ${chipClass}" data-click="openEditTask" data-id="${task.id}" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</div>`;
    });
    if (dayTasks.length > MAX) {
      html += `<div class="cal-more">+${dayTasks.length - MAX} daha</div>`;
    }
    html += '</div>';
  });

  html += '</div>';
  const container = document.getElementById('cal-grid-container');
  if (container) container.innerHTML = html;
}

export function calNavMonth(dir) {
  state.calMonth += dir;
  if (state.calMonth > 11) { state.calMonth = 0; state.calYear++; }
  if (state.calMonth < 0)  { state.calMonth = 11; state.calYear--; }
  renderCalendar();
}

export function calGoToday() {
  state.calYear  = new Date().getFullYear();
  state.calMonth = new Date().getMonth();
  renderCalendar();
}
