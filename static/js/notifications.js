// ══════════════════════════════════════════════════════════
//  notifications.js — Bildirim çanı + Bildirim Ayarları (v5.50, ESM Faz 4a)
//
//  Gerçek ESM modülü (app.js'ten çıkarıldı). main.js import edip public
//  fonksiyonları exposeAll ile window'a bağlar (inline onclick + app.js).
//  Bağımlılıklar: escapeHtml + _routineOverdueLabel (import utils.js), state
//  (import state.js), FIRMS + openEditTask + showToast (app.js klasik → global).
//  İç helper'lar (updateNotifUI/renderNotifList/_getReadIds/_saveReadIds) private.
// ══════════════════════════════════════════════════════════
import { escapeHtml, _routineOverdueLabel } from './utils.js';
import { state } from './state.js';

// ══════════════════════════════════════════════════════════
//  BİLDİRİM SİSTEMİ
// ══════════════════════════════════════════════════════════
// notifications → state.js (ESM Faz 2c-2)

// v5.0 — Bildirimler artık backend /api/notifications/preview üzerinden gelir
// (rutin gecikmeleri + tüm overdue + SLA warning + SLA breach). Yerel rutin
// scan'i fallback olarak kalır; backend cevapsızsa kullanıcı yine bilgilendirilir.
const NOTIF_READ_KEY = 'itt_notif_read_v1';
function _getReadIds() {
  try { return new Set(JSON.parse(sessionStorage.getItem(NOTIF_READ_KEY) || '[]')); }
  catch(e) { return new Set(); }
}
function _saveReadIds(set) {
  try { sessionStorage.setItem(NOTIF_READ_KEY, JSON.stringify([...set])); }
  catch(e) {}
}

export async function buildNotifications() {
  state.notifications = [];
  const readIds = _getReadIds();

  let backendOk = false;
  try {
    const r = await fetch('/api/notifications/preview');
    if (r.ok) {
      const data = await r.json();
      backendOk = true;
      // v5.22 — Yeni portal case / kullanıcı yanıtı (en üstte)
      (data.new_cases || []).forEach(t => state.notifications.push({
        id:'nc'+t.id, type:'info', title:t.title,
        meta:`${t.kind==='reply'?'Kullanıcı yanıtı':'Yeni talep'} · ${t.case_code||''} · ${(FIRMS[t.firm]||{}).label||t.firm||''}${t.pooled?' · havuz':''}`,
        tag:'new', tagLabel:t.kind==='reply'?'YENİ YANIT':'YENİ TALEP', taskId:t.id,
        read: readIds.has('nc'+t.id), mailSent:false, _sortKey:-1
      }));
      // Sıralama: yeni case → breached → overdue → warning
      (data.sla_breached || []).forEach(t => state.notifications.push({
        id:'sb'+t.id, type:'danger', title:t.title,
        meta:`SLA AŞILDI · ${t.firm||''} ${t.team?'· '+t.team:''}`,
        tag:'late', tagLabel:'SLA AŞILDI', taskId:t.id,
        read: readIds.has('sb'+t.id), mailSent:false, _sortKey:0
      }));
      (data.overdue || []).forEach(t => state.notifications.push({
        id:'ov'+t.id, type:'danger', title:t.title,
        meta:`${t.days_late||'?'} gün gecikti · ${t.firm||''} ${t.team?'· '+t.team:''}`,
        tag:'late', tagLabel:`${t.days_late||'?'}g gecikti`, taskId:t.id,
        read: readIds.has('ov'+t.id), mailSent:false, _sortKey:1
      }));
      (data.sla_warning || []).forEach(t => {
        const rh = t.sla_remaining_hours;
        const rem = (typeof rh === 'number')
          ? (rh >= 24 ? `${(rh/24).toFixed(1)}g kaldı` : `${rh.toFixed(1)}s kaldı`)
          : 'süresi azaldı';
        state.notifications.push({
          id:'sw'+t.id, type:'warn', title:t.title,
          meta:`SLA: ${rem} · ${t.firm||''} ${t.team?'· '+t.team:''}`,
          tag:'due', tagLabel:'SLA YAKIN', taskId:t.id,
          read: readIds.has('sw'+t.id), mailSent:false, _sortKey:2
        });
      });
      state.notifications.sort((a,b) => a._sortKey - b._sortKey);
    }
  } catch(e) { /* sessizce fallback */ }

  if (!backendOk) {
    // Fallback: önceki yerel rutin tarama
    // v5.1 — Kanonik is_overdue/overdue_periods kullan (donmuş deadline yerine)
    const routines = state.tasks.filter(t => t.cat === 'routine' && t.period !== 'Tek Seferlik' && !t.done);
    routines.forEach(t => {
      const id = 'n'+t.id;
      if (t.is_overdue) {
        const lbl = _routineOverdueLabel(t);
        state.notifications.push({ id, type:'danger', title:t.title,
          meta:`${lbl} · ${t.team||''} · ${(FIRMS[t.firm]||{}).label||t.firm}`,
          tag:'late', tagLabel:lbl, taskId:t.id, read:readIds.has(id), mailSent:t.mailSent||false });
      }
    });
  }
  updateNotifUI();
}

function updateNotifUI() {
  const unread = state.notifications.filter(n => !n.read).length;
  const dot = document.getElementById('notif-dot');
  if (dot) dot.style.display = unread > 0 ? 'block' : 'none';
  const overdueCount = state.tasks.filter(t => t.cat==='routine' && !t.done && t.is_overdue).length;
  const nb = document.getElementById('sched-nav-badge');
  if (nb) { nb.textContent = overdueCount; nb.style.display = overdueCount > 0 ? 'inline-flex' : 'none'; }
  renderNotifList();
}

function renderNotifList() {
  const el = document.getElementById('notif-list'); if (!el) return;
  if (!state.notifications.length) { el.innerHTML = '<div class="notif-empty">🎉 Tüm rutin görevler zamanında!<br>Gecikme veya uyarı yok.</div>'; return; }
  el.innerHTML = state.notifications.map(n => `
    <div class="notif-item ${n.read?'':'unread'}" onclick="notifClick('${n.id}',${n.taskId})">
      <div class="notif-icon ${n.type==='danger'?'ndanger':n.type==='warn'?'nwarn':'ninfo'}">${n.tag==='new'?(n.tagLabel==='YENİ YANIT'?'💬':'🆕'):n.type==='danger'?'🔴':n.type==='warn'?'⚠️':'🔔'}</div>
      <div style="flex:1">
        <div class="notif-body-title">${escapeHtml(n.title)}</div>
        <div class="notif-body-meta">${escapeHtml(n.meta)}</div>
        <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:3px">
          <span class="notif-tag ${n.tag}">${n.tagLabel}</span>
          ${n.mailSent?'<span class="mail-sent-badge">📧 Mail gönderildi</span>':''}
        </div>
      </div>
    </div>`).join('');
}

export function notifClick(notifId, taskId) {
  const n = state.notifications.find(x => x.id === notifId); if (n) n.read = true;
  const r = _getReadIds(); r.add(notifId); _saveReadIds(r);
  updateNotifUI(); closeNotifDropdown(); openEditTask(taskId);
}
export function clearAllNotifs() {
  const r = _getReadIds();
  state.notifications.forEach(n => { n.read = true; r.add(n.id); });
  _saveReadIds(r);
  updateNotifUI();
}
export function toggleNotifDropdown() {
  const dd = document.getElementById('notif-dropdown'); if (!dd) return;
  dd.classList.toggle('hidden');
  if (!dd.classList.contains('hidden')) buildNotifications(); // async — fire & forget
}
export function closeNotifDropdown() { document.getElementById('notif-dropdown')?.classList.add('hidden'); }
document.addEventListener('click', e => {
  const wrap = document.getElementById('notif-wrap');
  if (wrap && !wrap.contains(e.target)) closeNotifDropdown();
});

// ══════════════════════════════════════════════════════════
//  BİLDİRİM AYARLARI (v4.6)
// ══════════════════════════════════════════════════════════
export async function loadNotificationsPage() {
  // Preview alanını temizle
  const box = document.getElementById('notify-preview');
  if (box) { box.style.display = 'none'; box.innerHTML = ''; }
  // v5.10 — Digest saati dropdown'unu doldur (00:00–23:00)
  const hourSel = document.getElementById('notify-digest-hour');
  if (hourSel && !hourSel.options.length) {
    hourSel.innerHTML = Array.from({length: 24}, (_, h) =>
      `<option value="${h}">${String(h).padStart(2,'0')}:00</option>`).join('');
  }
  try {
    const nRes = await fetch('/api/notifications/settings');
    if (!nRes.ok) return;
    const n = await nRes.json();
    const o = document.getElementById('notify-overdue');
    const s = document.getElementById('notify-sla-warning');
    const b = document.getElementById('notify-sla-breach');
    const d = document.getElementById('notify-daily-digest');
    const m = document.getElementById('notify-manager-digest');
    if (o) o.checked = !!n.notify_overdue;
    if (s) s.checked = !!n.notify_sla_warning;
    if (b) b.checked = !!n.notify_sla_breach;
    if (d) d.checked = !!n.notify_daily_digest;
    if (m) m.checked = !!n.notify_manager_digest;
    // Müdür digesti yalnızca director+ kullanıcıya görünür
    const mGroup = document.getElementById('notify-manager-group');
    if (mGroup) mGroup.style.display = n.is_director ? '' : 'none';
    // Eşikler
    const days = document.getElementById('notify-overdue-days');
    if (days) days.value = n.overdue_days ?? 3;
    const ratio = document.getElementById('notify-sla-ratio');
    if (ratio) ratio.value = String(n.sla_warning_ratio ?? 0.25);
    if (hourSel) hourSel.value = String(n.digest_hour ?? 9);
    const tzLabel = document.getElementById('notify-tz-label');
    if (tzLabel) tzLabel.textContent = n.timezone ? `(${n.timezone})` : '';
    const sub = document.getElementById('notify-page-sub');
    if (sub && n.schedule) sub.textContent = `Özet maili: ${n.schedule} · Uyarı tercihlerinizi ve test mailini buradan yönetin`;
  } catch(e) { console.warn('Bildirim ayarları yüklenemedi:', e); }
}

export async function saveNotificationSettings() {
  const body = {
    notify_overdue:        document.getElementById('notify-overdue')?.checked ?? true,
    notify_sla_warning:    document.getElementById('notify-sla-warning')?.checked ?? true,
    notify_sla_breach:     document.getElementById('notify-sla-breach')?.checked ?? true,
    notify_daily_digest:   document.getElementById('notify-daily-digest')?.checked ?? true,
    notify_manager_digest: document.getElementById('notify-manager-digest')?.checked ?? true,
  };
  // v5.10 — eşikler (geçersiz/boş değer gönderilmez → backend mevcut değeri korur)
  const days = parseInt(document.getElementById('notify-overdue-days')?.value, 10);
  if (!Number.isNaN(days)) body.notify_overdue_days = days;
  const ratio = parseFloat(document.getElementById('notify-sla-ratio')?.value);
  if (!Number.isNaN(ratio)) body.notify_sla_ratio = ratio;
  const hour = parseInt(document.getElementById('notify-digest-hour')?.value, 10);
  if (!Number.isNaN(hour)) body.notify_digest_hour = hour;
  try {
    const r = await fetch('/api/notifications/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Kaydedilemedi');
    showToast('ok', 'Bildirim tercihleri kaydedildi');
    // Subtitle'daki saat/eşik bilgisini tazele
    loadNotificationsPage();
  } catch(e) {
    showToast('err', 'Hata: ' + e.message);
  }
}

export async function previewNotifications() {
  const box = document.getElementById('notify-preview');
  if (box) { box.style.display='block'; box.textContent = 'Yükleniyor…'; }
  try {
    const r = await fetch('/api/notifications/preview');
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Hata');
    if (!j.total) {
      box.textContent = 'Şu an bildirim gerektiren bir göreviniz yok.';
      return;
    }
    const lines = [];
    lines.push(`Toplam ${j.total} uyarı:`);
    if (j.overdue.length)      lines.push(`• ${j.overdue.length} geciken görev`);
    if (j.sla_breached.length) lines.push(`• ${j.sla_breached.length} SLA aşan destek`);
    if (j.sla_warning.length)  lines.push(`• ${j.sla_warning.length} SLA uyarısı destek`);
    lines.push('');
    const listAll = [...j.overdue.map(t=>`#${t.id} ${t.title} — ${t.days_late}g gecikme`),
                     ...j.sla_breached.map(t=>`#${t.id} ${t.title} — SLA AŞILDI`),
                     ...j.sla_warning.map(t=>`#${t.id} ${t.title} — ${t.sla_remaining_hours}s kaldı`)];
    box.innerHTML = lines.map(escapeHtml).join('<br>') + '<br>' + listAll.map(escapeHtml).join('<br>');
  } catch(e) {
    if (box) box.textContent = 'Hata: ' + e.message;
  }
}

export async function runNotificationTest() {
  if (!confirm('Test maili şimdi adresinize gönderilecek. Onaylıyor musunuz?')) return;
  showToast('ok', 'Test maili gönderiliyor…');
  try {
    const r = await fetch('/api/notifications/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Hata');
    const row = (j.results || [])[0];
    if (!row) { showToast('ok', 'Job çalıştı ama kayıt döndürmedi'); return; }
    if (row.skipped) showToast('ok', 'Şu an bildirilecek göreviniz yok (mail atılmadı).');
    else if (row.sent) showToast('ok', `Mail gönderildi: ${row.count} uyarı`);
    else showToast('err', `Gönderim hatası: ${row.error || 'bilinmiyor'}`);
  } catch(e) {
    showToast('err', 'Hata: ' + e.message);
  }
}
