// ══════════════════════════════════════════════════════════
//  admin.js — Kullanıcı yönetimi: tablo + davet + düzenleme (v5.52, ESM Faz 4c)
//
//  Gerçek ESM modülü (app.js'ten çıkarıldı). main.js import edip public
//  fonksiyonları exposeAll ile window'a bağlar (inline onclick + app.js).
//  Bağımlılıklar: escapeHtml (import utils.js), state (import state.js),
//  showToast + closeModal (app.js klasik → global). renderUserStats/
//  renderInvitations MODÜL-PRIVATE.
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { onClick } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — kullanıcı yönetimi aksiyonları (inline onclick → data-click)
onClick('openInviteModal',    () => openInviteModal());
onClick('sendInvite',         () => sendInvite());
onClick('saveEditUser',       () => saveEditUser());
onClick('closeEditUserModal', () => closeEditUserModal());
// generated-string (davet/kullanıcı satırı)
onClick('resendInvite', el => resendInvite(+el.dataset.id));
onClick('cancelInvite', el => cancelInvite(+el.dataset.id));
onClick('openEditUser', el => openEditUser(+el.dataset.id));
onClick('closeInviteModal',   () => closeModal());

//  ADMIN — KULLANICI TABLOSU (API'den)
// ══════════════════════════════════════════════════════════
// INVITATIONS → state.js (ESM Faz 2c-1, window.state)
export async function loadAndRenderUsers() {
  try {
    const [uRes, iRes] = await Promise.all([fetch('/api/admin/users'), fetch('/api/admin/invitations')]);
    if (!uRes.ok) { document.getElementById('user-tbody').innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">Yetkisiz erişim</td></tr>'; return; }
    state.USERS = await uRes.json();
    state.INVITATIONS = iRes.ok ? await iRes.json() : [];
    renderUserTable();
    renderUserStats();
    renderInvitations();
  } catch(e) { showToast('err', 'Kullanıcılar yüklenemedi: ' + e.message); }
}

function renderUserStats() {
  const total = state.USERS.length;
  const active = state.USERS.filter(u => u.active).length;
  const pending = state.INVITATIONS.length;
  const o365 = state.USERS.filter(u => u.o365_linked).length;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-active').textContent = active;
  document.getElementById('stat-pending').textContent = pending;
  document.getElementById('stat-o365').textContent = o365;

  // Yetki dağılımı
  const permCounts = {};
  const permLabels = {super_admin:'Super Admin', it_director:'IT Müdürü', it_manager:'IT Yöneticisi', it_specialist:'IT Specialist', junior:'Junior'};
  const permColors = {super_admin:'var(--accent)', it_director:'var(--accent-gold, #f5b400)', it_manager:'var(--accent3)', it_specialist:'var(--accent2)', junior:'var(--text-muted)'};
  state.USERS.forEach(u => { const p = u.permission_level || 'junior'; permCounts[p] = (permCounts[p]||0)+1; });
  const maxP = Math.max(...Object.values(permCounts), 1);
  document.getElementById('perm-dist-body').innerHTML = Object.entries(permCounts).map(([k,v]) =>
    `<div class="progress-wrap"><div class="progress-label"><span>${permLabels[k]||k}</span><span style="color:${permColors[k]||'var(--text-muted)'}">${v}</span></div><div class="progress-bar"><div class="progress-fill" style="width:${(v/maxP)*100}%;background:${permColors[k]||'var(--text-muted)'}"></div></div></div>`
  ).join('');
}

function renderInvitations() {
  const tbody = document.getElementById('inv-tbody');
  const empty = document.getElementById('inv-empty');
  if (!state.INVITATIONS.length) { tbody.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';
  tbody.innerHTML = state.INVITATIONS.map(inv => {
    const expired = new Date(inv.expires_at) < new Date();
    const expLabel = expired ? '<span style="color:var(--red)">Süresi dolmuş</span>' : new Date(inv.expires_at).toLocaleDateString('tr-TR');
    return `<tr>
      <td style="font-size:12px">${escapeHtml(inv.full_name || '—')}</td>
      <td style="font-size:11px;font-family:'IBM Plex Mono',monospace">${escapeHtml(inv.email)}</td>
      <td>${permBadge(inv.role === 'Super Admin' ? 'super_admin' : inv.role === 'IT Müdürü' ? 'it_director' : inv.role === 'IT Yöneticisi' ? 'it_manager' : inv.role === 'IT Specialist' ? 'it_specialist' : 'junior')}</td>
      <td>${firmChip(inv.firm)}</td>
      <td style="font-size:11px">${expLabel}</td>
      <td style="display:flex;gap:6px">
        <button class="btn btn-outline btn-sm" data-click="resendInvite" data-id="${inv.id}" title="Yeniden Gönder">&#8634; Gönder</button>
        <button class="btn btn-outline btn-sm" style="color:var(--red);border-color:var(--red)" data-click="cancelInvite" data-id="${inv.id}" title="İptal Et">&#10005; İptal</button>
      </td>
    </tr>`;
  }).join('');
}

function permBadge(level) {
  const map = {super_admin:['Super Admin','var(--accent)'], it_director:['IT Müdürü','var(--accent-gold, #f5b400)'], it_manager:['IT Yöneticisi','var(--accent3)'], it_specialist:['IT Specialist','var(--accent2)'], junior:['Junior','var(--text-muted)']};
  const [label, color] = map[level] || map.junior;
  return `<span style="font-size:10px;padding:2px 8px;border-radius:12px;border:1px solid ${color};color:${color};font-family:'IBM Plex Mono',monospace">${label}</span>`;
}

export function renderUserTable() {
  document.getElementById('user-tbody').innerHTML = state.USERS.map(u => `
    <tr>
      <td><div style="font-weight:600;font-size:12px">${escapeHtml(u.full_name)}</div><div style="font-size:10px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">${escapeHtml(u.username)}</div></td>
      <td><span style="font-size:11px;color:var(--text-muted)">${escapeHtml(u.role || '—')}</span></td>
      <td>${permBadge(u.permission_level)}</td>
      <td>${firmChip(u.firm)}</td>
      <td><span class="status-dot ${u.active?'active':'inactive'}"></span><span style="font-size:11px">${u.active?'Aktif':'Pasif'}</span></td>
      <td style="display:flex;gap:6px">
        <button class="btn btn-outline btn-sm" data-click="openEditUser" data-id="${u.id}">&#9998; Düzenle</button>
      </td>
    </tr>`).join('');
}

export async function resendInvite(id) {
  try {
    const res = await fetch(`/api/admin/invitations/${id}/resend`, {method:'POST'});
    const data = await res.json();
    if (data.ok) { showToast('ok','Davet maili yeniden gönderildi'); loadAndRenderUsers(); }
    else showToast('err', data.error || 'Gönderilemedi');
  } catch(e) { showToast('err', e.message); }
}
export async function cancelInvite(id) {
  if (!confirm('Bu daveti iptal etmek istediğinize emin misiniz?')) return;
  try {
    const res = await fetch(`/api/admin/invitations/${id}`, {method:'DELETE'});
    const data = await res.json();
    if (data.ok) { showToast('ok','Davet iptal edildi'); loadAndRenderUsers(); }
    else showToast('err', data.error || 'İptal edilemedi');
  } catch(e) { showToast('err', e.message); }
}

// ══════════════════════════════════════════════════════════
//  INVITE MODAL
// ══════════════════════════════════════════════════════════
export function openInviteModal() {
  // IT Müdürü seçeneği sadece Super Admin'e görünür
  const dirOpt = document.querySelector('#inv-perm option[value="it_director"]');
  if (dirOpt) dirOpt.style.display = (state.currentUser.permission_level === 'super_admin') ? '' : 'none';
  document.getElementById('invite-modal').classList.remove('hidden');
}
function closeModal() { document.getElementById('invite-modal').classList.add('hidden'); }
export async function sendInvite() {
  const name  = document.getElementById('inv-name').value.trim();
  const email = document.getElementById('inv-email').value.trim();
  if (!name || !email) { showToast('err','Ad ve mail zorunludur'); return; }
  try {
    const res = await fetch('/api/admin/invite', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ full_name:name, email, permission_level:document.getElementById('inv-perm').value, firm:document.getElementById('inv-firm').value })
    });
    const data = await res.json();
    if (data.ok) { closeModal(); showToast('ok',`Davet maili ${email} adresine gönderildi ✓`); loadAndRenderUsers(); }
    else showToast('err', data.error || 'Gönderilemedi');
  } catch(e) { showToast('err', e.message); }
}

//  EDIT USER MODAL — API bağlı
// ══════════════════════════════════════════════════════════
export function openEditUser(id) {
  id = parseInt(id);
  const u = state.USERS.find(u => u.id === id); if (!u) return;
  document.getElementById('edit-user-id').value       = id;
  document.getElementById('edit-user-name').value     = u.full_name || '';
  document.getElementById('edit-user-username').value = u.username  || '';
  document.getElementById('edit-user-email').value    = u.email     || '';
  document.getElementById('edit-user-role').value     = u.role       || '';
  document.getElementById('edit-user-perm').value     = u.permission_level || 'junior';
  document.getElementById('edit-user-firm').value     = u.firm      || '';
  document.getElementById('edit-user-status').value   = u.active ? 'active' : 'inactive';

  // IT Yöneticisi super_admin ve IT Müdürü seçeneklerini göremez
  const permSel = document.getElementById('edit-user-perm');
  const saOpt = permSel.querySelector('option[value="super_admin"]');
  const dirOpt = permSel.querySelector('option[value="it_director"]');
  const canAssignTop = (state.currentUser.permission_level === 'super_admin');
  if (saOpt) saOpt.style.display = canAssignTop ? '' : 'none';
  if (dirOpt) dirOpt.style.display = canAssignTop ? '' : 'none';
  // IT Müdürü düzenleniyorsa ve ben SA değilsem modalı açma
  if (u.permission_level === 'it_director' && !canAssignTop) {
    showToast('err', 'IT Müdürü kullanıcısını düzenleme yetkiniz yok');
    return;
  }
  // Super Admin düzenleniyorsa ve ben SA değilsem modalı açma
  if (u.permission_level === 'super_admin' && state.currentUser.permission_level !== 'super_admin') {
    showToast('err', 'Super Admin kullanıcısını düzenleme yetkiniz yok');
    return;
  }
  // Board erişim checkbox
  document.getElementById('edit-user-board-access').checked = !!u.can_access_board;
  // Board toggle sadece super_admin'e görünür
  document.getElementById('edit-user-board-group').style.display = (state.currentUser.permission_level === 'super_admin') ? '' : 'none';
  document.getElementById('edit-user-modal').classList.remove('hidden');
}
export async function saveEditUser() {
  const id = parseInt(document.getElementById('edit-user-id').value);
  const status = document.getElementById('edit-user-status').value;
  const perm = document.getElementById('edit-user-perm').value;
  const body = {
    permission_level: perm,
    role:     document.getElementById('edit-user-role').value,
    firm:     document.getElementById('edit-user-firm').value,
    active:   status === 'active',
  };
  // Board erişim — sadece super_admin gönderebilir
  if (state.currentUser.permission_level === 'super_admin') {
    body.can_access_board = document.getElementById('edit-user-board-access').checked;
  }
  try {
    const res = await fetch(`/api/admin/users/${id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error((await res.json()).error || 'API hatası');
    closeEditUserModal();
    await loadAndRenderUsers();
    showToast('ok', 'Kullanıcı güncellendi ✓');
  } catch(e) { showToast('err', e.message); }
}
export function closeEditUserModal() {
  document.getElementById('edit-user-modal').classList.add('hidden');
}
