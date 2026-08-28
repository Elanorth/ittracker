// ══════════════════════════════════════════════════════════
//  tasks.js — Görev işlemleri (v5.53, ESM Faz 4d-1: ekle + toggle)
//
//  Gerçek ESM modülü (app.js'ten çıkarılıyor; Faz 4d alt-adımlarında büyüyecek).
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//  Bağımlılıklar: state (import). showToast/buildNotifications/renderFullList/
//  showPage app.js klasik → bare global (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
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
