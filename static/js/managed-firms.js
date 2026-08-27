// ══════════════════════════════════════════════════════════
//  managed-firms.js — "Yönettiğim Firmalar" sayfası (v5.49, ESM Faz 3c)
//
//  Gerçek ESM modülü. main.js import edip public fonksiyonları exposeAll ile
//  window'a bağlar (inline onclick + app.js showPage('managed-firms') için).
//  Bağımlılıklar: escapeHtml (import utils.js), state (import state.js),
//  showPage + typeof-guard'lı filterFullByFirm/updateTeamOptions (app.js klasik
//  → global). İç render helper'ları (renderManagedFirms/_mf*Html) modül-private.
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';

let _mfPeriod = '1m';
let _mfData = null;        // son fetch sonucu
let _mfShowAll = false;    // 6+ firma için expand state

export async function loadManagedFirmsPage() {
  const lvl = (state.currentUser && state.currentUser.permission_level) || 'junior';
  if (lvl !== 'super_admin' && lvl !== 'it_director') {
    // Yetki guard — bu sayfa zaten sadece director+ için. Defensif.
    return;
  }
  const cont = document.getElementById('mf-container');
  const empty = document.getElementById('mf-empty');
  const expandBtn = document.getElementById('mf-expand-btn');
  const sub = document.getElementById('mf-subtitle');
  if (!cont) return;
  cont.innerHTML = '<div class="mf-loading" id="mf-loading">Yükleniyor…</div>';
  empty.style.display = 'none';
  expandBtn.style.display = 'none';

  try {
    const r = await fetch('/api/managed-firms/detail?period=' + encodeURIComponent(_mfPeriod));
    if (!r.ok) {
      cont.innerHTML = `<div class="mf-loading" style="color:var(--danger)">Veri yüklenemedi (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    _mfData = data;
    if (!Array.isArray(data) || data.length === 0) {
      cont.innerHTML = '';
      empty.style.display = 'block';
      if (sub) sub.textContent = 'Yönetilen firma yok';
      return;
    }
    // Subtitle
    const periodLabel = _mfPeriod === '1m' ? 'Bu ay' : _mfPeriod === '3m' ? 'Son 3 ay' : 'Bu yıl';
    if (sub) sub.textContent = `${data.length} firma · ${periodLabel}`;
    renderManagedFirms();
  } catch (e) {
    console.warn('[mf] yüklenemedi', e);
    cont.innerHTML = '<div class="mf-loading" style="color:var(--danger)">Veri yüklenirken hata oluştu</div>';
  }
}

function renderManagedFirms() {
  const data = _mfData || [];
  const cont = document.getElementById('mf-container');
  const expandBtn = document.getElementById('mf-expand-btn');
  if (!cont) return;
  // Levent kararı (Soru 3 = B): super_admin için ilk 6 göster, fazlası expand butonuyla
  const SHOW_LIMIT = 6;
  const visible = (!_mfShowAll && data.length > SHOW_LIMIT) ? data.slice(0, SHOW_LIMIT) : data;
  cont.innerHTML = visible.map(_mfCardHtml).join('');
  if (data.length > SHOW_LIMIT && !_mfShowAll) {
    expandBtn.style.display = 'block';
    expandBtn.textContent = `${data.length - SHOW_LIMIT} firma daha göster`;
  } else {
    expandBtn.style.display = 'none';
  }
}

export function expandManagedFirms() {
  _mfShowAll = true;
  renderManagedFirms();
}

export function setMfPeriod(period, btnEl) {
  if (period === _mfPeriod) return;
  _mfPeriod = period;
  _mfShowAll = false;
  // Tab visual state
  document.querySelectorAll('.mf-period-tabs .tab').forEach(t => {
    const isActive = t === btnEl;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  loadManagedFirmsPage();
}

function _mfCardHtml(f) {
  const k = f.kpi || {};
  const rateClass = k.rate >= 70 ? 'r-good' : k.rate >= 40 ? 'r-warn' : k.rate > 0 ? 'r-bad' : '';
  const sla = (f.sla_breach_count || 0) > 0
    ? `<span class="mf-card-sla" title="Açık SLA ihlali">${f.sla_breach_count} SLA</span>`
    : '';
  const themeCls = f.theme_class || '';
  const updated = f.last_updated ? new Date(f.last_updated).toLocaleString('tr-TR', {hour:'2-digit',minute:'2-digit'}) : '';
  return `
    <div class="mf-card ${themeCls}" aria-label="${escapeHtml(f.name)} firma özeti">
      <div class="mf-card-head">
        <div class="mf-card-name">${escapeHtml(f.name)} ${sla}</div>
        <div class="mf-kpis">
          <div class="mf-kpi-chip"><div class="mf-kpi-label">Toplam</div><div class="mf-kpi-val">${k.total||0}</div></div>
          <div class="mf-kpi-chip"><div class="mf-kpi-label">Tamamlanan</div><div class="mf-kpi-val r-good">${k.done||0}</div></div>
          <div class="mf-kpi-chip"><div class="mf-kpi-label">Geciken</div><div class="mf-kpi-val r-overdue">${k.overdue||0}</div></div>
          <div class="mf-kpi-chip"><div class="mf-kpi-label">Oran</div><div class="mf-kpi-val ${rateClass}">${k.total ? '%' + (k.rate||0) : '—'}</div></div>
        </div>
      </div>
      <div class="mf-card-body">
        <div class="mf-col">
          <div class="mf-col-title">Aylık Trend (6 Ay)</div>
          ${_mfTrendHtml(f.trend || [])}
        </div>
        <div class="mf-col">
          <div class="mf-col-title">Kategori Dağılımı</div>
          ${_mfCatBarsHtml(f.category_breakdown || [])}
        </div>
        <div class="mf-col">
          <div class="mf-col-title">Geciken Top-3</div>
          ${_mfOverdueHtml(f.overdue_top3 || [])}
          <div class="mf-col-title" style="margin-top:14px">Kullanıcı Dağılımı</div>
          ${_mfUsersHtml(f.users || [])}
        </div>
      </div>
      <div class="mf-card-foot">
        <div class="mf-updated">${updated ? 'Son güncelleme · ' + updated : ''}</div>
        <div class="mf-actions">
          <button class="btn btn-outline btn-sm" onclick="_mfGotoTasks('${escapeHtml(f.slug)}')">Anlık Görevler →</button>
          <button class="btn btn-primary btn-sm" onclick="_mfGotoAdd('${escapeHtml(f.slug)}')">＋ Görev Ekle</button>
        </div>
      </div>
    </div>
  `;
}

function _mfTrendHtml(trend) {
  if (!trend.length) return '<div class="mf-overdue-empty">Trend verisi yok</div>';
  const max = Math.max(1, ...trend.map(t => t.total || 0));
  return `<div class="mf-trend">${trend.map(t => {
    const totalH = Math.round((t.total / max) * 100);
    const doneH = t.total > 0 ? Math.round((t.done / t.total) * totalH) : 0;
    return `
      <div class="mf-trend-col" title="${t.month} ${t.year}: ${t.done}/${t.total}">
        <div class="mf-trend-stack" aria-hidden="true">
          <div class="mf-trend-fill" style="height:${doneH}%;background:var(--text-dim)"></div>
          <div class="mf-trend-fill" style="height:${doneH}%;background:var(--green)"></div>
        </div>
        <div class="mf-trend-num">${t.total}</div>
        <div class="mf-trend-label">${t.month}</div>
      </div>`;
  }).join('')}</div>`;
}

function _mfCatBarsHtml(breakdown) {
  if (!breakdown.length) return '<div class="mf-overdue-empty">Bu periyotta kategori verisi yok</div>';
  const max = Math.max(1, ...breakdown.map(b => b.count));
  return `<div class="mf-cats">${breakdown.map(b => {
    const w = Math.round((b.count / max) * 100);
    return `
      <div class="mf-cat-row">
        <div class="mf-cat-head"><span class="mf-cat-label">${escapeHtml(b.label)}</span><span class="mf-cat-count">${b.count}</span></div>
        <div class="mf-cat-bar"><div class="mf-cat-fill cat-${escapeHtml(b.cat)}" style="width:${w}%"></div></div>
      </div>`;
  }).join('')}</div>`;
}

function _mfOverdueHtml(items) {
  if (!items.length) return '<div class="mf-overdue-empty">🎉 Geciken yok</div>';
  const unit = { 'Günlük':'gün', 'Haftalık':'hafta', 'Aylık':'ay', 'Yıllık':'yıl' };
  return `<div class="mf-overdue-list">${items.map(o => {
    // Rutin: "N hafta atlandı"; deadline-bazlı: "Ng geç" (backend kanonik is_overdue)
    const badge = (o.overdue_periods != null)
      ? `${o.overdue_periods} ${unit[o.period] || 'dönem'} atlandı`
      : `${o.days_overdue}g geç`;
    return `
    <div class="mf-overdue-item" title="${escapeHtml(o.title)}${o.assigned_to ? ' · ' + escapeHtml(o.assigned_to) : ''}">
      <span class="mf-overdue-title">${escapeHtml(o.title)}</span>
      <span class="mf-overdue-days">${badge}</span>
    </div>`;
  }).join('')}</div>`;
}

function _mfUsersHtml(users) {
  if (!users.length) return '<div class="mf-users-empty">Kullanıcı verisi yok</div>';
  return `<table class="mf-users-table">
    <thead><tr><th>Kullanıcı</th><th class="num">Açık</th><th class="num">Bitti</th></tr></thead>
    <tbody>
      ${users.map(u => `
        <tr>
          <td title="${escapeHtml(u.full_name)}">${escapeHtml(u.full_name)}</td>
          <td class="num open">${u.open_tasks}</td>
          <td class="num done">${u.done_tasks}</td>
        </tr>`).join('')}
    </tbody>
  </table>`;
}

export function _mfGotoTasks(firmSlug) {
  // Anlık Görevler sayfasına geç + firma filtresini set et
  showPage('tasks');
  const sel = document.getElementById('tasks-firm-filter');
  if (sel) {
    sel.value = firmSlug;
    if (typeof filterFullByFirm === 'function') filterFullByFirm(firmSlug);
  }
}

export function _mfGotoAdd(firmSlug) {
  showPage('add');
  const fSel = document.getElementById('new-firm');
  if (fSel) {
    fSel.value = firmSlug;
    if (typeof updateTeamOptions === 'function') updateTeamOptions();
  }
}
