// ══════════════════════════════════════════════════════════
//  kb.js — Bilgi Bankası (v6.0)
//
//  v6.0 değişikliği: KB okuma tüm giriş yapmış rollere açık; yazma yalnız
//  director+. Liste iki modda render olur:
//    - Okuma modu (junior/senior operatör): "Görüntüle" butonu → salt-okunur
//      viewer modalı; taslak filtresi ve edit butonu gizli.
//    - Yönetim modu (director+): Mevcut editör deneyimi + arama + filtreler.
//  Arama tek fetch'in üstünde client-side; makale sayısı 100'lük ölçekte
//  server-round-trip'sizdir. 100+ olursa /api/kb'ye ?q= eklenip switch edilir.
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { FIRMS, showToast } from '../app.js';
import { onClick, onChange, onInput } from './events.js';

onClick('openKbEditor',    el => openKbEditor(el.dataset.id ? +el.dataset.id : null));
onClick('saveKbArticle',   () => saveKbArticle());
onClick('deleteKbArticle', () => deleteKbArticle());
// v6.0 — okuma modu handler'ları
onClick('openKbViewer',    el => openKbViewer(+el.dataset.id));
onClick('editFromViewer',  () => editFromViewer());
// v6.0 — arama + kategori/durum filtresi (data-input / data-change)
onInput('kbSearchDebounced', () => kbSearchDebounced());
onChange('renderKbList',     () => renderKbList());

const KB_CAT_LABELS = { genel:'Genel', 'ağ':'Ağ/İnternet', 'donanım':'Donanım', 'yazılım':'Yazılım', hesap:'Hesap/Erişim', 'diğer':'Diğer' };
let _kbArticles = [];
let _kbViewingId = null;   // salt-okunur modalda açık olan makale (editör geçişi için)
let _kbSearchT = null;

function _isDirectorUp() {
  const lvl = state.currentUser && state.currentUser.permission_level;
  return lvl === 'super_admin' || lvl === 'it_director';
}

export async function loadKb() {
  try {
    const r = await fetch('/api/kb');
    _kbArticles = r.ok ? await r.json() : [];
    renderKbList();
  } catch (e) { console.warn('KB yüklenemedi:', e); }
}

// v6.0 — search debounce (search+filter tek render fonksiyonuna gider)
export function kbSearchDebounced() {
  clearTimeout(_kbSearchT);
  _kbSearchT = setTimeout(renderKbList, 200);
}

export function renderKbList() {
  const box = document.getElementById('kb-admin-list');
  if (!box) return;

  const isDir = _isDirectorUp();
  const q = (document.getElementById('kb-search')?.value || '').trim().toLowerCase();
  const cat = document.getElementById('kb-filter-cat')?.value || '';
  const status = document.getElementById('kb-filter-status')?.value || '';

  let items = _kbArticles.slice();
  if (cat) items = items.filter(a => a.category === cat);
  if (isDir && status === 'published') items = items.filter(a => a.published);
  if (isDir && status === 'draft')     items = items.filter(a => !a.published);
  if (q) {
    items = items.filter(a =>
      (a.title || '').toLowerCase().includes(q) ||
      (a.keywords || '').toLowerCase().includes(q) ||
      (a.body || '').toLowerCase().includes(q)
    );
  }

  if (!items.length) {
    const emptyMsg = isDir
      ? (q || cat || status
          ? 'Arama ile eşleşen makale yok.'
          : 'Henüz makale yok. “＋ Yeni Makale” ile ekleyin.')
      : (q || cat
          ? 'Arama ile eşleşen yayınlanmış makale yok.'
          : 'Henüz yayınlanmış makale yok. Yönetim eklediğinde burada görünür.');
    box.innerHTML = `<div style="padding:26px;text-align:center;color:var(--text-muted);font-size:12.5px">${escapeHtml(emptyMsg)}</div>`;
    return;
  }

  box.innerHTML = items.map(a => {
    const firm = a.firm ? ((FIRMS[a.firm] && FIRMS[a.firm].label) || a.firm) : 'Tüm firmalar';
    // Yayın rozeti yalnız director+ için gösteriliyor — okuyucuya taslak/yayın
    // kavramı bulanıklık yaratır, üstelik listede zaten yayınlananlar dönüyor.
    const pub = isDir
      ? (a.published
          ? '<span class="prio-badge low" style="background:rgba(0,229,192,.12);color:var(--accent);border-color:rgba(0,229,192,.3)">✓ Yayında</span>'
          : '<span class="prio-badge" style="background:var(--surface2);color:var(--text-muted);border-color:var(--border2)">Taslak</span>')
      : '';
    const actionBtn = isDir
      ? `<button class="btn btn-outline btn-sm" style="padding:2px 10px;font-size:10px" data-click="openKbEditor" data-id="${a.id}">&#9998; Düzenle</button>`
      : `<button class="btn btn-outline btn-sm" style="padding:2px 10px;font-size:10px" data-click="openKbViewer" data-id="${a.id}">Görüntüle</button>`;
    const click = isDir ? 'openKbEditor' : 'openKbViewer';
    return `<div class="task-item" style="align-items:center;cursor:pointer" data-click="${click}" data-id="${a.id}">
      <div style="font-size:16px">📄</div>
      <div>
        <div class="task-title">${escapeHtml(a.title)}</div>
        <div class="task-meta">${escapeHtml(KB_CAT_LABELS[a.category]||a.category)} · ${escapeHtml(firm)} ${pub}
          <span style="color:var(--text-muted);font-size:10px">· 👁 ${a.view_count} · 👍 ${a.helpful_yes} 👎 ${a.helpful_no}</span></div>
      </div>
      <div></div>
      <div>${actionBtn}</div>
    </div>`;
  }).join('');
}

// v6.0 — Salt-okunur viewer. Non-director'ün birincil okuma yolu; director da
// "önce oku" davranışı için kullanabilir (rol UI'sında düzenle butonu görünür).
export function openKbViewer(id) {
  const a = _kbArticles.find(x => x.id === id);
  if (!a) return;
  _kbViewingId = id;
  const firm = a.firm ? ((FIRMS[a.firm] && FIRMS[a.firm].label) || a.firm) : 'Tüm firmalar';
  document.getElementById('kb-view-title').textContent = a.title || '—';
  document.getElementById('kb-view-meta').textContent =
    `${KB_CAT_LABELS[a.category] || a.category} · ${firm} · 👁 ${a.view_count} · 👍 ${a.helpful_yes} 👎 ${a.helpful_no}`;
  document.getElementById('kb-view-body').textContent = a.body || '(içerik boş)';
  const kwWrap = document.getElementById('kb-view-keywords');
  if (a.keywords) {
    document.getElementById('kb-view-kw').textContent = a.keywords;
    kwWrap.style.display = '';
  } else {
    kwWrap.style.display = 'none';
  }
  document.getElementById('kb-viewer-modal').classList.remove('hidden');
}

export function editFromViewer() {
  if (_kbViewingId == null) return;
  document.getElementById('kb-viewer-modal').classList.add('hidden');
  openKbEditor(_kbViewingId);
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
