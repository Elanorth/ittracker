// ══════════════════════════════════════════════════════════
//  backup.js — Yedekler sayfası (v5.66, ESM Faz 4f-6)
//
//  Config backup dosya listesi (firma/arama filtresi + istatistik + indir).
//  Bağımlılıklar: escapeHtml (utils), firmChip (tasks), state.
//  Inline: openEditTask/downloadBackup. getBackupTasks/formatFileSize modül-private.
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { firmChip, openEditTask } from './tasks.js';
import { state } from './state.js';
import { onClick, onChange, onInput } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — yedek filtreleri (firma select → change; arama kutusu → input)
onChange('filterBackups', () => filterBackups());
onInput('filterBackups',  () => filterBackups());
onClick('downloadBackup', el => downloadBackup(+el.dataset.id)); // satır "indir" (generated; tasks.js edit-modal da kullanır)

function getBackupTasks() {
  return state.tasks.filter(t => t.cat === 'backup' && t.backup);
}

function formatFileSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

export async function renderBackupList() {
  const body = document.getElementById('backup-list-body');

  // API'den backup listesini çek
  let backups = [];
  try {
    const res = await fetch('/api/backups');
    if (res.ok) backups = await res.json();
  } catch(e) { console.error('Backup yüklenemedi:', e); }

  const firmFilter   = document.getElementById('bk-filter-firm')?.value || '';
  const searchFilter = (document.getElementById('bk-search')?.value || '').toLowerCase();

  let filtered = backups;
  if (firmFilter)   filtered = filtered.filter(b => b.firm === firmFilter);
  if (searchFilter) filtered = filtered.filter(b =>
    (b.task_title||'').toLowerCase().includes(searchFilter) ||
    (b.filename||'').toLowerCase().includes(searchFilter) ||
    (b.device||'').toLowerCase().includes(searchFilter)
  );

  // İstatistikler
  const nowMonth = new Date().getMonth();
  document.getElementById('bk-total').textContent     = backups.length;
  document.getElementById('bk-inventist').textContent = backups.filter(b=>b.firm==='inventist').length;
  document.getElementById('bk-assos').textContent     = backups.filter(b=>b.firm==='assos').length;
  document.getElementById('bk-month').textContent     = backups.filter(b => {
    if (!b.uploaded_at) return false;
    return new Date(b.uploaded_at).getMonth() === nowMonth;
  }).length;
  document.getElementById('bk-count-label').textContent = `${filtered.length} kayıt`;

  if (!body) return;
  if (!filtered.length) {
    body.innerHTML = '<div style="padding:32px;text-align:center;font-size:12px;color:var(--text-muted)">Henüz config backup kaydı yok.<br>Yeni Görev Ekle → Config Backup seçerek dosya yükleyebilirsiniz.</div>';
    return;
  }

  body.innerHTML = filtered.map(b => {
    const sizeStr = b.file_size ? (b.file_size > 1024 ? Math.round(b.file_size/1024)+' KB' : b.file_size+' B') : '';
    const uploadDate = b.uploaded_at ? new Date(b.uploaded_at).toLocaleDateString('tr-TR') : '—';
    return `
    <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;padding:13px 0;border-bottom:1px solid var(--border)">
      <div>
        <div style="font-size:13px;font-weight:500">${escapeHtml(b.task_title || '—')}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:4px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          ${firmChip(b.firm||'')}
          <span>· ${b.team||''}</span>
          <span>· ${uploadDate}</span>
        </div>
        <div style="margin-top:6px;display:flex;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--border2);border-radius:6px;padding:6px 10px;width:fit-content">
          <span style="font-size:18px">💾</span>
          <div>
            <div style="font-size:11px;font-weight:600;color:var(--gold);font-family:'IBM Plex Mono',monospace">${escapeHtml(b.filename)}</div>
            <div style="font-size:9px;color:var(--text-muted)">${sizeStr}${b.device?' · '+escapeHtml(b.device):''}</div>
          </div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:5px;align-items:flex-end;min-width:80px">
        <button class="btn btn-outline btn-sm" style="padding:3px 9px;font-size:10px;width:80px" data-click="openEditTask" data-id="${b.task_id}">&#9998; Görev</button>
        <button class="btn btn-sm" style="padding:3px 9px;font-size:10px;width:80px;background:var(--gold-dim);border:1px solid rgba(244,185,66,.25);color:var(--gold)" data-click="downloadBackup" data-id="${b.id}">&#8595; İndir</button>
      </div>
    </div>`;
  }).join('');
}

export function filterBackups() {
  renderBackupList();
}

export function downloadBackup(backupId) {
  window.location.href = '/api/backups/' + backupId + '/download';
}
