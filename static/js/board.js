// ══════════════════════════════════════════════════════════
//  board.js — Ortak Alan / Kanban (Trello benzeri) (v5.51, ESM Faz 4b)
//
//  Gerçek ESM modülü (app.js'ten çıkarıldı). main.js import edip public
//  fonksiyonları exposeAll ile window'a bağlar (inline onclick + app.js).
//  Bağımlılıklar: escapeHtml (import utils.js), state (import state.js),
//  showToast (app.js klasik → global). İç: esc (yerel HTML-escape) +
//  populateBCardAssigned/renderBCardChecklist/renderBCardComments private.
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { onClick } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — Ortak Alan (Kanban) aksiyonları (inline onclick → data-click)
onClick('openNewCardModal',     el => openNewCardModal(el.dataset.col));
onClick('setBCardCol',          el => setBCardCol(el.dataset.col));
onClick('setBCardColor',        el => setBCardColor(el.dataset.color));
onClick('addBCardChecklistItem', () => addBCardChecklistItem());
onClick('addBCardComment',      () => addBCardComment());
onClick('closeBoardCardModal',  () => closeBoardCardModal());
onClick('deleteBoardCard',      () => deleteBoardCard());
onClick('saveBoardCard',        () => saveBoardCard());

//  ORTAK ALAN (BOARD) — Trello Kanban
// ══════════════════════════════════════════════════════════
// boardCards → state.js (ESM Faz 2c-1, window.state)
// boardUsers → state.js (ESM Faz 2c-1, window.state)
const BOARD_COLS = ['todo','in_progress','review','done'];
const COL_LABELS = {todo:'Yapılacak', in_progress:'Devam Eden', review:'İnceleme', done:'Tamamlandı'};

export async function renderBoard() {
  try {
    const [cardsRes, usersRes] = await Promise.all([
      fetch('/api/board/cards'),
      fetch('/api/board/users')
    ]);
    if (!cardsRes.ok) { showToast('err','Board yuklenemedi'); return; }
    state.boardCards = await cardsRes.json();
    if (usersRes.ok) state.boardUsers = await usersRes.json();
  } catch(e) { showToast('err', e.message); return; }

  BOARD_COLS.forEach(col => {
    const cards = state.boardCards.filter(c => c.column === col);
    const el = document.getElementById('board-col-' + col);
    const countEl = document.getElementById('bc-' + col);
    if (countEl) countEl.textContent = cards.length;
    if (!el) return;
    el.innerHTML = cards.sort((a,b) => a.position - b.position).map(c => {
      const cl = c.checklist || [];
      const cld = c.checklist_done || [];
      const clDone = cld.filter(Boolean).length;
      const clTotal = cl.length;
      const clText = clTotal ? `<span class="bc-tag">✓ ${clDone}/${clTotal}</span>` : '';
      const cmtText = c.comment_count ? `<span class="bc-tag">💬 ${c.comment_count}</span>` : '';
      const assignText = c.assignee_name ? `<span class="bc-tag">@${c.assignee_name.split(' ')[0]}</span>` : '';
      const desc = c.description ? `<div class="board-card-desc">${esc(c.description)}</div>` : '';
      return `<div class="board-card" data-color="${c.color}" onclick="openBoardCardModal(${c.id})">
        <div class="board-card-title">${esc(c.title)}</div>
        ${desc}
        <div class="board-card-footer">${clText}${cmtText}${assignText}</div>
      </div>`;
    }).join('');
  });
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ── Kart Detay Modalı ──
let _bCardColor = 'yellow';
let _bCardCol = 'todo';
let _bCardChecklist = [];
let _bCardChecklistDone = [];

export async function openBoardCardModal(id) {
  const card = state.boardCards.find(c => c.id === id);
  if (!card) return;
  document.getElementById('bcard-mode').value = 'edit';
  document.getElementById('bcard-id').value = id;
  document.getElementById('bcard-title').value = card.title;
  document.getElementById('bcard-desc').value = card.description || '';
  _bCardColor = card.color || 'yellow';
  _bCardCol = card.column || 'todo';
  _bCardChecklist = [...(card.checklist || [])];
  _bCardChecklistDone = [...(card.checklist_done || [])];
  setBCardColor(_bCardColor);
  setBCardCol(_bCardCol);
  renderBCardChecklist();
  populateBCardAssigned(card.assigned_to);
  document.getElementById('bcard-delete-btn').style.display = '';
  document.getElementById('bcard-comments-section').style.display = '';
  // Yorumları yükle
  try {
    const res = await fetch(`/api/board/cards/${id}/comments`);
    if (res.ok) renderBCardComments(await res.json());
  } catch(e) {}
  document.getElementById('board-card-modal').classList.remove('hidden');
}

export function openNewCardModal(col) {
  document.getElementById('bcard-mode').value = 'create';
  document.getElementById('bcard-id').value = '';
  document.getElementById('bcard-title').value = '';
  document.getElementById('bcard-desc').value = '';
  _bCardColor = 'yellow';
  _bCardCol = col || 'todo';
  _bCardChecklist = [];
  _bCardChecklistDone = [];
  setBCardColor('yellow');
  setBCardCol(_bCardCol);
  renderBCardChecklist();
  populateBCardAssigned(null);
  document.getElementById('bcard-delete-btn').style.display = 'none';
  document.getElementById('bcard-comments-section').style.display = 'none';
  document.getElementById('bcard-comments-list').innerHTML = '';
  document.getElementById('board-card-modal').classList.remove('hidden');
}

export function closeBoardCardModal() {
  document.getElementById('board-card-modal').classList.add('hidden');
}

export function setBCardColor(c) {
  _bCardColor = c;
  document.querySelectorAll('#bcard-colors .color-pick').forEach(el => {
    el.classList.toggle('active', el.dataset.c === c);
  });
}

export function setBCardCol(c) {
  _bCardCol = c;
  document.querySelectorAll('#bcard-col-btns button').forEach(el => {
    el.classList.toggle('active-col', el.dataset.col === c);
  });
}

function populateBCardAssigned(selectedId) {
  const sel = document.getElementById('bcard-assigned');
  sel.innerHTML = '<option value="">— Kimse —</option>' +
    state.boardUsers.map(u => `<option value="${u.id}" ${u.id===selectedId?'selected':''}>${escapeHtml(u.full_name)}</option>`).join('');
}

// Checklist
function renderBCardChecklist() {
  const el = document.getElementById('bcard-checklist');
  el.innerHTML = _bCardChecklist.map((item, i) => {
    const done = _bCardChecklistDone[i] ? 'done' : '';
    const checked = _bCardChecklistDone[i] ? 'checked' : '';
    return `<div class="bd-checklist-item ${done}">
      <input type="checkbox" ${checked} onchange="toggleBCardCL(${i})">
      <span>${esc(item)}</span>
      <button style="margin-left:auto;background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:14px;" onclick="removeBCardCL(${i})">×</button>
    </div>`;
  }).join('');
}

export function toggleBCardCL(i) {
  while (_bCardChecklistDone.length < _bCardChecklist.length) _bCardChecklistDone.push(false);
  _bCardChecklistDone[i] = !_bCardChecklistDone[i];
  renderBCardChecklist();
}

export function removeBCardCL(i) {
  _bCardChecklist.splice(i, 1);
  _bCardChecklistDone.splice(i, 1);
  renderBCardChecklist();
}

export function addBCardChecklistItem() {
  const inp = document.getElementById('bcard-cl-new');
  const val = inp.value.trim();
  if (!val) return;
  _bCardChecklist.push(val);
  _bCardChecklistDone.push(false);
  inp.value = '';
  renderBCardChecklist();
}

// Yorumlar
function renderBCardComments(comments) {
  const el = document.getElementById('bcard-comments-list');
  if (!comments.length) { el.innerHTML = '<div style="font-size:11px;color:var(--text-dim);padding:4px;">Henüz yorum yok</div>'; return; }
  el.innerHTML = comments.map(c => {
    const d = new Date(c.created_at);
    const dateStr = d.toLocaleDateString('tr-TR') + ' ' + d.toLocaleTimeString('tr-TR', {hour:'2-digit',minute:'2-digit'});
    return `<div class="bd-comment">
      <div class="bd-comment-header"><span class="bd-comment-author">${esc(c.author_name)}</span><span class="bd-comment-date">${dateStr}</span></div>
      <div class="bd-comment-body">${esc(c.content)}</div>
    </div>`;
  }).join('');
}

export async function addBCardComment() {
  const id = parseInt(document.getElementById('bcard-id').value);
  const inp = document.getElementById('bcard-comment-input');
  const content = inp.value.trim();
  if (!content || !id) return;
  try {
    const res = await fetch(`/api/board/cards/${id}/comments`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content})
    });
    if (!res.ok) throw new Error((await res.json()).error || 'Hata');
    inp.value = '';
    // Yorumları tekrar yükle
    const cmtRes = await fetch(`/api/board/cards/${id}/comments`);
    if (cmtRes.ok) renderBCardComments(await cmtRes.json());
    showToast('ok', 'Yorum eklendi');
  } catch(e) { showToast('err', e.message); }
}

// Kaydet
export async function saveBoardCard() {
  const mode = document.getElementById('bcard-mode').value;
  const title = document.getElementById('bcard-title').value.trim();
  if (!title) { showToast('err', 'Başlık zorunlu'); return; }
  const assigned = document.getElementById('bcard-assigned').value;
  const body = {
    title, description: document.getElementById('bcard-desc').value,
    column: _bCardCol, color: _bCardColor,
    checklist: _bCardChecklist, checklist_done: _bCardChecklistDone,
    assigned_to: assigned ? parseInt(assigned) : null,
    firm: state.currentUser.firm || '',
  };
  try {
    let url = '/api/board/cards';
    let method = 'POST';
    if (mode === 'edit') {
      url = `/api/board/cards/${document.getElementById('bcard-id').value}`;
      method = 'PATCH';
    }
    const res = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if (!res.ok) throw new Error((await res.json()).error || 'Hata');
    closeBoardCardModal();
    await renderBoard();
    showToast('ok', mode === 'create' ? 'Kart olusturuldu' : 'Kart guncellendi');
  } catch(e) { showToast('err', e.message); }
}

// Sil
export async function deleteBoardCard() {
  const id = document.getElementById('bcard-id').value;
  if (!id || !confirm('Bu karti silmek istediginizden emin misiniz?')) return;
  try {
    const res = await fetch(`/api/board/cards/${id}`, {method:'DELETE'});
    if (!res.ok) throw new Error((await res.json()).error || 'Hata');
    closeBoardCardModal();
    await renderBoard();
    showToast('ok', 'Kart silindi');
  } catch(e) { showToast('err', e.message); }
}
