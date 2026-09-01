// ══════════════════════════════════════════════════════════
//  projects.js — Projeler sayfası (v5.66, ESM Faz 4f-6)
//
//  Proje görevleri kart görünümü (aktif/tamamlanan + istatistik + nav badge).
//  Bağımlılıklar: escapeHtml/_periodCompletionLabel (utils), firmChip (tasks),
//  state. formatDateTR bare global. Inline: apiToggleTask/openEditTask.
// ══════════════════════════════════════════════════════════
import { escapeHtml, _periodCompletionLabel } from './utils.js';
import { firmChip } from './tasks.js';
import { state } from './state.js';

export function renderProjectsPage() {
  const firmFilter = document.getElementById('proj-filter-firm')?.value || '';
  let projs = state.tasks.filter(t => t.cat === 'project');
  if (firmFilter) projs = projs.filter(t => t.firm === firmFilter);

  const today = new Date(); today.setHours(0,0,0,0);
  const active = projs.filter(t => !t.done);
  const done   = projs.filter(t => t.done);
  const overdue = active.filter(t => t.deadline && new Date(t.deadline) < today).length;

  // Stats
  document.getElementById('ps-total').textContent  = projs.length;
  document.getElementById('ps-active').textContent = active.length;
  document.getElementById('ps-overdue').textContent = overdue;
  document.getElementById('ps-done').textContent   = done.length;
  document.getElementById('proj-active-count').textContent = `${active.length} proje`;
  document.getElementById('proj-done-count').textContent   = `${done.length} proje`;

  // Nav badge: sadece geciken varsa göster
  const badge = document.getElementById('proj-nav-badge');
  if (badge) { badge.textContent = overdue; badge.style.display = overdue ? '' : 'none'; }

  const renderProjCard = t => {
    const dl = t.deadline ? new Date(t.deadline) : null;
    const isOverdue = dl && !t.done && dl < today;
    const dlStr = dl ? formatDateTR(t.deadline) : '—';
    const dlColor = isOverdue ? 'var(--danger)' : (dl && !t.done ? 'var(--gold)' : 'var(--text-muted)');
    const statusNote = t.project_status
      ? `<div class="proj-status-note">📌 ${escapeHtml(t.project_status)}</div>`
      : '';
    let clNote = '';
    if (t.checklist && t.checklist.length > 0) {
      const clTotal = t.checklist.length;
      const clDone  = (t.checklist_done||[]).filter(Boolean).length;
      const clPct   = Math.round(clDone/clTotal*100);
      clNote = `<div style="font-size:9px;color:var(--text-muted);margin-top:6px">
        Adımlar: ${clDone}/${clTotal}
        <div class="checklist-progress" style="margin-top:3px"><div class="checklist-progress-fill" style="width:${clPct}%"></div></div>
      </div>`;
    }
    return `
    <div class="proj-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px;${t.done?'text-decoration:line-through;opacity:.5':''}">${escapeHtml(t.title)}</div>
          <div style="font-size:10px;color:var(--text-muted);display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            ${firmChip(t.firm)}
            <span>${escapeHtml(t.team || '')}</span>
            ${isOverdue ? '<span style="color:var(--danger);font-weight:600">⚠ Gecikti</span>' : ''}
          </div>
          ${statusNote}${clNote}
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;min-width:80px">
          <div style="font-size:10px;color:${dlColor};font-family:'IBM Plex Mono',monospace">${dlStr}</div>
          <div style="display:flex;gap:4px">
            <div class="cb ${t.done?'done':''}" role="checkbox" aria-checked="${t.done?'true':'false'}" aria-label="${t.done?'Geri al':'Tamamla'}: ${escapeHtml(t.title)}${_periodCompletionLabel(t) ? ' — ' + _periodCompletionLabel(t) : ''}" tabindex="0" onclick="apiToggleTask(${t.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();apiToggleTask(${t.id})}" style="width:16px;height:16px;border-radius:4px"></div>
            <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" onclick="openEditTask(${t.id})">&#9998;</button>
          </div>
        </div>
      </div>
    </div>`;
  };

  const activeEl = document.getElementById('proj-active-body');
  if (activeEl) activeEl.innerHTML = active.length
    ? active.sort((a,b) => { // Geciken önce, sonra deadline sıralı
        const ad = a.deadline ? new Date(a.deadline) : new Date('9999');
        const bd = b.deadline ? new Date(b.deadline) : new Date('9999');
        return ad - bd;
      }).map(renderProjCard).join('')
    : '<div style="padding:16px;font-size:12px;color:var(--text-muted);text-align:center">Aktif proje yok</div>';

  const doneEl = document.getElementById('proj-done-body');
  if (doneEl) doneEl.innerHTML = done.length
    ? done.slice().reverse().map(renderProjCard).join('')
    : '<div style="padding:16px;font-size:12px;color:var(--text-muted);text-align:center">Tamamlanan proje yok</div>';
}
