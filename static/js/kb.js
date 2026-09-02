// ══════════════════════════════════════════════════════════
//  kb.js — Bilgi Bankası (v5.63, ESM Faz 4f-3)
//
//  IT bilgi bankası makale yönetimi (liste + editör modal + CRUD). app.js'ten
//  çıkarıldı. main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//
//  Bağımlılıklar: escapeHtml (utils import), state (import). FIRMS/showToast
//  app.js klasik → bare global (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { onClick } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — bilgi bankası aksiyonları (inline onclick → data-click)
// openKbEditor: statik "yeni makale" (data-id yok → null); liste satırı data-id verir.
onClick('openKbEditor',    el => openKbEditor(el.dataset.id ? +el.dataset.id : null));
onClick('saveKbArticle',   () => saveKbArticle());
onClick('deleteKbArticle', () => deleteKbArticle());

const KB_CAT_LABELS = { genel:'Genel', 'ağ':'Ağ/İnternet', 'donanım':'Donanım', 'yazılım':'Yazılım', hesap:'Hesap/Erişim', 'diğer':'Diğer' };
let _kbArticles = [];

export async function loadKb() {
  try {
    const r = await fetch('/api/kb');
    _kbArticles = r.ok ? await r.json() : [];
    renderKbAdminList();
  } catch (e) { console.warn('KB yüklenemedi:', e); }
}

function renderKbAdminList() {
  const box = document.getElementById('kb-admin-list');
  if (!box) return;
  if (!_kbArticles.length) {
    box.innerHTML = '<div style="padding:26px;text-align:center;color:var(--text-muted);font-size:12.5px">Henüz makale yok. “＋ Yeni Makale” ile ekleyin.</div>';
    return;
  }
  box.innerHTML = _kbArticles.map(a => {
    const firm = a.firm ? ((FIRMS[a.firm] && FIRMS[a.firm].label) || a.firm) : 'Tüm firmalar';
    const pub = a.published
      ? '<span class="prio-badge low" style="background:rgba(0,229,192,.12);color:var(--accent);border-color:rgba(0,229,192,.3)">✓ Yayında</span>'
      : '<span class="prio-badge" style="background:var(--surface2);color:var(--text-muted);border-color:var(--border2)">Taslak</span>';
    return `<div class="task-item" style="align-items:center;cursor:pointer" onclick="openKbEditor(${a.id})">
      <div style="font-size:16px">📄</div>
      <div>
        <div class="task-title">${escapeHtml(a.title)}</div>
        <div class="task-meta">${escapeHtml(KB_CAT_LABELS[a.category]||a.category)} · ${escapeHtml(firm)} ${pub}
          <span style="color:var(--text-muted);font-size:10px">· 👁 ${a.view_count} · 👍 ${a.helpful_yes} 👎 ${a.helpful_no}</span></div>
      </div>
      <div></div>
      <div><button class="btn btn-outline btn-sm" style="padding:2px 10px;font-size:10px" onclick="event.stopPropagation();openKbEditor(${a.id})">&#9998; Düzenle</button></div>
    </div>`;
  }).join('');
}

function _kbPopulateFirmSelect(selected) {
  const sel = document.getElementById('kb-edit-firm');
  if (!sel) return;
  const isSA = state.currentUser.permission_level === 'super_admin';
  const opts = [];
  if (isSA) {
    opts.push('<option value="">Tüm firmalar (global)</option>');
    Object.entries(FIRMS).forEach(([slug, f]) => opts.push(`<option value="${slug}">${escapeHtml(f.label || slug)}</option>`));
  } else {
    // director: yönettiği firmalar (mevcut makalelerden + kendi firması)
    const scope = new Set(_kbArticles.map(a => a.firm).filter(Boolean));
    if (state.currentUser.firm) scope.add(state.currentUser.firm);
    (state.currentUser.managed_firm_slugs || []).forEach(s => scope.add(s));
    [...scope].forEach(slug => opts.push(`<option value="${slug}">${escapeHtml((FIRMS[slug] && FIRMS[slug].label) || slug)}</option>`));
  }
  sel.innerHTML = opts.join('');
  if (selected != null) sel.value = selected;
}

export function openKbEditor(id) {
  const editing = id != null;
  const a = editing ? _kbArticles.find(x => x.id === id) : null;
  document.getElementById('kb-editor-title').textContent = editing ? 'Makaleyi Düzenle' : 'Yeni Makale';
  document.getElementById('kb-edit-id').value = editing ? id : '';
  _kbPopulateFirmSelect(a ? a.firm : null);
  document.getElementById('kb-edit-cat').value = a ? a.category : 'genel';
  document.getElementById('kb-edit-title').value = a ? a.title : '';
  document.getElementById('kb-edit-keywords').value = a ? a.keywords : '';
  document.getElementById('kb-edit-body').value = a ? a.body : '';
  document.getElementById('kb-edit-published').checked = a ? a.published : false;
  document.getElementById('kb-edit-delete').style.display = editing ? '' : 'none';
  document.getElementById('kb-editor-modal').classList.remove('hidden');
}

export async function saveKbArticle() {
  const id = document.getElementById('kb-edit-id').value;
  const title = document.getElementById('kb-edit-title').value.trim();
  if (!title) { showToast('err', 'Başlık boş olamaz'); return; }
  const body = {
    title,
    firm: document.getElementById('kb-edit-firm').value,
    category: document.getElementById('kb-edit-cat').value,
    keywords: document.getElementById('kb-edit-keywords').value.trim(),
    body: document.getElementById('kb-edit-body').value,
    published: document.getElementById('kb-edit-published').checked,
  };
  try {
    const url = id ? `/api/kb/${id}` : '/api/kb';
    const method = id ? 'PATCH' : 'POST';
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || 'Kaydedilemedi');
    showToast('ok', id ? 'Makale güncellendi' : 'Makale eklendi');
    document.getElementById('kb-editor-modal').classList.add('hidden');
    loadKb();
  } catch (e) { showToast('err', e.message); }
}

export async function deleteKbArticle() {
  const id = document.getElementById('kb-edit-id').value;
  if (!id || !confirm('Bu makaleyi silmek istediğinize emin misiniz?')) return;
  try {
    const res = await fetch(`/api/kb/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();
    showToast('ok', 'Makale silindi');
    document.getElementById('kb-editor-modal').classList.add('hidden');
    loadKb();
  } catch (e) { showToast('err', 'Silinemedi'); }
}
