// ══════════════════════════════════════════════════════════
//  pool.js — Destek Havuzu (v5.65, ESM Faz 4f-5)
//
//  Atanmamış (portal) destek talepleri havuzu: liste + üstlen/bırak/çöz.
//  app.js'ten çıkarıldı. main.js import edip public fonksiyonları exposeAll
//  ile window'a bağlar.
//
//  Bağımlılıklar: escapeHtml/catLabel/priorityBadge/slaBadge/unreadBadge (utils),
//  firmChip (tasks), state (import). normalizeTask/formatDateTR/showToast/loadTasks/
//  renderFullList/closeEditTaskModal app.js/tasks.js → bare global. Inline: openEditTask.
// ══════════════════════════════════════════════════════════
import { escapeHtml, catLabel, priorityBadge, slaBadge, unreadBadge } from './utils.js';
import { firmChip } from './tasks.js';
import { state } from './state.js';
import { onClick } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — destek havuzu aksiyonları (inline onclick → data-click)
// releaseCase/resolveCase edit-task modalından çağrılır → aktif görev id'sini oku.
const _editTaskId = () => parseInt(document.getElementById('edit-task-id').value, 10);
onClick('loadPoolPage', () => loadPoolPage());
onClick('releaseCase',  () => releaseCase(_editTaskId()));
onClick('resolveCase',  () => resolveCase(_editTaskId()));

let _poolCases = [];

export async function updatePoolBadge() {
  try {
    const r = await fetch('/api/support/pool');
    if (!r.ok) return;
    _poolCases = (await r.json()).map(normalizeTask);
    const badge = document.getElementById('pool-nav-badge');
    if (badge) {
      badge.textContent = String(_poolCases.length);
      badge.style.display = _poolCases.length ? '' : 'none';
    }
  } catch (e) { /* sessiz */ }
}

export async function loadPoolPage() {
  const body = document.getElementById('pool-list-body');
  const cnt = document.getElementById('pool-count-label');
  if (body) body.innerHTML = '<div style="padding:20px;text-align:center;font-size:12px;color:var(--text-muted)">Yükleniyor…</div>';
  try {
    const r = await fetch('/api/support/pool');
    _poolCases = r.ok ? (await r.json()).map(normalizeTask) : [];
  } catch (e) { _poolCases = []; }
  updatePoolBadge();
  renderPool();
}

function renderPool() {
  const body = document.getElementById('pool-list-body');
  const cnt = document.getElementById('pool-count-label');
  if (!body) return;
  if (cnt) cnt.textContent = `${_poolCases.length} bekleyen`;
  if (!_poolCases.length) {
    body.innerHTML = '<div style="padding:28px;text-align:center;font-size:12px;color:var(--text-muted)">🫧 Havuz boş — bekleyen atanmamış talep yok.</div>';
    return;
  }
  body.innerHTML = _poolCases.map(t => {
    const age = t.startDate ? formatDateTR(t.startDate) : '';
    const anydesk = t.reporter_anydesk ? ` · 🖥 ${escapeHtml(t.reporter_anydesk)}` : '';
    return `
    <div class="task-item" style="align-items:center">
      <div style="font-size:16px">🫧</div>
      <div>
        <div class="task-title">${escapeHtml(t.title)}</div>
        <div class="task-meta">${catLabel(t.cat)}${priorityBadge(t)}${slaBadge(t)} ${firmChip(t.firm)}
          ${t.case_code ? `<span class="prio-badge low" style="background:rgba(0,229,192,.12);color:var(--accent);border-color:rgba(0,229,192,.3)">🌐 ${escapeHtml(t.case_code)}</span>` : ''}
          ${unreadBadge(t)}</div>
        <div style="font-size:9px;color:var(--text-muted);margin-top:2px">${escapeHtml(t.reporter_name||'')} &lt;${escapeHtml(t.reporter_email||'')}&gt;${anydesk} · ${age}</div>
      </div>
      <div></div>
      <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
        <button class="btn btn-primary btn-sm" style="padding:4px 12px;font-size:11px" onclick="claimCase(${t.id})">✋ Üstlen</button>
        <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" onclick="openEditTask(${t.id})">&#9998; İncele</button>
      </div>
    </div>`;
  }).join('');
}

export async function claimCase(id) {
  try {
    const r = await fetch(`/api/tasks/${id}/claim`, { method:'POST' });
    if (!r.ok) throw new Error((await r.json()).error || 'Üstlenilemedi');
    showToast('ok', '✋ Talep üstlenildi — Destek Talepleri listenizde');
    _poolCases = _poolCases.filter(t => t.id !== id);
    renderPool(); updatePoolBadge();
    await loadTasks();  // kendi listeme düşsün
  } catch (e) { showToast('err', e.message); }
}

export async function releaseCase(id) {
  if (!confirm('Bu talebi havuza geri bırakmak istediğinize emin misiniz?')) return;
  try {
    const r = await fetch(`/api/tasks/${id}/release`, { method:'POST' });
    if (!r.ok) throw new Error((await r.json()).error || 'Bırakılamadı');
    showToast('ok', '🫧 Talep havuza geri bırakıldı');
    closeEditTaskModal();
    await loadTasks(); renderFullList(state.tasks); updatePoolBadge();
  } catch (e) { showToast('err', e.message); }
}

// v5.23 — Portal case'i çözüldü olarak kapat (is_done=true → 'resolved' + kapanış maili)
// veya zaten çözülmüşse yeniden aç. Buton etiketi openEditTask'ta t.done'a göre ayarlanır.
export async function resolveCase(id) {
  const t = state.tasks.find(x => x.id === id);
  const wasDone = t && t.done;
  const msg = wasDone
    ? 'Bu talebi yeniden açmak istediğinize emin misiniz?'
    : 'Bu talebi ÇÖZÜLDÜ olarak kapatmak istiyor musunuz? Talep sahibine kapanış maili gönderilir.';
  if (!confirm(msg)) return;
  try {
    const r = await fetch(`/api/tasks/${id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ is_done: !wasDone }),
    });
    if (!r.ok) throw new Error((await r.json()).error || 'İşlem başarısız');
    showToast('ok', wasDone ? '↩ Talep yeniden açıldı' : '✓ Talep çözüldü — kullanıcıya bilgi verildi');
    closeEditTaskModal();
    await loadTasks(); renderFullList(state.tasks); updatePoolBadge();
  } catch (e) { showToast('err', e.message); }
}
