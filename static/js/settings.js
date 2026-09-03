// ══════════════════════════════════════════════════════════
//  settings.js — Ayarlar sayfası (v5.64, ESM Faz 4f-4)
//
//  Portal otomatik atama kuralları + Teams webhook bildirimleri + kullanıcı/SMTP
//  ayarları. app.js'ten çıkarıldı (Ayarlar sayfasının 3 kartı).
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//
//  Bağımlılıklar: escapeHtml (utils import), state (import). FIRMS/showToast/
//  renderUserTable app.js/admin.js → bare global (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { onClick, onChange } from './events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — ayarlar sayfası aksiyonları (inline onclick → data-click)
onClick('addAssignRule',      () => addAssignRule());
onChange('toggleAutoAssign',  el => toggleAutoAssign(el.checked)); // master toggle checkbox
onClick('saveUserSettings',   () => saveUserSettings());
onClick('saveSmtpSettings',   () => saveSmtpSettings());
onClick('testSmtp',           () => testSmtp());
onClick('saveTeamsSettings',  () => saveTeamsSettings());
onClick('testTeams',          () => testTeams());

// ══════════════════════════════════════════════════════════
//  PORTAL OTOMATİK ATAMA (v5.19 — Havuz D2)
// ══════════════════════════════════════════════════════════
const AA_CAT_LABELS = { '': 'Tümü', support: 'Genel Destek', infra: 'Ağ/İnternet', other: 'Diğer' };

export async function loadAutoAssign() {
  const card = document.getElementById('settings-card-autoassign');
  if (!card || card.style.display === 'none') return;
  try {
    // Hedef kişi listesi (kapsamdaki kullanıcılar) — state.firmUsers'ı tazele
    try {
      const uRes = await fetch('/api/firm/users');
      if (uRes.ok) state.firmUsers = await uRes.json();
    } catch (e) { /* state.firmUsers eski haliyle kalır */ }
    // Master toggle durumu
    const tRes = await fetch('/api/settings/auto-assign');
    if (tRes.ok) {
      const t = await tRes.json();
      const cb = document.getElementById('aa-toggle');
      if (cb) cb.checked = !!t.enabled;
    }
    populateAaSelects();
    // Kurallar
    const rRes = await fetch('/api/assign-rules');
    renderAssignRules(rRes.ok ? await rRes.json() : []);
  } catch (e) {
    console.warn('Otomatik atama yüklenemedi:', e);
  }
}

function populateAaSelects() {
  const isSA = (state.currentUser.permission_level === 'super_admin');
  // Firma seçenekleri — super_admin: tüm firmalar + global; director: kapsamı
  const firmSel = document.getElementById('aa-firm');
  if (firmSel) {
    const opts = [];
    if (isSA) {
      opts.push('<option value="">Tüm firmalar</option>');
      Object.entries(FIRMS).forEach(([slug, f]) => opts.push(`<option value="${slug}">${escapeHtml(f.label || slug)}</option>`));
    } else {
      const scope = [...new Set(state.firmUsers.map(u => u.firm).filter(Boolean))];
      scope.forEach(slug => opts.push(`<option value="${slug}">${escapeHtml((FIRMS[slug] && FIRMS[slug].label) || slug)}</option>`));
    }
    firmSel.innerHTML = opts.join('');
  }
  // Hedef kişi seçenekleri
  const tgtSel = document.getElementById('aa-target');
  if (tgtSel) {
    tgtSel.innerHTML = state.firmUsers.length
      ? state.firmUsers.map(u => `<option value="${u.id}">${escapeHtml(u.full_name)}${u.firm ? ' · ' + escapeHtml(u.firm) : ''}</option>`).join('')
      : '<option value="">(kullanıcı yok)</option>';
  }
}

function renderAssignRules(rules) {
  const box = document.getElementById('aa-rules-list');
  if (!box) return;
  if (!rules.length) {
    box.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:4px 2px">Henüz kural yok. Aşağıdan ekleyin.</div>';
    return;
  }
  box.innerHTML = rules.map(r => {
    const firm = r.firm ? escapeHtml((FIRMS[r.firm] && FIRMS[r.firm].label) || r.firm) : 'Tüm firmalar';
    const cat = AA_CAT_LABELS[r.category] || r.category || 'Tümü';
    const kw = r.keyword ? `“${escapeHtml(r.keyword)}”` : '<span style="color:var(--text-muted)">anahtar yok</span>';
    return `<div class="aa-rule${r.enabled ? '' : ' off'}">
      <span class="aa-tag">#${r.priority}</span>
      <span class="aa-tag">${firm}</span>
      <span class="aa-tag">${escapeHtml(cat)}</span>
      <span>${kw}</span>
      <span class="aa-arrow">→</span>
      <span>${escapeHtml(r.target_name || '?')}</span>
      <div class="aa-actions">
        <label class="aa-switch" style="width:36px;height:20px"><input type="checkbox" ${r.enabled ? 'checked' : ''} onchange="patchAssignRule(${r.id}, { enabled: this.checked })"><span></span></label>
        <button class="aa-x" title="Sil" onclick="deleteAssignRule(${r.id})">✕</button>
      </div>
    </div>`;
  }).join('');
}

export async function toggleAutoAssign(checked) {
  try {
    const res = await fetch('/api/settings/auto-assign', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: checked }),
    });
    if (!res.ok) throw new Error();
    showToast('ok', checked ? 'Otomatik atama açıldı' : 'Otomatik atama kapatıldı');
  } catch (e) {
    showToast('err', 'Ayar değiştirilemedi');
    const cb = document.getElementById('aa-toggle'); if (cb) cb.checked = !checked;
  }
}

export async function addAssignRule() {
  const target = document.getElementById('aa-target').value;
  if (!target) { showToast('err', 'Atanacak kişi seçin'); return; }
  const body = {
    firm: document.getElementById('aa-firm').value,
    category: document.getElementById('aa-cat').value,
    keyword: document.getElementById('aa-kw').value.trim(),
    target_user_id: parseInt(target, 10),
    priority: parseInt(document.getElementById('aa-prio').value, 10) || 100,
  };
  try {
    const res = await fetch('/api/assign-rules', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || 'hata');
    document.getElementById('aa-kw').value = '';
    showToast('ok', 'Kural eklendi');
    loadAutoAssign();
  } catch (e) {
    showToast('err', e.message || 'Kural eklenemedi');
  }
}

export async function patchAssignRule(id, patch) {
  try {
    const res = await fetch(`/api/assign-rules/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error();
  } catch (e) {
    showToast('err', 'Kural güncellenemedi'); loadAutoAssign();
  }
}

export async function deleteAssignRule(id) {
  if (!confirm('Bu kuralı silmek istediğinize emin misiniz?')) return;
  try {
    const res = await fetch(`/api/assign-rules/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();
    showToast('ok', 'Kural silindi');
    loadAutoAssign();
  } catch (e) {
    showToast('err', 'Kural silinemedi');
  }
}

// ══════════════════════════════════════════════════════════
//  TEAMS BİLDİRİMLERİ (v5.32)
// ══════════════════════════════════════════════════════════
export async function loadTeamsSettings() {
  const card = document.getElementById('settings-card-teams');
  if (!card || card.style.display === 'none') return;
  try {
    const r = await fetch('/api/settings/teams');
    if (!r.ok) return;
    const d = await r.json();
    const st = document.getElementById('teams-status');
    const inp = document.getElementById('teams-url');
    if (st) st.textContent = d.configured ? `· kayıtlı (${d.masked})` : '· ayarlı değil';
    if (inp) inp.placeholder = d.configured ? '(kayıtlı — değiştirmek için yeni URL yazın)' : 'https://outlook.office.com/webhook/...';
  } catch (e) { /* sessiz */ }
}

export async function saveTeamsSettings() {
  const url = document.getElementById('teams-url').value.trim();
  try {
    const r = await fetch('/api/settings/teams', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Kaydedilemedi');
    showToast('ok', url ? 'Teams webhook kaydedildi' : 'Teams bildirimleri kapatıldı');
    document.getElementById('teams-url').value = '';
    loadTeamsSettings();
  } catch (e) { showToast('err', e.message); }
}

export async function testTeams() {
  try {
    const r = await fetch('/api/settings/teams/test', { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Gönderilemedi');
    showToast('ok', '✅ Test kartı Teams kanalına gönderildi');
  } catch (e) { showToast('err', 'Test başarısız: ' + e.message); }
}

// ══════════════════════════════════════════════════════════
//  KULLANICI + SMTP AYARLARI
// ══════════════════════════════════════════════════════════
export async function loadSettingsFromServer() {
  try {
    // Kullanıcı bilgilerini yükle
    const uRes = await fetch('/api/me');
    if (uRes.ok) {
      const u = await uRes.json();
      const fn = document.getElementById('set-fullname');
      const un = document.getElementById('set-username');
      const em = document.getElementById('set-email');
      const rl = document.getElementById('set-role');
      if (fn) fn.value = u.full_name || '';
      if (un) un.value = u.username  || '';
      if (em) em.value = u.email     || '';
      if (rl) rl.value = u.role || '';
    }
    // SMTP ayarlarını yükle
    const sRes = await fetch('/api/settings/smtp');
    if (sRes.ok) {
      const s = await sRes.json();
      const sh = document.getElementById('smtp-host');
      const sp = document.getElementById('smtp-port');
      const su = document.getElementById('smtp-user');
      if (sh) sh.value = s.smtp_host || '';
      if (sp) sp.value = s.smtp_port || '587';
      if (su) su.value = s.smtp_user || '';
      // Şifreyi gösterme ama placeholder ile dolu olduğunu belirt
      const spw = document.getElementById('smtp-pass');
      if (spw && s.smtp_pass) spw.placeholder = '(kayıtlı — değiştirmek için yazın)';
    }
  } catch(e) {
    console.warn('Ayarlar yüklenemedi:', e);
  }
}

export async function saveUserSettings() {
  const fullname = document.getElementById('set-fullname').value.trim();
  const username = document.getElementById('set-username').value.trim();
  const email    = document.getElementById('set-email').value.trim();
  const role     = document.getElementById('set-role').value;
  const password = document.getElementById('set-password').value;
  if (!fullname || !username || !email) {
    showToast('err', 'Ad, kullanici adi ve mail bos olamaz');
    return;
  }
  const body = { full_name: fullname, username, email, role };
  if (password) body.password = password;
  try {
    const res  = await fetch('/api/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) {
      showToast('err', data.error || 'Kayit basarisiz');
      return;
    }
    // Sidebar güncelle
    document.getElementById('sb-name').textContent = data.full_name;
    document.getElementById('sb-role').textContent = data.role;
    const initials = data.full_name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('sb-avatar').textContent = initials;
    // Şifre alanını temizle
    document.getElementById('set-password').value = '';
    // state.USERS dizisini güncelle
    const me = state.USERS.find(u => u.username === 'lmc' || u.id === 1);
    if (me) { me.name = data.full_name; me.username = data.username; me.email = data.email; me.role = data.role; }
    showToast('ok', 'Kullanici bilgileri kaydedildi — yeni kullanici adi: ' + data.username);
    renderUserTable();
  } catch(e) {
    showToast('err', 'Sunucu hatasi: ' + e.message);
  }
}

export async function saveSmtpSettings() {
  const body = {
    smtp_host: document.getElementById('smtp-host').value.trim(),
    smtp_port: document.getElementById('smtp-port').value.trim(),
    smtp_user: document.getElementById('smtp-user').value.trim(),
    smtp_pass: document.getElementById('smtp-pass').value,
  };
  if (!body.smtp_user) { showToast('err', 'Mail adresi bos olamaz'); return; }
  try {
    const res  = await fetch('/api/settings/smtp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (res.ok) {
      document.getElementById('smtp-pass').value = '';
      document.getElementById('smtp-pass').placeholder = '(kayıtlı — değiştirmek için yazın)';
      showToast('ok', 'SMTP ayarlari .env dosyasina kaydedildi');
    } else {
      showToast('err', data.error || 'Kayit basarisiz');
    }
  } catch(e) {
    showToast('err', 'Sunucu hatasi: ' + e.message);
  }
}

export async function testSmtp() {
  showToast('ok', 'SMTP baglantisi test ediliyor...');
  try {
    const res  = await fetch('/api/settings/smtp/test', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.ok) showToast('ok', data.message || 'Baglanti basarili');
    else showToast('err', data.error || 'Baglanti basarisiz');
  } catch(e) {
    showToast('err', 'Sunucu hatasi: ' + e.message);
  }
}
