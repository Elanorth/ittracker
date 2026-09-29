// ══════════════════════════════════════════════════════════
//  trash.js — Geri Dönüşüm (v5.100)
//
//  Silinen görevlerin listesi + geri getirme + super_admin için kalıcı silme.
//  60 gün retention penceresi; süre bitiminde APScheduler cron ile otomatik
//  kalıcı silinir.
//
//  Bağımlılıklar: escapeHtml (utils), state (state), showToast (app.js).
//  Inline data-click handler'ları events.js delegation üzerinden.
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { showToast, formatDateTR } from '../app.js';
import { onClick } from './events.js';

onClick('loadTrashList',   () => loadTrashList());
onClick('restoreTrashRow', el => restoreTrashRow(+el.dataset.id));
onClick('hardDeleteRow',   el => hardDeleteRow(+el.dataset.id, el.dataset.title || ''));

const _CAT_LABEL = {
  routine:'Rutin', project:'Proje', support:'Destek',
  infra:'Altyapı', backup:'Backup', other:'Diğer',
};

function _fmtDT(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const dd = String(d.getDate()).padStart(2,'0');
  const hh = String(d.getHours()).padStart(2,'0');
  const mn = String(d.getMinutes()).padStart(2,'0');
  return `${dd}.${mm}.${yyyy} ${hh}:${mn}`;
}

function _daysLeft(untilIso) {
  if (!untilIso) return null;
  const ms = new Date(untilIso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000*60*60*24)));
}

export async function loadTrashList() {
  const tbody = document.getElementById('trash-tbody');
  const empty = document.getElementById('trash-empty');
  const cnt = document.getElementById('trash-count-label');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="8" style="padding:20px;text-align:center;font-size:12px;color:var(--text-muted)">Yükleniyor…</td></tr>';
  if (empty) empty.style.display = 'none';
  try {
    const r = await fetch('/api/tasks/deleted');
    if (!r.ok) throw new Error((await r.json()).error || 'Yüklenemedi');
    const rows = await r.json();
    if (cnt) cnt.textContent = rows.length ? `${rows.length} kayıt` : '';
    if (!rows.length) {
      tbody.innerHTML = '';
      if (empty) empty.style.display = '';
      return;
    }
    const isSuper = state.currentUser?.permission_level === 'super_admin';
    tbody.innerHTML = rows.map(t => {
      const days = _daysLeft(t.restorable_until);
      const daysBadge = days !== null
        ? `<span style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:${days <= 7 ? 'var(--danger)' : 'var(--text-muted)'}">${days} gün</span>`
        : '—';
      const caseCode = t.case_code
        ? `<div style="font-size:9px;color:var(--text-muted);margin-top:2px">🌐 ${escapeHtml(t.case_code)}</div>`
        : '';
      const source = t.source === 'portal' ? '🌐 Portal' : '⚙ Manuel';
      const hardBtn = isSuper
        ? `<button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px;color:var(--danger);border-color:rgba(248,81,73,.3)" data-click="hardDeleteRow" data-id="${t.id}" data-title="${escapeHtml(t.title)}">🗑 Kalıcı Sil</button>`
        : '';
      return `
        <tr>
          <td>
            <div style="font-size:12px">${escapeHtml(t.title)}</div>
            ${caseCode}
          </td>
          <td style="font-size:11px">${_CAT_LABEL[t.category] || t.category}</td>
          <td style="font-size:11px">${escapeHtml((t.firm || '').toString().replace(/^./, c => c.toUpperCase()))}</td>
          <td style="font-size:11px">${source}</td>
          <td style="font-size:11px">${escapeHtml(t.deleted_by || '—')}</td>
          <td style="font-size:11px;font-family:'IBM Plex Mono',monospace">${_fmtDT(t.deleted_at)}</td>
          <td>${daysBadge}</td>
          <td style="text-align:right">
            <div style="display:flex;gap:6px;justify-content:flex-end">
              <button class="btn btn-primary btn-sm" style="padding:2px 10px;font-size:10px" data-click="restoreTrashRow" data-id="${t.id}">↩ Geri Getir</button>
              ${hardBtn}
            </div>
          </td>
        </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" style="padding:20px;text-align:center;color:var(--danger);font-size:12px">Hata: ${escapeHtml(e.message)}</td></tr>`;
    if (cnt) cnt.textContent = '';
  }
}

export async function restoreTrashRow(id) {
  try {
    const r = await fetch(`/api/tasks/${id}/restore`, { method: 'POST' });
    if (!r.ok) throw new Error((await r.json()).error || 'Geri getirilemedi');
    showToast('ok', '↩ Görev geri getirildi');
    loadTrashList();
  } catch (e) {
    showToast('err', e.message);
  }
}

export async function hardDeleteRow(id, title) {
  if (!confirm(`"${title}" görevini KALICI olarak silmek istiyor musunuz?\n\nBu işlem geri alınamaz — tüm mesajlar, ekler ve tamamlama kayıtları da silinir.`)) return;
  try {
    const r = await fetch(`/api/tasks/${id}/hard`, { method: 'DELETE' });
    if (!r.ok) throw new Error((await r.json()).error || 'Kalıcı silme başarısız');
    showToast('ok', '🗑 Kayıt kalıcı olarak silindi');
    loadTrashList();
  } catch (e) {
    showToast('err', e.message);
  }
}
