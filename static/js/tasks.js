// ══════════════════════════════════════════════════════════
//  tasks.js — Görev işlemleri (v5.56, ESM Faz 4d: ekle/toggle + edit modal + full list + checklist)
//
//  Gerçek ESM modülü (app.js'ten çıkarılıyor; Faz 4d alt-adımlarında büyüyecek).
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//  Bağımlılıklar: state (import). showToast/buildNotifications/renderFullList/
//  showPage app.js klasik → bare global (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';

// ══════════════════════════════════════════════════════════
//  API — GÖREV TOGGLE (checkbox)
// ══════════════════════════════════════════════════════════
export async function apiToggleTask(id) {
  const t = state.tasks.find(t => t.id === id); if (!t) return;
  const newDone = !t.done;
  // v5.0 — server `date.today()` kullanır (Karar 2 = B). Frontend month/year göndermez,
  // server bugünün period_key'ini hesaplar (Günlük/Haftalık/Aylık/Yıllık).
  try {
    const res = await fetch(`/api/tasks/${id}`, {
      method: 'PATCH', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({is_done: newDone})
    });
    if (!res.ok) throw new Error('API hatası');
    const updated = await res.json();
    const normalized = normalizeTask(updated);

    // Rutin görev tamamlandığında backend is_done=false döner (sıfırlandı)
    // Kullanıcıya kısa süre "tamamlandı" göster, sonra yeni deadline ile güncelle
    const wasRoutineComplete = newDone && t.cat === 'routine' && t.period !== 'Tek Seferlik';
    if (wasRoutineComplete) {
      // Gerçek veriyle hemen güncelle — geçici done gösterme
      Object.assign(t, normalized);
      renderDashboardTaskList();
      renderFullList(state.tasks);
      renderDashUpcoming();
      buildNotifications();
      if (document.getElementById('page-scheduled')?.classList.contains('active')) renderScheduledPage();
      if (document.getElementById('page-projects')?.classList.contains('active')) renderProjectsPage();
      const nextStr = normalized.next_due ? formatDateTR(normalized.next_due) : '?';
      showToast('ok', `✓ Tamamlandı — sonraki: ${nextStr}`);
    } else {
      Object.assign(t, normalized);
      renderDashboardTaskList();
      renderFullList(state.tasks);
      renderDashUpcoming();
      buildNotifications();
      if (document.getElementById('page-scheduled')?.classList.contains('active')) renderScheduledPage();
      if (document.getElementById('page-projects')?.classList.contains('active')) renderProjectsPage();
      if (newDone) showToast('ok', '✓ Tamamlandı');
    }
  } catch(e) { showToast('err', 'Güncelleme başarısız: ' + e.message); }
}

// ══════════════════════════════════════════════════════════
//  API — GÖREV EKLE
// ══════════════════════════════════════════════════════════
export async function addTask() {
  const title = document.getElementById('new-title').value.trim();
  const firm  = document.getElementById('new-firm').value;
  if (!title) { showToast('err','Görev başlığı boş olamaz'); return; }
  if (!firm)  { showToast('err','Firma seçmediniz'); return; }
  const cat = document.getElementById('new-cat').value;
  const backupFile = document.getElementById('backup-file').files[0];
  // v4.3 — atama modu: director+ başka kullanıcıyı görüntülüyorsa görev ona atanır
  const isDirectorUp = state.currentUser.permission_level === 'super_admin' || state.currentUser.permission_level === 'it_director';
  const assignTo = (isDirectorUp && state.selectedUserId && state.selectedUserId !== state.currentUser.id) ? state.selectedUserId : null;
  const mgrNote = isDirectorUp ? (document.getElementById('new-manager-note')?.value || '').trim() : '';
  let body, fetchOpts;
  if (cat === 'backup' && backupFile) {
    const fd = new FormData();
    fd.append('title',    title);
    fd.append('category', cat);
    fd.append('period',   document.getElementById('new-period').value);
    fd.append('firm',     firm);
    fd.append('team',     document.getElementById('new-team').value);
    fd.append('notes',    document.getElementById('new-notes').value);
    fd.append('deadline', document.getElementById('new-deadline').value || '');
    fd.append('backup_file', backupFile);
    fd.append('backup_device', document.getElementById('backup-device')?.value || '');
    if (assignTo) fd.append('user_id', assignTo);
    if (mgrNote) fd.append('manager_note', mgrNote);
    fetchOpts = { method:'POST', body: fd };
  } else {
    const clItems = _getNewChecklistItems();
    body = {
      title, category: cat,
      period:   document.getElementById('new-period').value,
      firm,     team: document.getElementById('new-team').value,
      notes:    document.getElementById('new-notes').value,
      deadline: document.getElementById('new-deadline').value || null,
      checklist: clItems,
    };
    if (cat === 'support') body.priority = document.getElementById('new-priority')?.value || 'orta';
    if (assignTo) body.user_id = assignTo;
    if (mgrNote) body.manager_note = mgrNote;
    fetchOpts = { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) };
  }
  try {
    const btn = document.querySelector('#page-add .btn-primary');
    if (btn) { btn.disabled = true; btn.textContent = 'Kaydediliyor...'; }
    const res  = await fetch('/api/tasks', fetchOpts);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Kayıt hatası');
    state.tasks.unshift(normalizeTask(data));
    // Formu temizle
    document.getElementById('new-title').value = '';
    document.getElementById('new-start').value = TODAY;
    document.getElementById('new-deadline').value = '';
    document.getElementById('new-notes').value = '';
    document.getElementById('backup-file').value = '';
    document.getElementById('upload-filename').style.display = 'none';
    document.getElementById('upload-zone').classList.remove('has-file');
    document.getElementById('new-cat').value = 'routine';
    document.getElementById('checklist-items').innerHTML = '';
    document.getElementById('new-checklist-item').value = '';
    onCatChange();
    // Manager note alanını temizle
    const mnInput = document.getElementById('new-manager-note');
    if (mnInput) mnInput.value = '';
    let okMsg;
    if (cat === 'backup') okMsg = 'Config Backup kaydedildi ✓';
    else if (assignTo) {
      const u = state.firmUsers.find(u => u.id === assignTo);
      okMsg = `✓ ${u ? u.full_name : 'Kullanıcı'} kişisine görev atandı`;
    } else okMsg = 'Görev eklendi ✓';
    showToast('ok', okMsg);
    // v5.21 — Kullanıcının 'Yeni Görev'e girmeden önce olduğu menüye geri dön
    // (eskiden kategori ne olursa olsun hep 'Anlık Görevler'e atıyordu). Config
    // backup yeni eklendiyse dosya listesini görmek mantıklı → 'backups'.
    showPage(cat === 'backup' ? 'backups' : (_addReturnPage || 'tasks'));
  } catch(e) {
    showToast('err', 'Hata: ' + e.message);
  } finally {
    const btn = document.querySelector('#page-add .btn-primary');
    if (btn) { btn.disabled = false; btn.textContent = 'Görevi Kaydet'; }
  }
}

// ── ESM Faz 4d-2: Edit Task Modal + Case Mesajları + Backup Dosya ──
//  EDIT TASK MODAL — API bağlı
// ══════════════════════════════════════════════════════════
export function openEditTask(id) {
  const t = state.tasks.find(t => t.id === id); if (!t) return;
  document.getElementById('edit-task-id').value       = id;
  document.getElementById('edit-task-title').value    = t.title;
  document.getElementById('edit-task-cat').value      = t.cat;
  document.getElementById('edit-task-period').value   = t.period;
  document.getElementById('edit-task-deadline').value = t.deadline || '';
  document.getElementById('edit-task-done').value     = t.done ? 'true' : 'false';
  document.getElementById('edit-task-notes').value    = t.notes || '';
  // v4.3 — IT Müdürü notu alanı: director+ düzenleyebilir, diğerleri sadece görür
  const mnGroup = document.getElementById('edit-manager-note-group');
  const mnArea  = document.getElementById('edit-task-manager-note');
  const isDirectorUp = state.currentUser.permission_level === 'super_admin' || state.currentUser.permission_level === 'it_director';
  if (mnGroup && mnArea) {
    mnArea.value = t.manager_note || '';
    // director+ her zaman görür; diğer kullanıcılar sadece not varsa görür (salt okunur)
    const hasNote = !!(t.manager_note && t.manager_note.trim());
    if (isDirectorUp) {
      mnGroup.classList.remove('hidden');
      mnArea.readOnly = false;
    } else if (hasNote) {
      mnGroup.classList.remove('hidden');
      mnArea.readOnly = true;
    } else {
      mnGroup.classList.add('hidden');
    }
  }
  const prRow = document.getElementById('edit-priority-row');
  if (prRow) prRow.classList.toggle('hidden', t.cat !== 'support');
  // v5.37 — Destek: manuel son tarih gizli, SLA notu görünür
  document.getElementById('edit-deadline-field')?.classList.toggle('hidden', t.cat === 'support');
  document.getElementById('edit-sla-deadline-note')?.classList.toggle('hidden', t.cat !== 'support');
  const prSel = document.getElementById('edit-task-priority');
  if (prSel) prSel.value = (t.priority || 'orta');
  document.getElementById('edit-task-firm').value     = t.firm;
  updateEditTeamOptions();
  setTimeout(() => { document.getElementById('edit-task-team').value = t.team; }, 20);

  // Son tamamlanma (rutin görevler)
  const lcRow = document.getElementById('edit-last-completed-row');
  const lcVal = document.getElementById('edit-last-completed-val');
  if (lcRow && t.cat === 'routine' && t.last_completed) {
    const d = new Date(t.last_completed);
    lcVal.textContent = d.toLocaleDateString('tr-TR', {day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'});
    lcRow.classList.remove('hidden');
  } else if (lcRow) { lcRow.classList.add('hidden'); }

  // Checklist
  const clSection = document.getElementById('edit-checklist-section');
  if (clSection) {
    const isRoutine = t.cat === 'routine';
    const isProject = t.cat === 'project';
    clSection.classList.toggle('hidden', !(isRoutine || isProject));
    if (isRoutine || isProject) {
      _loadEditChecklist(t.checklist || [], t.checklist_done || []);
    }
  }

  // Backup paneli
  const backupPanel = document.getElementById('edit-backup-panel');
  if (backupPanel) {
    backupPanel.classList.toggle('hidden', t.cat !== 'backup');
    if (t.cat === 'backup') loadTaskBackups(id);
  }

  // v5.15 Faz B — Portal yazışması (yalnız portal kaynaklı case'lerde)
  const caseSec = document.getElementById('edit-case-section');
  if (caseSec) {
    const isPortal = t.source === 'portal' && t.case_code;
    caseSec.classList.toggle('hidden', !isPortal);
    // v5.19 — portal case'te modalı yatay 2-sütun geniş moda al
    document.getElementById('edit-task-modal-box')?.classList.toggle('case-wide', !!isPortal);
    if (isPortal) {
      document.getElementById('edit-case-code').textContent = t.case_code;
      document.getElementById('edit-case-reporter').textContent =
        `${t.reporter_name || ''} <${t.reporter_email || ''}>` + (t.reporter_anydesk ? ` · 🖥 AnyDesk: ${t.reporter_anydesk}` : '');
      // Havuza Bırak: yalnız atanmış (sahibi olan) case'te göster
      const relBtn = document.getElementById('edit-case-release');
      if (relBtn) relBtn.style.display = t.user_id ? '' : 'none';
      // v5.23 — Çöz/Kapat butonu etiketi duruma göre
      const resBtn = document.getElementById('edit-case-resolve');
      if (resBtn) {
        resBtn.innerHTML = t.done ? '↩ Yeniden Aç' : '✓ Çözüldü &amp; Kapat';
        resBtn.className = t.done ? 'btn btn-outline btn-sm' : 'btn btn-primary btn-sm';
      }
      _caseTab = 'it';
      caseTab('it');
      loadCaseMessages(id);
    }
  }

  // Tamamlandı butonunu duruma göre güncelle
  const completeBtn = document.getElementById('edit-complete-btn');
  if (completeBtn) {
    if (t.done) {
      completeBtn.textContent = '✓ Zaten Tamamlandı';
      completeBtn.style.opacity = '.45';
      completeBtn.style.cursor  = 'default';
      completeBtn.onclick = null;
    } else {
      completeBtn.textContent = '✓ Tamamlandı';
      completeBtn.style.opacity = '1';
      completeBtn.style.cursor  = 'pointer';
      completeBtn.onclick = saveAndCompleteTask;
    }
  }

  document.getElementById('edit-task-modal').classList.remove('hidden');
}
export function updateEditTeamOptions() {
  const firm = document.getElementById('edit-task-firm').value;
  const sel  = document.getElementById('edit-task-team');
  sel.innerHTML = '';
  if (FIRMS[firm]) FIRMS[firm].teams.forEach(name => {
    const o = document.createElement('option'); o.value = name; o.textContent = name; sel.appendChild(o);
  });
}
export async function saveEditTask() {
  const id = parseInt(document.getElementById('edit-task-id').value);
  const body = {
    title:    document.getElementById('edit-task-title').value.trim(),
    category: document.getElementById('edit-task-cat').value,
    period:   document.getElementById('edit-task-period').value,
    firm:     document.getElementById('edit-task-firm').value,
    team:     document.getElementById('edit-task-team').value,
    deadline: document.getElementById('edit-task-deadline').value || null,
    is_done:  document.getElementById('edit-task-done').value === 'true',
    notes:    document.getElementById('edit-task-notes').value,
  };
  if (body.category === 'support') body.priority = document.getElementById('edit-task-priority')?.value || 'orta';
  // v4.3 — director+ ise manager_note gönder
  const isDirectorUp = state.currentUser.permission_level === 'super_admin' || state.currentUser.permission_level === 'it_director';
  if (isDirectorUp) {
    const mn = document.getElementById('edit-task-manager-note');
    if (mn) body.manager_note = mn.value || '';
  }
  // Checklist verisi (rutin görevlerde)
  const clSection = document.getElementById('edit-checklist-section');
  if (clSection && !clSection.classList.contains('hidden')) {
    const { items, doneArr } = _getEditChecklistData();
    body.checklist      = items;
    body.checklist_done = doneArr;
  }
  if (!body.title) { showToast('err','Başlık boş olamaz'); return; }
  try {
    const res = await fetch(`/api/tasks/${id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error((await res.json()).error || 'API hatası');
    const updated = await res.json();
    const idx = state.tasks.findIndex(t => t.id === id);
    if (idx > -1) state.tasks[idx] = normalizeTask(updated);
    closeEditTaskModal();
    renderDashboardTaskList();
    renderFullList(state.tasks);
    renderDashUpcoming();
    buildNotifications();
    showToast('ok', 'Görev güncellendi ✓');
  } catch(e) { showToast('err', 'Güncelleme hatası: ' + e.message); }
}
export async function saveAndCompleteTask() {
  const id = parseInt(document.getElementById('edit-task-id').value);
  const t  = state.tasks.find(t => t.id === id);
  if (!t) return;
  const body = {
    title:    document.getElementById('edit-task-title').value.trim(),
    category: document.getElementById('edit-task-cat').value,
    period:   document.getElementById('edit-task-period').value,
    firm:     document.getElementById('edit-task-firm').value,
    team:     document.getElementById('edit-task-team').value,
    deadline: document.getElementById('edit-task-deadline').value || null,
    notes:    document.getElementById('edit-task-notes').value,
    is_done:  true,
    month:    new Date().getMonth() + 1,
    year:     new Date().getFullYear(),
  };
  if (body.category === 'support') body.priority = document.getElementById('edit-task-priority')?.value || 'orta';
  const clSection = document.getElementById('edit-checklist-section');
  if (clSection && !clSection.classList.contains('hidden')) {
    const { items, doneArr } = _getEditChecklistData();
    body.checklist      = items;
    body.checklist_done = doneArr;
  }
  if (!body.title) { showToast('err','Başlık boş olamaz'); return; }
  try {
    const res = await fetch(`/api/tasks/${id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error((await res.json()).error || 'API hatası');
    const updated = await res.json();
    const idx = state.tasks.findIndex(t => t.id === id);
    if (idx > -1) state.tasks[idx] = normalizeTask(updated);
    closeEditTaskModal();
    renderDashboardTaskList();
    renderFullList(state.tasks);
    if (document.getElementById('page-scheduled')?.classList.contains('active')) renderScheduledPage();
    if (document.getElementById('page-projects')?.classList.contains('active'))  renderProjectsPage();
    renderDashUpcoming();
    buildNotifications();
    showToast('ok', '✓ Görev kaydedildi ve tamamlandı');
  } catch(e) { showToast('err', 'Hata: ' + e.message); }
}

export async function deleteTask() {
  const id = parseInt(document.getElementById('edit-task-id').value);
  if (!confirm('Bu görevi silmek istediğinizden emin misiniz?')) return;
  try {
    const res = await fetch(`/api/tasks/${id}`, { method:'DELETE' });
    if (!res.ok) throw new Error('Silme hatası');
    state.tasks.splice(state.tasks.findIndex(t => t.id === id), 1);
    closeEditTaskModal();
    renderDashboardTaskList();
    renderFullList(state.tasks);
    renderDashUpcoming();
    buildNotifications();
    if (document.getElementById('page-backups')?.classList.contains('active')) renderBackupList();
    if (document.getElementById('page-projects')?.classList.contains('active')) renderProjectsPage();
    showToast('ok', 'Görev silindi');
  } catch(e) { showToast('err', e.message); }
}
export function closeEditTaskModal() { document.getElementById('edit-task-modal').classList.add('hidden'); }

// ══════════════════════════════════════════════════════════
//  v5.15 Faz B — PORTAL CASE YAZIŞMASI (IT tarafı)
// ══════════════════════════════════════════════════════════
let _caseTab = 'it';        // 'it' (kullanıcıya yanıt) | 'internal' (iç not)
let _caseMessages = [];     // son yüklenen tüm mesajlar (reporter+it+internal)

export function caseTab(which) {
  _caseTab = which;
  const ti = document.getElementById('case-tab-it');
  const ii = document.getElementById('case-tab-internal');
  ti.classList.toggle('active', which === 'it');
  ii.classList.toggle('active', which === 'internal');
  ti.style.color = which === 'it' ? 'var(--accent)' : 'var(--text-muted)';
  ti.style.borderBottomColor = which === 'it' ? 'var(--accent)' : 'transparent';
  ii.style.color = which === 'internal' ? 'var(--accent)' : 'var(--text-muted)';
  ii.style.borderBottomColor = which === 'internal' ? 'var(--accent)' : 'transparent';
  const hint = document.getElementById('case-tab-hint');
  const inp = document.getElementById('case-msg-input');
  if (which === 'it') {
    hint.textContent = '📧 Gönderdiğinizde talep sahibine "yanıt var" e-postası iletilir · portalda görünür.';
    if (inp) inp.placeholder = 'Kullanıcıya yanıt yazın…';
  } else {
    hint.textContent = '🔒 İç notlar yalnızca IT ekibince görülür — kullanıcıya ASLA gösterilmez.';
    if (inp) inp.placeholder = 'İç not yazın (kullanıcı görmez)…';
  }
  renderCaseThread();
}

async function loadCaseMessages(taskId) {
  try {
    const r = await fetch(`/api/tasks/${taskId}/messages`);
    if (!r.ok) return;
    const d = await r.json();
    _caseMessages = d.messages || [];
    // "Kullanıcıya Yanıt" sekmesinde okunmamış reporter mesajı sayısı rozeti
    const badge = document.getElementById('case-it-badge');
    if (badge) {
      const reporterCount = _caseMessages.filter(m => m.sender_type === 'reporter').length;
      badge.textContent = reporterCount ? `(${reporterCount})` : '';
    }
    renderCaseThread();
  } catch (e) { console.warn('[case] mesajlar yüklenemedi', e); }
}

function renderCaseThread() {
  const el = document.getElementById('case-thread');
  if (!el) return;
  // İç Notlar sekmesi: yalnız internal · Kullanıcıya Yanıt sekmesi: reporter+it
  const list = _caseTab === 'internal'
    ? _caseMessages.filter(m => m.sender_type === 'internal')
    : _caseMessages.filter(m => m.sender_type === 'reporter' || m.sender_type === 'it');
  if (!list.length) {
    el.innerHTML = `<div style="font-size:11px;color:var(--text-muted);text-align:center;padding:10px">${_caseTab==='internal'?'Henüz iç not yok.':'Henüz yazışma yok.'}</div>`;
    return;
  }
  el.innerHTML = list.map(m => {
    const t = m.created_at ? new Date(m.created_at).toLocaleString('tr-TR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : '';
    const mine = m.sender_type === 'it' || m.sender_type === 'internal';  // IT üretimi → sağ
    const isInternal = m.sender_type === 'internal';
    const bg = isInternal ? 'rgba(244,185,66,.12)' : (m.sender_type==='it' ? 'var(--accent)' : 'var(--surface2)');
    const col = m.sender_type==='it' ? '#06231d' : 'var(--text)';
    const bd = isInternal ? '1px solid rgba(244,185,66,.35)' : '1px solid var(--border)';
    return `<div style="align-self:${mine?'flex-end':'flex-start'};max-width:82%;background:${bg};color:${col};border:${bd};border-radius:11px;padding:8px 11px;font-size:12px;line-height:1.5;white-space:pre-wrap">
      <div style="font-size:9px;opacity:.7;margin-bottom:3px;font-family:'IBM Plex Mono',monospace">${escapeHtml(m.author_name||(m.sender_type==='reporter'?'Kullanıcı':'IT'))} · ${t}</div>${escapeHtml(m.body)}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

export async function sendCaseMessage() {
  const id = parseInt(document.getElementById('edit-task-id').value);
  const inp = document.getElementById('case-msg-input');
  const body = inp.value.trim();
  if (!body) return;
  try {
    const r = await fetch(`/api/tasks/${id}/messages`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ sender_type: _caseTab, body })
    });
    if (!r.ok) throw new Error((await r.json()).error || 'Gönderilemedi');
    inp.value = '';
    await loadCaseMessages(id);
    showToast('ok', _caseTab === 'it' ? '💬 Yanıt gönderildi (kullanıcıya mail iletildi)' : '📝 İç not kaydedildi');
  } catch (e) { showToast('err', e.message); }
}

// ══════════════════════════════════════════════════════════
//  BACKUP DOSYA YÖNETİMİ — Edit modal içi
// ══════════════════════════════════════════════════════════
async function loadTaskBackups(taskId) {
  const el = document.getElementById('edit-backup-file-list');
  if (!el) return;
  try {
    const res = await fetch(`/api/tasks/${taskId}/backups`);
    const list = res.ok ? await res.json() : [];
    if (!list.length) {
      el.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:4px 0">Henüz dosya yüklenmemiş.</div>';
      return;
    }
    el.innerHTML = list.map(b => {
      const sizeStr = b.file_size > 1024 ? Math.round(b.file_size/1024)+' KB' : (b.file_size||0)+' B';
      const date = b.uploaded_at ? new Date(b.uploaded_at).toLocaleDateString('tr-TR') : '';
      return `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px solid var(--border)">
        <div style="flex:1;min-width:0">
          <div style="font-size:11px;font-weight:600;color:var(--gold);font-family:'IBM Plex Mono',monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(b.filename)}</div>
          <div style="font-size:9px;color:var(--text-muted)">${sizeStr}${b.device?' · '+escapeHtml(b.device):''} · ${date}</div>
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0">
          <button class="btn btn-sm" style="padding:2px 8px;font-size:9px;background:var(--gold-dim);border:1px solid rgba(244,185,66,.25);color:var(--gold)" onclick="downloadBackup(${b.id})">&#8595;</button>
          <button class="btn btn-sm btn-danger" style="padding:2px 8px;font-size:9px" onclick="deleteBackupFile(${b.id}, ${taskId})">&#10005;</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML = '<div style="font-size:11px;color:var(--danger)">Yüklenemedi</div>'; }
}

export async function deleteBackupFile(backupId, taskId) {
  if (!confirm('Bu dosyayı silmek istediğinizden emin misiniz?')) return;
  try {
    const res = await fetch(`/api/backups/${backupId}`, { method:'DELETE' });
    if (!res.ok) throw new Error('Silme hatası');
    showToast('ok', 'Dosya silindi');
    loadTaskBackups(taskId);
    if (document.getElementById('page-backups')?.classList.contains('active')) renderBackupList();
  } catch(e) { showToast('err', e.message); }
}

export async function uploadBackupToTask() {
  const input = document.getElementById('edit-backup-upload-input');
  const taskId = parseInt(document.getElementById('edit-task-id').value);
  if (!input.files[0]) return;
  const fd = new FormData();
  fd.append('backup_file', input.files[0]);
  try {
    const res = await fetch(`/api/tasks/${taskId}/backups`, { method:'POST', body: fd });
    if (!res.ok) throw new Error((await res.json()).error || 'Yükleme hatası');
    showToast('ok', 'Dosya yüklendi ✓');
    input.value = '';
    loadTaskBackups(taskId);
    if (document.getElementById('page-backups')?.classList.contains('active')) renderBackupList();
  } catch(e) { showToast('err', e.message); }
}

// ── ESM Faz 4d-3a: Anlık Görevler (full list) render + filtre ──
// ══════════════════════════════════════════════════════════
//  FULL TASK LIST
// ══════════════════════════════════════════════════════════
export function renderFullList(list) {
  let l = list || state.tasks;
  if (state.ftFirm)   l = l.filter(t => t.firm === state.ftFirm);
  if (state.ftCat)    l = l.filter(t => t.cat  === state.ftCat);
  if (state.ftSearch) l = l.filter(t => t.title.toLowerCase().includes(state.ftSearch));
  const el = document.getElementById('full-task-list');
  if (el) el.innerHTML = `<div style="padding:4px 18px">${l.map(taskRow).join('')}</div>`;
  const cnt = document.getElementById('task-count-label');
  if (cnt) cnt.textContent = `${l.length} kayıt`;
}
export function filterFullByFirm(v) { state.ftFirm = v; renderFullList(); }
export function filterFullByCat(v)  { state.ftCat  = v; renderFullList(); }
export function filterFullList(v)   { state.ftSearch = v.toLowerCase(); renderFullList(); }

// ── ESM Faz 4d-3b: Checklist (yeni görev + edit modal, paylaşımlı) ──
// ══════════════════════════════════════════════════════════
//  CHECKLİST FONKSİYONLARI
// ══════════════════════════════════════════════════════════

// Yeni görev formu — checklist (addTask _getNewChecklistItems'ı okur)
function _getNewChecklistItems() {
  const items = [];
  document.querySelectorAll('#checklist-items .checklist-item').forEach(el => {
    const lbl = el.querySelector('.checklist-label');
    if (lbl && lbl.textContent.trim()) items.push(lbl.textContent.trim());
  });
  return items;
}

export function addChecklistItem() {
  const inp = document.getElementById('new-checklist-item');
  const val = inp.value.trim(); if (!val) return;
  _appendChecklistItem('checklist-items', val, false, true);
  inp.value = '';
}

function _appendChecklistItem(containerId, label, done, removable) {
  const container = document.getElementById(containerId); if (!container) return;
  const div = document.createElement('div');
  div.className = 'checklist-item';
  const cb = document.createElement('div');
  cb.className = 'checklist-cb' + (done ? ' checked' : '');
  cb.onclick = function() {
    this.classList.toggle('checked');
    this.nextElementSibling.classList.toggle('done', this.classList.contains('checked'));
  };
  const lbl = document.createElement('span');
  lbl.className = 'checklist-label' + (done ? ' done' : '');
  lbl.textContent = label;
  div.appendChild(cb);
  div.appendChild(lbl);
  if (removable) {
    const rm = document.createElement('span');
    rm.className = 'checklist-rm';
    rm.textContent = '×';
    rm.onclick = function() { this.closest('.checklist-item').remove(); };
    div.appendChild(rm);
  }
  container.appendChild(div);
}
function _renderChecklistProgress(containerId, items, doneArr) {
  const total = items.length;
  if (!total) return;
  const done  = doneArr.filter(Boolean).length;
  const pct   = Math.round(done/total*100);
  const container = document.getElementById(containerId); if (!container) return;
  const existing = container.querySelector('.checklist-progress');
  if (existing) existing.remove();
  const prog = document.createElement('div');
  prog.className = 'checklist-progress';
  prog.innerHTML = `<div class="checklist-progress-fill" style="width:${pct}%"></div>`;
  container.after(prog);
}

// Edit modal checklist (openEditTask _loadEditChecklist, saveEditTask _getEditChecklistData okur)
function _loadEditChecklist(items, doneArr) {
  const container = document.getElementById('edit-checklist-items'); if (!container) return;
  container.innerHTML = '';
  items.forEach((item, i) => _appendEditChecklistRow(container, item, doneArr[i]||false, i));
  _renderChecklistProgress('edit-checklist-items', items, doneArr);
}

function _appendEditChecklistRow(container, label, done, idx) {
  const div = document.createElement('div');
  div.className = 'checklist-item';
  div.dataset.idx = idx;
  const cb = document.createElement('div');
  cb.className = 'checklist-cb' + (done ? ' checked' : '');
  cb.onclick = function() { _toggleEditCb(this); };
  const lbl = document.createElement('span');
  lbl.className = 'checklist-label' + (done ? ' done' : '');
  lbl.textContent = label;
  const rm = document.createElement('span');
  rm.className = 'checklist-rm';
  rm.textContent = '×';
  rm.onclick = function() { this.closest('.checklist-item').remove(); _syncEditChecklistProgress(); };
  div.appendChild(cb);
  div.appendChild(lbl);
  div.appendChild(rm);
  container.appendChild(div);
}
function _toggleEditCb(cbEl) {
  cbEl.classList.toggle('checked');
  const label = cbEl.nextElementSibling;
  label.classList.toggle('done', cbEl.classList.contains('checked'));
  _syncEditChecklistProgress();
}

function _syncEditChecklistProgress() {
  const items   = [...document.querySelectorAll('#edit-checklist-items .checklist-item')];
  const total   = items.length;
  const done    = items.filter(el => el.querySelector('.checklist-cb')?.classList.contains('checked')).length;
  const pct     = total ? Math.round(done/total*100) : 0;
  const fill    = document.querySelector('.checklist-progress-fill');
  if (fill) fill.style.width = pct + '%';
}

export function addEditChecklistItem() {
  const inp = document.getElementById('edit-new-checklist-item');
  const val = inp.value.trim(); if (!val) return;
  const container = document.getElementById('edit-checklist-items');
  const idx = container.children.length;
  _appendEditChecklistRow(container, val, false, idx);
  inp.value = '';
  _syncEditChecklistProgress();
}

function _getEditChecklistData() {
  const items = []; const doneArr = [];
  document.querySelectorAll('#edit-checklist-items .checklist-item').forEach(el => {
    const lbl = el.querySelector('.checklist-label');
    const cb  = el.querySelector('.checklist-cb');
    if (lbl) { items.push(lbl.textContent.trim()); doneArr.push(cb?.classList.contains('checked')||false); }
  });
  return { items, doneArr };
}
