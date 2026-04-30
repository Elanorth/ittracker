// IT Tracker — main client bundle (v4.9)
// templates/app.html içinden çıkarıldı (v4.9 madde #17). Davranış değişmedi.

// ══════════════════════════════════════════════════════════
//  KULLANICI FİRMA BAZLI TEMA (v3)
// ══════════════════════════════════════════════════════════
function applyThemeForFirm(firmSlug) {
  const f = (firmSlug || '').toLowerCase();
  let theme = null;
  let logoText = 'İnventist & Assos · v4.9';

  if (f.includes('assos')) {
    theme = 'assos';
    logoText = 'Assos Pharma · v4.9';
  } else if (f.includes('inventist')) {
    theme = 'inventist';
    logoText = 'İnventist · v4.9';
  }

  if (theme) {
    document.documentElement.setAttribute('data-theme', theme);
  } else {
    document.documentElement.removeAttribute('data-theme');
  }

  const logoSub = document.getElementById('logo-sub-text');
  if (logoSub) logoSub.textContent = logoText;
}

// ══════════════════════════════════════════════════════════
//  YETKİ SİSTEMİ (v3)
// ══════════════════════════════════════════════════════════
function applyPermissions(level) {
  // Nav item görünürlüğü
  document.querySelectorAll('[data-perm="manager"]').forEach(el => {
    el.style.display = (level === 'junior') ? 'none' : '';
  });

  // v4.4 — director+ özel (audit vb.)
  const isDirectorUp = (level === 'super_admin' || level === 'it_director');
  document.querySelectorAll('[data-perm="director"]').forEach(el => {
    el.style.display = isDirectorUp ? '' : 'none';
  });

  // Ortak Alan — can_access_board veya super_admin
  const showBoard = currentUser.can_access_board || currentUser.permission_level === 'super_admin';
  document.querySelectorAll('[data-perm="board"]').forEach(el => {
    el.style.display = showBoard ? '' : 'none';
  });

  // Junior: "Yeni Görev" butonunu kısıtla (sadece anlık)
  const newTaskBtn = document.getElementById('btn-new-task-top');
  if (newTaskBtn && level === 'junior') {
    newTaskBtn.setAttribute('data-junior', 'true');
  }
}

function applySettingsPermissions() {
  const level = (currentUser.permission_level || 'junior');
  const smtpCard = document.getElementById('settings-card-smtp');
  const backupCard = document.getElementById('settings-card-backup');
  if (smtpCard) smtpCard.style.display = (level === 'super_admin') ? '' : 'none';
  if (backupCard) backupCard.style.display = (level === 'super_admin') ? '' : 'none';
}

function applyJuniorTaskRestrictions() {
  const level = (currentUser.permission_level || 'junior');
  const catSel = document.getElementById('new-cat');
  const firmSel = document.getElementById('new-firm');
  const periodSel = document.getElementById('new-period');

  if (level === 'junior') {
    // Kategori: sadece Anlık Görev ve Destek Talebi
    Array.from(catSel.options).forEach(opt => {
      if (['routine','project','backup'].includes(opt.value)) opt.style.display = 'none';
      else opt.style.display = '';
    });
    catSel.value = 'task';
    // Firma: otomatik kullanıcının firması
    if (currentUser.firm) {
      firmSel.value = currentUser.firm;
      firmSel.disabled = true;
      updateTeamOptions();
    }
    // Periyot gizle
    periodSel.closest('.form-group').style.display = 'none';
  } else {
    // Manager/admin: tümünü göster
    Array.from(catSel.options).forEach(opt => opt.style.display = '');
    firmSel.disabled = false;
    periodSel.closest('.form-group').style.display = '';
  }
}

const PERM_LABELS = {super_admin:'Super Admin', it_director:'IT Müdürü', it_manager:'IT Yöneticisi', it_specialist:'IT Specialist', junior:'Junior'};
const JUNIOR_ALLOWED_PAGES = ['dashboard', 'tasks', 'add', 'board'];

// ══════════════════════════════════════════════════════════
//  SABİT VERİLER
// ══════════════════════════════════════════════════════════
// FIRMS objesi — başlangıçta sabit, loadFirmsFromDB() ile DB'den güncellenir
const FIRMS = {
  inventist: { id: null, label: 'İnventist', cls: 'inventist', teams: [], teamIds: {} },
  assos:     { id: null, label: 'Assos',     cls: 'assos',     teams: [], teamIds: {} }
};

async function loadFirmsFromDB() {
  try {
    const res = await fetch('/api/firms');
    if (!res.ok) return;
    const firms = await res.json();
    firms.forEach(f => {
      const slug = f.slug;
      if (FIRMS[slug]) {
        FIRMS[slug].id = f.id;
        FIRMS[slug].label = f.name;
        FIRMS[slug].teams = f.teams.map(t => t.name);
        FIRMS[slug].teamIds = {};
        f.teams.forEach(t => { FIRMS[slug].teamIds[t.name] = t.id; });
      }
    });
  } catch(e) { console.warn('Firma verileri yüklenemedi:', e); }
}
const BACKUP_TYPES = ['.cfg','.conf','.txt','.bin','.xml','.json','.tar','.zip'];
const STATUS_LABELS = {active:'Aktif', pending:'Bekliyor', inactive:'Pasif'};
const CAT_LABELS = {task:'Anlık',project:'Proje',routine:'Rutin',backup:'Config Backup',support:'Anlık',infra:'Anlık',other:'Anlık'};

// ── Uygulama durumu ──
let tasks = [];       // API'den yüklenir
let USERS = [];       // API'den yüklenir
let currentUser = {}; // /api/me
let selectedUserId = null; // v4.2 — director+ tarafından görüntülenen kullanıcı (null = kendim)
let firmUsers = [];   // v4.2 — director+'in firmasındaki kullanıcılar

// ══════════════════════════════════════════════════════════
//  AUTH
// ══════════════════════════════════════════════════════════
function showLoginScreen() { document.getElementById('login-screen').style.display = 'flex'; }
function o365Login() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('sb-o365').style.display = 'inline-flex';
  showToast('ok','Microsoft 365 hesabı başarıyla bağlandı');
}
function manualLogin() {
  const u = document.getElementById('login-user').value;
  const p = document.getElementById('login-pass').value;
  fetch('/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:u,password:p}) })
    .then(r => r.json()).then(d => {
      if (d.ok) { document.getElementById('login-screen').style.display = 'none'; loadApp(); }
      else showToast('err', d.error || 'Hatalı kullanıcı adı veya şifre');
    }).catch(() => { document.getElementById('login-screen').style.display = 'none'; loadApp(); });
}

// ══════════════════════════════════════════════════════════
//  UYGULAMA YÜKLEME — API'den tüm veriyi çek
// ══════════════════════════════════════════════════════════
async function loadApp() {
  try {
    const me = await fetch('/api/me').then(r => r.json());
    currentUser = me;
    document.getElementById('sb-name').textContent = me.full_name || me.username;
    document.getElementById('sb-role').textContent = me.role || '';
    document.getElementById('sb-avatar').textContent = (me.full_name||'?').split(' ').map(w=>w[0]).join('').substring(0,2).toUpperCase();
    if (me.o365_linked) document.getElementById('sb-o365').style.display = 'inline-flex';
    // Kullanıcının firmasına göre tema uygula
    applyThemeForFirm(me.firm);
    // Yetki seviyesine göre UI kısıtla
    applyPermissions(me.permission_level || 'junior');
  } catch(e) { console.warn('Me yüklenemedi', e); }

  await loadFirmsFromDB();
  await initFirmUserFilter(); // v4.2 — director+ için
  await loadTasks();
  setDateDisplay('topbar-date-day', 'topbar-date-full');
  renderDashboard();
  setTimeout(() => buildNotifications(), 400);
}

// ── v4.2: Director+ kullanıcı filtresi ──
async function initFirmUserFilter() {
  const level = currentUser.permission_level || 'junior';
  if (level !== 'super_admin' && level !== 'it_director') return;
  try {
    const res = await fetch('/api/firm/users');
    if (!res.ok) return;
    firmUsers = await res.json();
    const sel = document.getElementById('firm-user-filter');
    const wrap = document.getElementById('firm-user-filter-wrap');
    if (!sel || !wrap) return;
    // Options: kendim + diğer kullanıcılar (kendisini ayrı kategori "kendim" olarak sunuyoruz)
    const others = firmUsers.filter(u => u.id !== currentUser.id);
    sel.innerHTML = '<option value="">— Kendim —</option>' +
      others.map(u => `<option value="${u.id}">${u.full_name}${u.firm ? ' · '+u.firm : ''}</option>`).join('');
    wrap.style.display = others.length ? 'flex' : 'none';
    refreshAssignModeUI();
  } catch(e) { console.warn('firm users yüklenemedi', e); }
}

async function onFirmUserChange() {
  const val = document.getElementById('firm-user-filter').value;
  selectedUserId = val ? parseInt(val) : null;
  refreshAssignModeUI();
  await loadTasks();
  renderDashboard();
  // Hangi sayfadaysak yeniden render et
  const activePage = document.querySelector('.page-section.active');
  if (activePage && activePage.id === 'page-tasks') renderFullList(tasks.filter(t => t.cat === 'task' || t.cat === 'backup'));
}

// v4.9 — Atama modu (director+ başka kullanıcıyı görüntülüyor) açıkken kategori default'u "support"
function applyAssignModeDefaults() {
  const isDirectorUp = currentUser.permission_level === 'super_admin' || currentUser.permission_level === 'it_director';
  const inAssignMode = isDirectorUp && selectedUserId && selectedUserId !== currentUser.id;
  const catSel = document.getElementById('new-cat');
  if (!catSel || !inAssignMode) return;
  // Sadece sayfaya ilk girişte / hâlâ default değerdeyken support'a çevir
  // (kullanıcı manuel seçimini bozmamak için 'routine'/'task' default değerlerini kontrol et)
  if (catSel.value === 'routine' || catSel.value === 'task' || !catSel.value) {
    catSel.value = 'support';
  }
}

// v4.3 — Yeni görev sayfasında atama modu banner'ı + IT Müdürü notu alanı görünürlüğü
function refreshAssignModeUI() {
  const isDirectorUp = currentUser.permission_level === 'super_admin' || currentUser.permission_level === 'it_director';
  const banner = document.getElementById('assign-mode-banner');
  const target = document.getElementById('assign-target-name');
  const mnGroup = document.getElementById('new-manager-note-group');
  const assignTo = (isDirectorUp && selectedUserId && selectedUserId !== currentUser.id) ? selectedUserId : null;
  if (banner) {
    if (assignTo) {
      const u = firmUsers.find(u => u.id === assignTo);
      if (target) target.textContent = u ? u.full_name : '—';
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  }
  // IT Müdürü notu alanı: her zaman director+'a görünür
  if (mnGroup) mnGroup.classList.toggle('hidden', !isDirectorUp);
}

async function loadTasks(month, year) {
  try {
    const now = new Date();
    const m = month || now.getMonth() + 1;
    const y = year  || now.getFullYear();
    // v4.2 — director+ başka kullanıcıyı görüntülüyorsa user_id eklenir
    const userParam = selectedUserId ? '&user_id=' + selectedUserId : '';
    const res = await fetch('/api/tasks?month=' + m + '&year=' + y + userParam);
    const data = await res.json();
    // API alanlarını frontend formatına normalize et
    tasks = data.map(normalizeTask);
  } catch(e) { console.error('Görevler yüklenemedi:', e); tasks = []; }
}

// v4.2 — başka kullanıcının görevlerine yazma izni yok (yalnızca görüntüleme)
function isReadOnlyScope() { return !!selectedUserId && selectedUserId !== currentUser.id; }

// v4.3 — HTML escape (kırmızı not ve benzeri güvenli gösterim için)
function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ══════════════════════════════════════════════════════════
//  v4.4 — AUDIT LOG SAYFASI
// ══════════════════════════════════════════════════════════
const AUDIT_ACTION_LABELS = {
  'task.create':'Görev Oluşturma', 'task.assign':'Görev Atama',
  'task.update':'Görev Güncelleme','task.complete':'Görev Tamamlama',
  'task.reopen':'Görev Yeniden Açma','task.manager_note':'IT Müdürü Notu',
  'task.delete':'Görev Silme',
  'user.invite':'Kullanıcı Daveti','user.update':'Kullanıcı Güncelleme','user.delete':'Kullanıcı Silme',
};
// v5.0 BUG-1 fix: sabit hex değerleri — tema-bağımsız (Inventist temasında
// var(--accent) #ffffff olduğu için beyaz on beyaz badge görünmez oluyordu).
// Tüm badge'ler beyaz text üstüne kontrastlı renk göstermeli, tema değiştiğinde
// audit log'un okunabilirliği bozulmamalı.
const AUDIT_ACTION_COLORS = {
  'task.create':'#34d058',           // yeşil — oluşturma
  'task.assign':'#f4b942',           // gold — atama
  'task.update':'#7f6cf7',           // mor — güncelleme
  'task.complete':'#34d058',         // yeşil — tamamlanma
  'task.reopen':'#ff5f3d',           // turuncu — yeniden açma
  'task.manager_note':'#ef4444',     // kırmızı — vurgu
  'task.delete':'#f85149',           // kırmızı — silme
  'user.invite':'#34d058',           // yeşil — davet
  'user.update':'#7f6cf7',           // mor — kullanıcı güncelleme
  'user.delete':'#f85149',           // kırmızı — silme
};

function initAuditPage() {
  // Hedef kullanıcı dropdown'u firmUsers'tan doldur
  const sel = document.getElementById('audit-target-user');
  if (sel && firmUsers.length) {
    sel.innerHTML = '<option value="">Tümü</option>' +
      firmUsers.map(u => `<option value="${u.id}">${escapeHtml(u.full_name)}</option>`).join('');
  }
  // Varsayılan: son 30 gün
  const start = document.getElementById('audit-start');
  const end   = document.getElementById('audit-end');
  if (start && !start.value && end && !end.value) setAuditRange('30d');
  // Otomatik yükle
  loadAuditLog();
}

function setAuditRange(kind) {
  const now = new Date();
  const end = now.toISOString().slice(0,10);
  let start = end;
  if (kind === '7d')  { const d = new Date(now); d.setDate(d.getDate()-6);  start = d.toISOString().slice(0,10); }
  if (kind === '30d') { const d = new Date(now); d.setDate(d.getDate()-29); start = d.toISOString().slice(0,10); }
  if (kind === 'month') { start = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0,10); }
  if (kind === 'today') { start = end; }
  document.getElementById('audit-start').value = start;
  document.getElementById('audit-end').value   = end;
}

function resetAuditFilters() {
  document.getElementById('audit-start').value = '';
  document.getElementById('audit-end').value   = '';
  document.getElementById('audit-action').value = '';
  document.getElementById('audit-target-user').value = '';
  loadAuditLog();
}

async function loadAuditLog() {
  const tbody = document.getElementById('audit-tbody');
  const count = document.getElementById('audit-count');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-muted);font-size:12px">Yükleniyor…</td></tr>';
  const params = new URLSearchParams();
  const s = document.getElementById('audit-start').value;
  const e = document.getElementById('audit-end').value;
  const a = document.getElementById('audit-action').value;
  const t = document.getElementById('audit-target-user').value;
  if (s) params.set('start', s);
  if (e) params.set('end', e);
  if (a) params.set('action', a);
  if (t) params.set('target_user_id', t);
  try {
    const res = await fetch('/api/audit?' + params.toString());
    if (!res.ok) throw new Error((await res.json()).error || 'API hatası');
    const data = await res.json();
    if (count) count.textContent = `${data.rows.length} / ${data.total} kayıt`;
    if (!data.rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-muted);font-size:12px">Bu filtrelerle kayıt bulunamadı.</td></tr>';
      return;
    }
    tbody.innerHTML = data.rows.map(r => {
      const label = AUDIT_ACTION_LABELS[r.action] || r.action;
      const color = AUDIT_ACTION_COLORS[r.action] || 'var(--text-muted)';
      const dt = r.created_at ? new Date(r.created_at) : null;
      const dtStr = dt ? dt.toLocaleString('tr-TR', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
      return `<tr>
        <td style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--text-muted)">${dtStr}</td>
        <td><span style="font-size:10px;padding:2px 8px;border-radius:4px;background:${color};color:#fff;font-weight:600;white-space:nowrap">${escapeHtml(label)}</span></td>
        <td style="font-size:12px">${escapeHtml(r.actor_name || '—')}</td>
        <td style="font-size:12px;color:var(--text-muted)">${escapeHtml(r.target_name || '—')}</td>
        <td style="font-size:12px">${escapeHtml(r.summary || '')}</td>
      </tr>`;
    }).join('');
  } catch(err) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--danger);font-size:12px">Hata: ${escapeHtml(err.message)}</td></tr>`;
  }
}

// API to_dict() → frontend format dönüşümü
function normalizeTask(t) {
  return {
    id:       t.id,
    title:    t.title,
    cat:      t.category,      // API: category → FE: cat
    priority: t.priority || 'orta',
    period:   t.period,
    firm:     t.firm,
    team:     t.team,
    notes:    t.notes || '',
    deadline: t.deadline,
    done:     t.is_done,       // API: is_done → FE: done
    startDate: t.created_at ? t.created_at.substring(0,10) : null,
    backup:         t.has_backup ? '(dosya var)' : null,
    alarm:          (t.alarm_enabled !== undefined && t.alarm_enabled !== null) ? !!t.alarm_enabled : (t.alarm !== undefined ? t.alarm : true),
    last_notified:  t.last_notified || null,
    mailSent:       !!t.last_notified,
    last_completed: t.last_completed || null,
    next_due:       t.next_due || null,
    checklist:           t.checklist || [],
    checklist_done:      t.checklist_done || [],
    project_status:      t.project_status || '',
    manager_note:        t.manager_note || '',
    assigned_by:         t.assigned_by || null,
    completed_at:        t.completed_at || null,
    from_previous_month: t.from_previous_month || false,
    sla:                 t.sla || null,
  };
}

// ══════════════════════════════════════════════════════════
//  NAVIGATION
// ══════════════════════════════════════════════════════════
// v5.0 BUG-2 — Mobil sidebar hamburger toggle.
// Desktop/tablet'te etkisi yok (>720px CSS sidebar her zaman görünür).
// Mobil'de .open class'ı sidebar'ı slide-in yapar, backdrop ile kapatılabilir.
function toggleSidebar(forceClose) {
  const sb = document.getElementById('sidebar');
  const bd = document.getElementById('sidebar-backdrop');
  const btn = document.getElementById('sidebar-toggle-btn');
  if (!sb) return;
  const willOpen = forceClose === true ? false : !sb.classList.contains('open');
  sb.classList.toggle('open', willOpen);
  bd?.classList.toggle('show', willOpen);
  btn?.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  btn?.setAttribute('aria-label', willOpen ? 'Menüyü kapat' : 'Menüyü aç');
}

function showPage(name) {
  // v5.0 BUG-2 — mobile'da menü item'a tıklayınca sidebar otomatik kapansın
  toggleSidebar(true);
  // Yetki guard: Junior sadece izinli sayfalara erişebilir
  const level = (currentUser.permission_level || 'junior');
  if (level === 'junior' && !JUNIOR_ALLOWED_PAGES.includes(name)) return;
  // Board guard: can_access_board veya super_admin
  if (name === 'board' && !currentUser.can_access_board && level !== 'super_admin') return;
  // v4.4 — Denetim sayfası yalnızca director+
  if (name === 'audit' && !(level === 'super_admin' || level === 'it_director')) return;

  document.querySelectorAll('.page-section').forEach(p => p.classList.remove('active'));
  document.getElementById('page-'+name)?.classList.add('active');
  // v5.0 BUG-3 fix: nav active highlight için onclick içinde tam showPage('name')
  // call'unu regex ile match et. Eski `.includes("'"+name+"'")` yöntemi başka
  // onclick'lerde aynı string parçasını içeren item'ları da yanlışlıkla aktif
  // bırakabiliyordu (örn. settings butonu içinde 'audit' modal kapama mantığı varsa).
  document.querySelectorAll('.nav-item').forEach(n => {
    const m = (n.getAttribute('onclick') || '').match(/showPage\(['"]([^'"]+)['"]\)/);
    n.classList.toggle('active', !!(m && m[1] === name));
  });
  if (name==='dashboard') renderDashboard();
  if (name==='tasks')     { _ftCat = 'task'; loadTasks().then(() => { document.getElementById('tasks-cat-filter').value = 'task'; renderFullList(tasks.filter(t => t.cat === 'task' || t.cat === 'backup')); }); }
  if (name==='projects')  { loadTasks().then(() => renderProjectsPage()); }
  if (name==='add')       { applyJuniorTaskRestrictions(); applyAssignModeDefaults(); onCatChange(); refreshAssignModeUI(); }
  if (name==='audit')     { initAuditPage(); }
  if (name==='backups')   renderBackupList();
  if (name==='admin')     loadAndRenderUsers();
  if (name==='settings')  { loadFirmsFromDB().then(() => renderSettingsTeams()); loadSettingsFromServer(); applySettingsPermissions(); }
  if (name==='notifications') loadNotificationsPage();
  if (name==='scheduled') { loadTasks().then(() => renderScheduledPage()); }
  if (name==='report')    initReportPage();
  if (name==='board')     renderBoard();
}

// ══════════════════════════════════════════════════════════
//  DASHBOARD RENDER
// ══════════════════════════════════════════════════════════
function renderDashboard() {
  const now = new Date();
  const el = document.getElementById('dash-name');
  // v4.2 — başka kullanıcıyı görüntülüyorsak onun adını göster
  let displayName = (currentUser.full_name || '').split(' ')[0] || 'Hoş Geldiniz';
  if (selectedUserId) {
    const u = firmUsers.find(u => u.id === selectedUserId);
    if (u) displayName = `👁 ${u.full_name}`;
  }
  if (el) el.textContent = displayName;

  // Dinamik selamlama + tarih altyazısı
  const GUN_TR = ['Pazar','Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi'];
  const AY_TR  = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  const hr = now.getHours();
  const greet = (hr < 5) ? 'İyi geceler' : (hr < 12) ? 'Günaydın' : (hr < 18) ? 'İyi günler' : 'İyi akşamlar';
  const gEl = document.getElementById('dash-greeting');
  if (gEl) gEl.textContent = greet;

  // "Perşembe · 20 Nisan 2026 · Nisan ayında 11 gün kaldı"
  const gunAdi = GUN_TR[now.getDay()];
  const ayAdi  = AY_TR[now.getMonth()];
  const tarihStr = `${gunAdi} · ${now.getDate()} ${ayAdi} ${now.getFullYear()}`;
  // Ay sonuna kalan gün
  const ayLastDay = new Date(now.getFullYear(), now.getMonth()+1, 0).getDate();
  const kalanGun = ayLastDay - now.getDate();
  const aySonu = (kalanGun === 0)
    ? `${ayAdi} ayının son günü`
    : `${ayAdi} ayında ${kalanGun} gün kaldı`;
  const subEl = document.getElementById('dash-subtitle');
  if (subEl) subEl.textContent = `${tarihStr} · ${aySonu}`;

  const total   = tasks.length;
  const done    = tasks.filter(t => t.done).length;
  const pending = tasks.filter(t => !t.done).length;
  const late    = tasks.filter(t => !t.done && t.deadline && t.deadline < TODAY).length;
  const backups = tasks.filter(t => t.cat === 'backup').length;
  const rate    = total ? Math.round(done/total*100) : 0;

  // KPI kartları — dinamik güncelle (v4.9: backend'den gelen gerçek trend)
  const kpiEls = document.querySelectorAll('.kpi-value');
  const kpiSubs = document.querySelectorAll('.kpi-sub');

  if (kpiEls[0]) { kpiEls[0].textContent = total; if(kpiSubs[0]) kpiSubs[0].textContent = 'Bu dönem'; }
  if (kpiEls[1]) { kpiEls[1].textContent = done;  if(kpiSubs[1]) kpiSubs[1].textContent = `%${rate} oran`; }
  if (kpiEls[2]) { kpiEls[2].textContent = pending; if(kpiSubs[2]) kpiSubs[2].textContent = pending ? 'Aktif görev' : 'Tamamlandı'; }
  if (kpiEls[3]) { kpiEls[3].textContent = late; if(kpiSubs[3]) kpiSubs[3].textContent = late ? 'Müdahale gerek' : 'Temiz'; }
  if (kpiEls[4]) { kpiEls[4].textContent = backups; }

  // v4.9 — Gerçek trend backend'den gelir (asenkron — KPI yenilendikçe rozet eklenir)
  loadKpiTrends();

  dashPage = 0; // dashboard açılışında sayfayı sıfırla
  renderDashboardTaskList();
  renderDashUpcoming();
  renderBars();
  renderTeamBars();
  // v4.7 — dinamik pie chart + firma dağılımı
  renderCategoryPie();
  renderFirmBars();
  // v4.5 — SLA KPI kartları
  loadSlaKpi();
  // v4.9 — IT Müdürü için yönetilen firma şeridi (super_admin/it_director only)
  loadDirectorFirmsStrip();
}

// v4.9 — Gerçek trend rozetleri (backend /api/dashboard/trends)
async function loadKpiTrends() {
  try {
    const url = '/api/dashboard/trends' + (selectedUserId ? `?user_id=${selectedUserId}` : '');
    const r = await fetch(url);
    if (!r.ok) return;
    const data = await r.json();
    const subs = document.querySelectorAll('.kpi-sub');
    const fmt = (n, suffix='') => {
      if (n === 0) return `<span class="kpi-trend flat">◆ değişim yok${suffix}</span>`;
      const cls = n > 0 ? 'up' : 'down';
      const arr = n > 0 ? '▲' : '▼';
      return `<span class="kpi-trend ${cls}">${arr} ${n>0?'+':''}${n}${suffix}</span>`;
    };
    // İyi/kötü algısı: total/done/rate için artı = iyi (yeşil); overdue için artı = kötü (kırmızı)
    const fmtInverse = (n, suffix='') => {
      if (n === 0) return `<span class="kpi-trend flat">◆ değişim yok${suffix}</span>`;
      const cls = n > 0 ? 'down' : 'up';   // overdue arttıysa kırmızı
      const arr = n > 0 ? '▲' : '▼';
      return `<span class="kpi-trend ${cls}">${arr} ${n>0?'+':''}${n}${suffix}</span>`;
    };
    const d = data.delta;
    if (subs[0]) subs[0].innerHTML = `Bu dönem ${fmt(d.total)}`;
    if (subs[1]) subs[1].innerHTML = `%${data.current.rate} oran ${fmt(d.rate, '%')}`;
    if (subs[3]) subs[3].innerHTML = `${data.current.overdue ? 'Müdahale gerek' : 'Temiz'} ${fmtInverse(d.overdue)}`;
  } catch(e) { /* sessiz başarısızlık — rozet yoksa metin kalır */ }
}

// v4.9 — KPI kartı tıklaması → ilgili filtre/sayfaya geçiş
function kpiJump(kind) {
  if (kind === 'backup') { showPage('backups'); return; }
  if (kind === 'overdue') {
    // Tasks sayfasına git, sadece geciken açık görevler
    showPage('tasks');
    setTimeout(() => {
      const filter = document.getElementById('tasks-cat-filter');
      if (filter) filter.value = 'task';
      renderFullList(tasks.filter(t => !t.done && t.deadline && t.deadline < TODAY));
    }, 80);
    return;
  }
  if (kind === 'done' || kind === 'open' || kind === 'all') {
    // Dashboard task widget filtresi
    const tab = document.getElementById('tab-' + (kind === 'all' ? 'all' : kind));
    if (tab) tab.click();
    document.getElementById('task-list-body')?.scrollIntoView({ behavior:'smooth', block:'start' });
  }
}

// v4.7 — KATEGORİ DAĞILIMI: gerçek verilerden pie chart
function renderCategoryPie() {
  const wrap = document.getElementById('dash-pie-wrap');
  if (!wrap) return;

  const CAT_META = {
    routine : { label:'Rutin',       color:'var(--accent)'  },
    support : { label:'Destek',      color:'var(--accent3)' },
    infra   : { label:'Altyapı',     color:'var(--accent2)' },
    backup  : { label:'Backup',      color:'var(--gold)'    },
    project : { label:'Proje',       color:'var(--green)'   },
    other   : { label:'Diğer',       color:'var(--surface3)'}
  };

  const counts = {};
  tasks.forEach(t => {
    const k = (t.cat && CAT_META[t.cat]) ? t.cat : 'other';
    counts[k] = (counts[k] || 0) + 1;
  });

  const total = tasks.length;
  const done  = tasks.filter(t => t.done).length;
  const rate  = total ? Math.round(done / total * 100) : 0;

  if (!total) {
    wrap.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:12px;padding:30px 0">Henüz görev yok</div>';
    return;
  }

  // stroke-dasharray + stroke-dashoffset ile halka dilimleri üret
  const entries = Object.entries(counts).sort((a,b) => b[1] - a[1]);
  let offset = 25; // -90° rotasyon ile 12 saat konumundan başlar
  const circles = [];
  const legend  = [];
  entries.forEach(([cat, n]) => {
    const pct = (n / total) * 100;
    const meta = CAT_META[cat] || CAT_META.other;
    circles.push(`<circle cx="18" cy="18" r="15.9" fill="none" stroke="${meta.color}" stroke-width="3.4" stroke-dasharray="${pct.toFixed(2)} ${(100-pct).toFixed(2)}" stroke-dashoffset="${offset.toFixed(2)}" transform="rotate(-90 18 18)"/>`);
    legend.push(`<div class="legend-item"><div class="legend-dot" style="background:${meta.color}"></div>${meta.label} (${Math.round(pct)}%)</div>`);
    offset = (offset - pct + 100) % 100; // sonraki dilimin başlangıç konumu
  });

  wrap.innerHTML = `
    <div class="chart-wrap">
      <svg width="130" height="130" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--surface3)" stroke-width="3.4"/>
        ${circles.join('')}
        <text x="18" y="19" text-anchor="middle" fill="var(--text)" font-size="5.5" font-family="IBM Plex Mono" font-weight="700">${rate}%</text>
        <text x="18" y="22.5" text-anchor="middle" fill="var(--text-muted)" font-size="3">tamamlandı</text>
      </svg>
      <div class="chart-legend">
        ${legend.join('')}
      </div>
    </div>`;
}

// v4.7 — FİRMA DAĞILIMI: gerçek verilerden progress bars
function renderFirmBars() {
  const el = document.getElementById('dash-firm-bars');
  if (!el) return;
  const firmMap = {};
  tasks.forEach(t => {
    const f = (t.firm && String(t.firm).trim()) || '—';
    firmMap[f] = (firmMap[f] || 0) + 1;
  });
  const sorted = Object.entries(firmMap).sort((a,b) => b[1] - a[1]).slice(0, 6);
  if (!sorted.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px 0">Henüz görev yok</div>';
    return;
  }
  const total = sorted.reduce((s, [,n]) => s + n, 0);
  const colors = ['var(--accent)','var(--gold)','var(--accent3)','var(--accent2)','var(--green)','var(--surface3)'];
  el.innerHTML = sorted.map(([name, n], i) => {
    const pct = Math.round((n / total) * 100);
    return `
      <div class="progress-wrap">
        <div class="progress-label"><span>${name}</span><span style="color:${colors[i]}">${n} görev · %${pct}</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${colors[i]}"></div></div>
      </div>`;
  }).join('');
}

// v4.9 — Yönetilen Firmalar Şeridi (IT Müdürü dashboard'ında)
// Backend: /api/dashboard/firm-summary (super_admin tüm firmaları, it_director managed_firms'ı görür)
// Tıklama (Q3-A): firm-user-filter dropdown o firmanın ilk kullanıcısına auto-set olur
async function loadDirectorFirmsStrip() {
  const stripEl = document.getElementById('director-firms-strip');
  if (!stripEl) return;
  const lvl = (currentUser && currentUser.permission_level) || 'junior';
  // Yetki kapısı — diğer roller için gizli kalır
  if (lvl !== 'super_admin' && lvl !== 'it_director') {
    stripEl.style.display = 'none';
    return;
  }
  try {
    const r = await fetch('/api/dashboard/firm-summary');
    if (!r.ok) { stripEl.style.display = 'none'; return; }
    const data = await r.json();
    // Levent kararı: 1 veya 0 firma yönetiliyorsa şerit gizli (gürültü ekleme)
    if (!Array.isArray(data) || data.length <= 1) {
      stripEl.style.display = 'none';
      return;
    }
    // Levent kararı: ilk 9 kart (slice tavanı, sınırsız scroll değil)
    const firms = data.slice(0, 9);
    const track = document.getElementById('firm-strip-track');
    const countEl = document.getElementById('firm-strip-count');
    if (countEl) countEl.textContent = (data.length > 9 ? `${firms.length}/${data.length}` : `${data.length}`) + ' firma';
    track.innerHTML = firms.map(f => {
      const rateClass = f.rate >= 70 ? 'r-good' : (f.rate >= 40 ? 'r-warn' : (f.rate > 0 ? 'r-bad' : 'r-none'));
      const themeClass = f.slug === 'inventist' ? 'fc-inv' : (f.slug === 'assos' ? 'fc-assos' : '');
      const slaTag = f.sla_breach > 0 ? `<div class="firm-card-sla" title="Açık SLA ihlali">${f.sla_breach} SLA</div>` : '';
      const aria = `${f.name}: ${f.total} görev, ${f.done} tamamlandı, ${f.overdue} gecikmiş, %${f.rate} oran`;
      const slugAttr = escapeHtml(f.slug || '');
      return `
        <div class="firm-card ${themeClass}" role="listitem" tabindex="0"
             data-firm-slug="${slugAttr}"
             onclick="onFirmStripClick('${slugAttr}', this)"
             onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();onFirmStripClick('${slugAttr}', this)}"
             aria-label="${escapeHtml(aria)}">
          ${slaTag}
          <div class="firm-card-top">
            <div class="firm-card-name">${escapeHtml(f.name || f.slug)}</div>
            <div class="firm-card-rate ${rateClass}">${f.total > 0 ? '%' + f.rate : '—'}</div>
          </div>
          <div class="firm-card-progress"><div class="firm-card-progress-fill ${rateClass}" style="width:${f.total > 0 ? f.rate : 0}%"></div></div>
          <div class="firm-card-stats">
            <span>${f.total} görev</span>
            ${f.overdue > 0 ? `<span class="ov">${f.overdue} geciken</span>` : ''}
          </div>
        </div>
      `;
    }).join('');
    stripEl.style.display = 'block';
  } catch (e) {
    console.warn('[firm-strip] yüklenemedi', e);
    stripEl.style.display = 'none';
  }
}

// v4.9 Q3-A — Karta tıklayınca firm-user-filter dropdown o firmanın ilk
// kullanıcısına auto-set olur, dashboard tek-kullanıcı mantığıyla yeniden yüklenir.
function onFirmStripClick(firmSlug, cardEl) {
  // Aktif kart vurgusu (single-select)
  document.querySelectorAll('#firm-strip-track .firm-card').forEach(c => c.classList.remove('active'));
  if (cardEl) cardEl.classList.add('active');

  if (!firmSlug) return;
  // firmUsers (initFirmUserFilter'da yüklenir) içinden bu firma'nın ilk
  // kullanıcısını bul. Self ise filtreyi temizle (kendim).
  const sel = document.getElementById('firm-user-filter');
  if (!sel) return;
  const candidates = (firmUsers || []).filter(u => (u.firm || '') === firmSlug);
  // Önce kendim olmayanı seç (varsa); yoksa kendim
  let pick = candidates.find(u => u.id !== currentUser.id) || candidates[0];
  if (pick && pick.id !== currentUser.id) {
    sel.value = String(pick.id);
  } else {
    sel.value = ''; // Kendim
  }
  onFirmUserChange();
}

// v4.5 — SLA KPI kartlarını yükler
async function loadSlaKpi() {
  const row = document.getElementById('sla-kpi-row');
  if (!row) return;
  try {
    const now = new Date();
    const q = new URLSearchParams();
    q.set('month', now.getMonth() + 1); q.set('year', now.getFullYear());
    if (selectedUserId) q.set('user_id', selectedUserId);
    const r = await fetch('/api/sla/stats?' + q.toString());
    if (!r.ok) { row.style.display = 'none'; return; }
    const s = await r.json();
    if (!s.total) { row.style.display = 'none'; return; }
    row.style.display = '';
    // Compliance
    const comp = s.compliance_pct;
    const compEl = document.getElementById('sla-kpi-compliance');
    compEl.textContent = `%${comp}`;
    compEl.style.color = comp >= 90 ? 'var(--green)' : comp >= 70 ? 'var(--gold)' : 'var(--danger)';
    document.getElementById('sla-kpi-compliance-sub').textContent =
      s.resolved ? `${s.resolved_on_time}/${s.resolved} zamanında` : 'Çözülen ticket yok';
    // Breached
    document.getElementById('sla-kpi-breached').textContent = s.breached;
    document.getElementById('sla-kpi-breached-sub').textContent =
      s.breached ? 'Müdahale gerek' : 'İhlal yok';
    // Avg resolution
    const avg = s.avg_resolution_hours;
    const avgEl = document.getElementById('sla-kpi-avg');
    if (avg > 0) {
      avgEl.textContent = avg >= 24 ? `${Math.round(avg/24*10)/10}g` : `${Math.round(avg*10)/10}s`;
    } else {
      avgEl.textContent = '—';
    }
    document.getElementById('sla-kpi-avg-sub').textContent =
      s.resolved ? `${s.resolved} ticket üzerinden` : 'Destek talepleri';
    // Open
    document.getElementById('sla-kpi-open').textContent = s.open;
    document.getElementById('sla-kpi-open-sub').textContent =
      `Toplam ${s.total} talep`;
  } catch (e) {
    console.warn('[sla] kpi yüklenemedi', e);
    row.style.display = 'none';
  }
}

// ══════════════════════════════════════════════════════════
//  CASCADING FIRM → TEAM
// ══════════════════════════════════════════════════════════
function updateTeamOptions() {
  const firm = document.getElementById('new-firm').value;
  const teamSel = document.getElementById('new-team');
  teamSel.innerHTML = '';
  if (!firm) { teamSel.innerHTML = '<option>— Önce Firma Seçin —</option>'; teamSel.disabled = true; return; }
  teamSel.disabled = false;
  FIRMS[firm].teams.forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; teamSel.appendChild(o); });
}

// ══════════════════════════════════════════════════════════
//  BACKUP SECTION TOGGLE
// ══════════════════════════════════════════════════════════
function onCatChange() {
  const cat       = document.getElementById('new-cat').value;
  const isBackup  = cat === 'backup';
  const isRoutine = cat === 'routine';
  const isProject = cat === 'project';
  const isTask    = cat === 'task';
  const isSupport = cat === 'support';

  // Backup section
  document.getElementById('backup-section').classList.toggle('hidden', !isBackup);

  // Priority: sadece destek taleplerinde
  document.getElementById('priority-row')?.classList.toggle('hidden', !isSupport);

  // Period: sadece rutin görevde anlamlı; diğerlerinde "Tek Seferlik" sabit
  const periodSel = document.getElementById('new-period');
  const periodRow = document.getElementById('deadline-row')?.previousElementSibling;
  if (isRoutine) {
    periodSel.disabled = false;
    if (periodSel.value === 'Tek Seferlik') periodSel.value = 'Aylık';
  } else if (isBackup) {
    periodSel.value = 'Günlük';
    periodSel.disabled = true;
  } else {
    // task veya project: periyot yok, tek seferlik
    periodSel.value = 'Tek Seferlik';
    periodSel.disabled = true;
  }

  // Checklist rutin ve proje görevlerinde
  document.getElementById('checklist-section').classList.toggle('hidden', !(isRoutine || isProject));

  // Rutin bilgi kutusu
  const infoBox = document.getElementById('routine-info-box');
  if (infoBox) infoBox.classList.toggle('hidden', !isRoutine);

  _updateDeadlineHint();
}

function _updateDeadlineHint() {
  const cat    = document.getElementById('new-cat')?.value;
  const period = document.getElementById('new-period')?.value;
  const hint   = document.getElementById('deadline-hint');
  const infoTxt= document.getElementById('routine-info-text');
  const deadlineGrp = document.getElementById('deadline-group');
  const isRoutineRecurring = cat === 'routine' && period && period !== 'Tek Seferlik';

  if (deadlineGrp) {
    deadlineGrp.style.opacity = isRoutineRecurring ? '0.5' : '1';
  }
  if (hint) {
    hint.textContent = isRoutineRecurring
      ? 'Boş bırakırsanız periyota göre otomatik hesaplanır'
      : 'Aşılırsa geciken olarak işaretlenir';
  }
  if (infoTxt && isRoutineRecurring) {
    const map = {
      Günlük:   'Her gün sıfırlanır. Tamamlandığında yarın için otomatik açılır.',
      Haftalık: 'Her Pazartesi sıfırlanır. Tamamlandığında gelecek haftanın başında açılır.',
      Aylık:    'Her ayın 1. günü sıfırlanır. Tamamlandığında gelecek ayın başında açılır.',
      Yıllık:   'Her yılın 1 Ocak tarihinde sıfırlanır.',
    };
    infoTxt.textContent = map[period] || 'Tamamlandığında bir sonraki periyoda otomatik geçer.';
  }
}

// Periyot değişince de hint'i güncelle
document.addEventListener('change', e => {
  if (e.target?.id === 'new-period') _updateDeadlineHint();
  if (e.target?.id === 'edit-task-cat') {
    const cat = e.target.value;
    document.getElementById('edit-priority-row')?.classList.toggle('hidden', cat !== 'support');
  }
});
function toggleBackupSection() { onCatChange(); }
function triggerUpload() { /* input[type=file] zaten tüm alanı kaplıyor */ }
function onFileSelected(input) {
  const file = input.files[0]; if (!file) return;
  const el = document.getElementById('upload-filename');
  el.textContent = '💾 ' + file.name; el.style.display = 'block';
  document.getElementById('upload-zone').classList.add('has-file');
}

// ══════════════════════════════════════════════════════════
//  TASK HELPERS
// ══════════════════════════════════════════════════════════
function dlClass(dl, done) {
  if (done) return 'ok'; if (!dl) return null;
  const diff = (new Date(dl) - new Date(TODAY)) / 86400000;
  return diff < 0 ? 'late' : diff <= 2 ? 'warn' : 'ok';
}
function dlText(dl, done) {
  if (!dl) return null; if (done) return 'Tamamlandı';
  const diff = Math.round((new Date(dl) - new Date(TODAY)) / 86400000);
  if (diff < 0) return `${Math.abs(diff)}g gecikti`;
  if (diff === 0) return 'Bugün son!';
  return `${diff}g kaldı`;
}
function catLabel(cat) {
  return `<span class="tag ${cat}">${CAT_LABELS[cat]||cat}</span>`;
}
function priorityBadge(t) {
  if (!t || t.cat !== 'support') return '';
  const p = (t.priority || 'orta').toLowerCase();
  const cls = p === 'yüksek' ? 'high' : (p === 'düşük' ? 'low' : 'med');
  const label = p === 'yüksek' ? 'Yüksek' : (p === 'düşük' ? 'Düşük' : 'Orta');
  const dot = p === 'yüksek' ? '⬤' : (p === 'düşük' ? '⬤' : '⬤');
  return ` <span class="prio-badge ${cls}" title="Öncelik">${dot} ${label}</span>`;
}
// v4.5 — SLA rozeti (destek talepleri için)
function slaBadge(t) {
  if (!t || t.cat !== 'support' || !t.sla) return '';
  const s = t.sla;
  const tgt = s.target_hours;
  // Çözüldü
  if (t.done && s.resolution_hours != null) {
    const h = s.resolution_hours;
    const label = h >= 24 ? `${Math.round(h/24*10)/10}g` : `${Math.round(h*10)/10}s`;
    if (s.breached) {
      return ` <span class="prio-badge high" title="SLA aşıldı (hedef ${tgt}s)">⚠ SLA ${label}</span>`;
    }
    return ` <span class="prio-badge low" title="SLA içinde çözüldü (hedef ${tgt}s)">✓ SLA ${label}</span>`;
  }
  // Açık görev
  const rem = s.remaining_hours;
  if (s.breached) {
    const over = Math.abs(rem);
    const label = over >= 24 ? `${Math.round(over/24*10)/10}g` : `${Math.round(over*10)/10}s`;
    return ` <span class="prio-badge high" title="SLA aşıldı (hedef ${tgt}s)">⚠ SLA +${label}</span>`;
  }
  const label = rem >= 24 ? `${Math.round(rem/24*10)/10}g` : `${Math.round(rem*10)/10}s`;
  const cls = rem < (tgt * 0.25) ? 'med' : 'low';
  return ` <span class="prio-badge ${cls}" title="SLA kalan süre (hedef ${tgt}s)">⏱ SLA ${label}</span>`;
}
function firmChip(firm) {
  const f = FIRMS[firm]; if (!f) return firm ? `<span class="firm-chip">${firm}</span>` : '';
  return `<span class="firm-chip ${firm}">${f.label}</span>`;
}
// v4.9 — SLA kalan süreyi insan-okur formatta döndürür ("3s 12dk", "1g 4s", "GECİKTİ")
function _slaRemainingHuman(t) {
  if (t.cat !== 'support' || !t.sla) return null;
  const rem = t.sla.remaining_hours;
  if (typeof rem !== 'number') return null;
  if (t.sla.breached || rem < 0) {
    const over = Math.abs(rem);
    if (over >= 24) return { txt: `+${(over/24).toFixed(1)}g`, color: 'var(--danger)' };
    const h = Math.floor(over); const m = Math.round((over - h) * 60);
    return { txt: h ? `+${h}s ${m}dk` : `+${m}dk`, color: 'var(--danger)' };
  }
  if (rem >= 24)  return { txt: `${(rem/24).toFixed(1)}g`, color: 'var(--accent)' };
  const h = Math.floor(rem); const m = Math.round((rem - h) * 60);
  const color = rem < (t.sla.target_hours || 24) * 0.25 ? 'var(--gold)' : 'var(--accent)';
  return { txt: h ? `${h}s ${m}dk` : `${m}dk`, color };
}

function taskRow(t) {
  // v4.9 — destek talepleri için deadline yerine SLA kalan süresi gösterilir (sol kolon: dl-badge)
  let dl;
  const slaRem = _slaRemainingHuman(t);
  if (t.cat === 'support' && slaRem) {
    const cls = (t.sla?.breached || (t.sla?.remaining_hours ?? 99) < 0) ? 'late'
              : ((t.sla?.remaining_hours ?? 99) < (t.sla?.target_hours || 24) * 0.25 ? 'warn' : 'ok');
    dl = `<div class="dl-badge ${cls}" title="SLA: hedef ${t.sla?.target_hours||'?'}s">SLA ${slaRem.txt}</div>`;
  } else {
    dl = t.deadline ? `<div class="dl-badge ${dlClass(t.deadline,t.done)}">${dlText(t.deadline,t.done)}</div>` : '<div></div>';
  }
  // Önceki aydan taşınan görev etiketi
  const prevBadge = t.from_previous_month
    ? `<span style="font-size:9px;background:rgba(244,185,66,.15);color:var(--gold);border-radius:4px;padding:1px 6px;margin-left:4px;border:1px solid rgba(244,185,66,.25)">⏩ Önceki Aydan</span>`
    : '';
  // Checklist ilerleme çubuğu (rutin ve proje görevlerinde)
  let clProgress = '';
  if ((t.cat === 'routine' || t.cat === 'project') && t.checklist && t.checklist.length > 0) {
    const total = t.checklist.length;
    const done2 = (t.checklist_done||[]).filter(Boolean).length;
    const pct   = Math.round(done2/total*100);
    clProgress = `<div style="font-size:9px;color:var(--text-muted);margin-top:2px">
      Adımlar: ${done2}/${total}
      <div class="checklist-progress" style="margin-top:3px"><div class="checklist-progress-fill" style="width:${pct}%"></div></div>
    </div>`;
  }
  // Son tamamlanma
  const lcStr = (t.cat === 'routine' && t.last_completed)
    ? `<div style="font-size:9px;color:var(--accent);margin-top:2px">✓ Son: ${new Date(t.last_completed).toLocaleDateString('tr-TR',{day:'numeric',month:'short'})}</div>`
    : '';
  // v4.3 — IT Müdürü notu (kırmızı kutu)
  const mnStr = (t.manager_note && t.manager_note.trim())
    ? `<div style="margin-top:4px;padding:4px 8px;border-left:3px solid #ef4444;background:rgba(239,68,68,.08);font-size:10px;color:#ef4444;font-weight:600;border-radius:3px">🛡️ ${escapeHtml(t.manager_note)}</div>`
    : '';
  return `
  <div class="task-item" id="ti-${t.id}">
    <div class="cb ${t.done?'done':''}" role="checkbox" aria-checked="${t.done?'true':'false'}" aria-label="${t.done?'Geri al':'Tamamla'}: ${escapeHtml(t.title)}" tabindex="0" onclick="apiToggleTask(${t.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();apiToggleTask(${t.id})}"></div>
    <div>
      <div class="task-title ${t.done?'done':''}">${t.title}</div>
      <div class="task-meta">${catLabel(t.cat)}${priorityBadge(t)}${slaBadge(t)}${prevBadge} ${firmChip(t.firm)} <span>· ${t.team||''}</span> <span>· ${t.period||''}</span></div>
      ${clProgress}${lcStr}${mnStr}
    </div>
    ${dl}
    <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
      <div style="font-size:9px;${t.cat==='support'&&slaRem?`color:${slaRem.color};font-weight:700`:'color:var(--text-muted)'};font-family:'IBM Plex Mono',monospace">${
        t.cat==='support' && slaRem ? `⏱ ${slaRem.txt} kaldı` : (t.deadline ? formatDateTR(t.deadline) : '—')
      }</div>
      <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" onclick="openEditTask(${t.id})">&#9998; Düzenle</button>
    </div>
  </div>`;
}

// ══════════════════════════════════════════════════════════
//  DASHBOARD TASK LIST (sayfalı, 5'er)
// ══════════════════════════════════════════════════════════
let currentFilter = 'all';
let dashPage = 0;
const DASH_PAGE_SIZE = 5;

function filterTasks(f) {
  currentFilter = f;
  dashPage = 0; // filtre değiştiğinde ilk sayfaya dön
  document.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+f)?.classList.add('active');
  renderDashboardTaskList();
}

function setDashPage(p) {
  dashPage = Math.max(0, p);
  renderDashboardTaskList();
}

// v4.7 — akıllı gruplama: geciken → bugün → yarın → ileri → tarihsiz → bitmiş
const DASH_GROUP_META = {
  overdue    : { label:'Geciken',        icon:'🔴', color:'var(--danger)' },
  today      : { label:'Bugün',          icon:'⚡', color:'var(--gold)' },
  tomorrow   : { label:'Yarın',          icon:'📅', color:'var(--accent2)' },
  upcoming   : { label:'İleri Tarih',    icon:'⏭', color:'var(--accent3)' },
  no_deadline: { label:'Tarihsiz',       icon:'—',  color:'var(--text-muted)' },
  done       : { label:'Tamamlandı',     icon:'✓',  color:'var(--green)' }
};
const DASH_GROUP_ORDER = ['overdue','today','tomorrow','upcoming','no_deadline','done'];

function _dashGroupKey(t) {
  if (t.done) return 'done';
  // v4.7.1 — Destek talepleri SLA'ya göre gruplanır (deadline yerine SLA kalan süresi belirler)
  if (t.cat === 'support' && t.sla) {
    if (t.sla.breached) return 'overdue';
    const rem = t.sla.remaining_hours;
    if (typeof rem === 'number') {
      if (rem <= 24)  return 'today';
      if (rem <= 48)  return 'tomorrow';
      return 'upcoming';
    }
  }
  if (!t.deadline) return 'no_deadline';
  const today = TODAY;
  const tomorrow = (() => { const d = new Date(); d.setDate(d.getDate()+1); return d.toISOString().split('T')[0]; })();
  if (t.deadline <  today)    return 'overdue';
  if (t.deadline === today)   return 'today';
  if (t.deadline === tomorrow)return 'tomorrow';
  return 'upcoming';
}

// v4.7.1 — Grup içinde sıralama anahtarı (saat hassasiyetinde)
function _dashSortKey(t) {
  // Destek talepleri: SLA kalan saati → en az kalan en üstte
  if (t.cat === 'support' && t.sla && typeof t.sla.remaining_hours === 'number') {
    return t.sla.remaining_hours; // breached negatif olabilir → en başa gider
  }
  // Diğer: deadline → ISO string sayısal hale çevrilemez, ms cinsinden epoch dönelim
  if (t.deadline) {
    return new Date(t.deadline).getTime() / 3600000; // saat cinsinden
  }
  return Number.POSITIVE_INFINITY;
}

function renderDashboardTaskList() {
  const body = document.getElementById('task-list-body');
  if (!body) return;
  let list = tasks;
  if (currentFilter === 'open') list = tasks.filter(t => !t.done);
  if (currentFilter === 'done') list = tasks.filter(t => t.done);
  if (!list.length) {
    body.innerHTML = '<div style="padding:16px;font-size:12px;color:var(--text-muted);text-align:center">Görev yok</div>';
    return;
  }

  // Gruplara göre sırala (group order + group içinde saat hassasiyetinde — destek için SLA kalan süresi)
  list = [...list].sort((a, b) => {
    const ka = DASH_GROUP_ORDER.indexOf(_dashGroupKey(a));
    const kb = DASH_GROUP_ORDER.indexOf(_dashGroupKey(b));
    if (ka !== kb) return ka - kb;
    return _dashSortKey(a) - _dashSortKey(b);
  });

  const total = list.length;
  const pageCount = Math.ceil(total / DASH_PAGE_SIZE);
  if (dashPage >= pageCount) dashPage = pageCount - 1;
  const start = dashPage * DASH_PAGE_SIZE;
  const slice = list.slice(start, start + DASH_PAGE_SIZE);

  // Grup başlıkları ekleyerek render et (grup değiştiğinde ya da sayfa ilkinde)
  let lastGroup = null;
  let html = slice.map(t => {
    const g = _dashGroupKey(t);
    let prefix = '';
    if (g !== lastGroup) {
      const m = DASH_GROUP_META[g];
      prefix = `<div style="font-size:9px;color:${m.color};font-weight:700;letter-spacing:1.1px;text-transform:uppercase;padding:8px 4px 4px;display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--border);margin-top:${lastGroup?'8px':'0'}"><span>${m.icon}</span><span>${m.label}</span></div>`;
      lastGroup = g;
    }
    return prefix + taskRow(t);
  }).join('');

  if (pageCount > 1) {
    const prevDisabled = dashPage === 0 ? 'disabled' : '';
    const nextDisabled = dashPage >= pageCount - 1 ? 'disabled' : '';
    html += `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 6px 2px;border-top:1px solid var(--border);margin-top:auto">
        <div style="font-size:10px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">
          ${start+1}–${Math.min(start+DASH_PAGE_SIZE, total)} / ${total}
        </div>
        <div style="display:flex;gap:6px;align-items:center">
          <button class="btn btn-outline btn-sm" ${prevDisabled} style="padding:3px 10px;font-size:11px" onclick="setDashPage(${dashPage-1})">‹ Önceki</button>
          <span style="font-size:11px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">
            ${dashPage+1} / ${pageCount}
          </span>
          <button class="btn btn-outline btn-sm" ${nextDisabled} style="padding:3px 10px;font-size:11px" onclick="setDashPage(${dashPage+1})">Sonraki ›</button>
        </div>
      </div>`;
  }
  body.innerHTML = html;
}

// ══════════════════════════════════════════════════════════
//  PROJELER SAYFASI
// ══════════════════════════════════════════════════════════
function renderProjectsPage() {
  const firmFilter = document.getElementById('proj-filter-firm')?.value || '';
  let projs = tasks.filter(t => t.cat === 'project');
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
      ? `<div class="proj-status-note">📌 ${t.project_status}</div>`
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
          <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px;${t.done?'text-decoration:line-through;opacity:.5':''}">${t.title}</div>
          <div style="font-size:10px;color:var(--text-muted);display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            ${firmChip(t.firm)}
            <span>${t.team || ''}</span>
            ${isOverdue ? '<span style="color:var(--danger);font-weight:600">⚠ Gecikti</span>' : ''}
          </div>
          ${statusNote}${clNote}
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;min-width:80px">
          <div style="font-size:10px;color:${dlColor};font-family:'IBM Plex Mono',monospace">${dlStr}</div>
          <div style="display:flex;gap:4px">
            <div class="cb ${t.done?'done':''}" role="checkbox" aria-checked="${t.done?'true':'false'}" aria-label="${t.done?'Geri al':'Tamamla'}: ${escapeHtml(t.title)}" tabindex="0" onclick="apiToggleTask(${t.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();apiToggleTask(${t.id})}" style="width:16px;height:16px;border-radius:4px"></div>
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

// ══════════════════════════════════════════════════════════
//  FULL TASK LIST
// ══════════════════════════════════════════════════════════
let _ftFirm = '', _ftCat = '', _ftSearch = '';
function renderFullList(list) {
  let l = list || tasks;
  if (_ftFirm)   l = l.filter(t => t.firm === _ftFirm);
  if (_ftCat)    l = l.filter(t => t.cat  === _ftCat);
  if (_ftSearch) l = l.filter(t => t.title.toLowerCase().includes(_ftSearch));
  const el = document.getElementById('full-task-list');
  if (el) el.innerHTML = `<div style="padding:4px 18px">${l.map(taskRow).join('')}</div>`;
  const cnt = document.getElementById('task-count-label');
  if (cnt) cnt.textContent = `${l.length} kayıt`;
}
function filterFullByFirm(v) { _ftFirm = v; renderFullList(); }
function filterFullByCat(v)  { _ftCat  = v; renderFullList(); }
function filterFullList(v)   { _ftSearch = v.toLowerCase(); renderFullList(); }

// ══════════════════════════════════════════════════════════
//  API — GÖREV TOGGLE (checkbox)
// ══════════════════════════════════════════════════════════
async function apiToggleTask(id) {
  const t = tasks.find(t => t.id === id); if (!t) return;
  const newDone = !t.done;
  const _now = new Date();
  try {
    const res = await fetch(`/api/tasks/${id}`, {
      method: 'PATCH', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({is_done: newDone, month: _now.getMonth()+1, year: _now.getFullYear()})
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
      renderFullList(tasks);
      renderDashUpcoming();
      buildNotifications();
      if (document.getElementById('page-scheduled')?.classList.contains('active')) renderScheduledPage();
      if (document.getElementById('page-projects')?.classList.contains('active')) renderProjectsPage();
      const nextStr = normalized.next_due ? formatDateTR(normalized.next_due) : '?';
      showToast('ok', `✓ Tamamlandı — sonraki: ${nextStr}`);
    } else {
      Object.assign(t, normalized);
      renderDashboardTaskList();
      renderFullList(tasks);
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
async function addTask() {
  const title = document.getElementById('new-title').value.trim();
  const firm  = document.getElementById('new-firm').value;
  if (!title) { showToast('err','Görev başlığı boş olamaz'); return; }
  if (!firm)  { showToast('err','Firma seçmediniz'); return; }
  const cat = document.getElementById('new-cat').value;
  const backupFile = document.getElementById('backup-file').files[0];
  // v4.3 — atama modu: director+ başka kullanıcıyı görüntülüyorsa görev ona atanır
  const isDirectorUp = currentUser.permission_level === 'super_admin' || currentUser.permission_level === 'it_director';
  const assignTo = (isDirectorUp && selectedUserId && selectedUserId !== currentUser.id) ? selectedUserId : null;
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
    tasks.unshift(normalizeTask(data));
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
      const u = firmUsers.find(u => u.id === assignTo);
      okMsg = `✓ ${u ? u.full_name : 'Kullanıcı'} kişisine görev atandı`;
    } else okMsg = 'Görev eklendi ✓';
    showToast('ok', okMsg);
    showPage(cat === 'backup' ? 'backups' : 'tasks');
  } catch(e) {
    showToast('err', 'Hata: ' + e.message);
  } finally {
    const btn = document.querySelector('#page-add .btn-primary');
    if (btn) { btn.disabled = false; btn.textContent = 'Görevi Kaydet'; }
  }
}

// ══════════════════════════════════════════════════════════
//  CHARTS (gerçek veriden)
// ══════════════════════════════════════════════════════════
function renderBars() {
  // Son 5 günün görev sayısı
  const barEl = document.getElementById('bar-chart');
  if (!barEl) return;
  const days = [];
  for (let i = 4; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    const ds = d.toISOString().split('T')[0];
    const dayTasks = tasks.filter(t => t.startDate === ds);
    days.push({ label: ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'][d.getDay()], c: dayTasks.length, d: dayTasks.filter(t=>t.done).length });
  }
  const max = Math.max(...days.map(d=>d.c), 1);
  barEl.innerHTML = days.map(d => `
    <div class="bar-col">
      <div class="bar-num">${d.c}</div>
      <div class="bar-inner" style="height:80px">
        <div style="position:absolute;bottom:0;width:100%;height:${(d.c/max)*80}px;background:var(--surface3);border-radius:4px 4px 0 0"></div>
        <div style="position:absolute;bottom:0;width:100%;height:${(d.d/max)*80}px;background:var(--accent);border-radius:4px 4px 0 0;opacity:.85"></div>
      </div>
    </div>`).join('');
}

function renderTeamBars() {
  const el = document.getElementById('team-bars'); if (!el) return;
  const teamMap = {};
  tasks.forEach(t => { if (t.team) teamMap[t.team] = (teamMap[t.team]||0) + 1; });
  const sorted = Object.entries(teamMap).sort((a,b)=>b[1]-a[1]).slice(0,5);
  if (!sorted.length) { el.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Henüz görev yok</div>'; return; }
  const max = sorted[0][1];
  const colors = ['var(--accent)','var(--accent3)','var(--accent2)','var(--gold)','var(--green)'];
  el.innerHTML = sorted.map(([name, n], i) => `
    <div class="progress-wrap" style="margin:5px 0">
      <div class="progress-label"><span>${name}</span><span style="color:${colors[i]}">${n}</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${(n/max)*100}%;background:${colors[i]}"></div></div>
    </div>`).join('');
}

// ══════════════════════════════════════════════════════════
//  ADMIN — KULLANICI TABLOSU (API'den)
// ══════════════════════════════════════════════════════════
let INVITATIONS = [];
async function loadAndRenderUsers() {
  try {
    const [uRes, iRes] = await Promise.all([fetch('/api/admin/users'), fetch('/api/admin/invitations')]);
    if (!uRes.ok) { document.getElementById('user-tbody').innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">Yetkisiz erişim</td></tr>'; return; }
    USERS = await uRes.json();
    INVITATIONS = iRes.ok ? await iRes.json() : [];
    renderUserTable();
    renderUserStats();
    renderInvitations();
  } catch(e) { showToast('err', 'Kullanıcılar yüklenemedi: ' + e.message); }
}

function renderUserStats() {
  const total = USERS.length;
  const active = USERS.filter(u => u.active).length;
  const pending = INVITATIONS.length;
  const o365 = USERS.filter(u => u.o365_linked).length;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-active').textContent = active;
  document.getElementById('stat-pending').textContent = pending;
  document.getElementById('stat-o365').textContent = o365;

  // Yetki dağılımı
  const permCounts = {};
  const permLabels = {super_admin:'Super Admin', it_director:'IT Müdürü', it_manager:'IT Yöneticisi', it_specialist:'IT Specialist', junior:'Junior'};
  const permColors = {super_admin:'var(--accent)', it_director:'var(--accent-gold, #f5b400)', it_manager:'var(--accent3)', it_specialist:'var(--accent2)', junior:'var(--text-muted)'};
  USERS.forEach(u => { const p = u.permission_level || 'junior'; permCounts[p] = (permCounts[p]||0)+1; });
  const maxP = Math.max(...Object.values(permCounts), 1);
  document.getElementById('perm-dist-body').innerHTML = Object.entries(permCounts).map(([k,v]) =>
    `<div class="progress-wrap"><div class="progress-label"><span>${permLabels[k]||k}</span><span style="color:${permColors[k]||'var(--text-muted)'}">${v}</span></div><div class="progress-bar"><div class="progress-fill" style="width:${(v/maxP)*100}%;background:${permColors[k]||'var(--text-muted)'}"></div></div></div>`
  ).join('');
}

function renderInvitations() {
  const tbody = document.getElementById('inv-tbody');
  const empty = document.getElementById('inv-empty');
  if (!INVITATIONS.length) { tbody.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';
  tbody.innerHTML = INVITATIONS.map(inv => {
    const expired = new Date(inv.expires_at) < new Date();
    const expLabel = expired ? '<span style="color:var(--red)">Süresi dolmuş</span>' : new Date(inv.expires_at).toLocaleDateString('tr-TR');
    return `<tr>
      <td style="font-size:12px">${inv.full_name || '—'}</td>
      <td style="font-size:11px;font-family:'IBM Plex Mono',monospace">${inv.email}</td>
      <td>${permBadge(inv.role === 'Super Admin' ? 'super_admin' : inv.role === 'IT Müdürü' ? 'it_director' : inv.role === 'IT Yöneticisi' ? 'it_manager' : inv.role === 'IT Specialist' ? 'it_specialist' : 'junior')}</td>
      <td>${firmChip(inv.firm)}</td>
      <td style="font-size:11px">${expLabel}</td>
      <td style="display:flex;gap:6px">
        <button class="btn btn-outline btn-sm" onclick="resendInvite(${inv.id})" title="Yeniden Gönder">&#8634; Gönder</button>
        <button class="btn btn-outline btn-sm" style="color:var(--red);border-color:var(--red)" onclick="cancelInvite(${inv.id})" title="İptal Et">&#10005; İptal</button>
      </td>
    </tr>`;
  }).join('');
}

function permBadge(level) {
  const map = {super_admin:['Super Admin','var(--accent)'], it_director:['IT Müdürü','var(--accent-gold, #f5b400)'], it_manager:['IT Yöneticisi','var(--accent3)'], it_specialist:['IT Specialist','var(--accent2)'], junior:['Junior','var(--text-muted)']};
  const [label, color] = map[level] || map.junior;
  return `<span style="font-size:10px;padding:2px 8px;border-radius:12px;border:1px solid ${color};color:${color};font-family:'IBM Plex Mono',monospace">${label}</span>`;
}

function renderUserTable() {
  document.getElementById('user-tbody').innerHTML = USERS.map(u => `
    <tr>
      <td><div style="font-weight:600;font-size:12px">${u.full_name}</div><div style="font-size:10px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">${u.username}</div></td>
      <td><span style="font-size:11px;color:var(--text-muted)">${u.role || '—'}</span></td>
      <td>${permBadge(u.permission_level)}</td>
      <td>${firmChip(u.firm)}</td>
      <td><span class="status-dot ${u.active?'active':'inactive'}"></span><span style="font-size:11px">${u.active?'Aktif':'Pasif'}</span></td>
      <td style="display:flex;gap:6px">
        <button class="btn btn-outline btn-sm" onclick="openEditUser(${u.id})">&#9998; Düzenle</button>
      </td>
    </tr>`).join('');
}

async function resendInvite(id) {
  try {
    const res = await fetch(`/api/admin/invitations/${id}/resend`, {method:'POST'});
    const data = await res.json();
    if (data.ok) { showToast('ok','Davet maili yeniden gönderildi'); loadAndRenderUsers(); }
    else showToast('err', data.error || 'Gönderilemedi');
  } catch(e) { showToast('err', e.message); }
}
async function cancelInvite(id) {
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
function openInviteModal() {
  // IT Müdürü seçeneği sadece Super Admin'e görünür
  const dirOpt = document.querySelector('#inv-perm option[value="it_director"]');
  if (dirOpt) dirOpt.style.display = (currentUser.permission_level === 'super_admin') ? '' : 'none';
  document.getElementById('invite-modal').classList.remove('hidden');
}
function closeModal() { document.getElementById('invite-modal').classList.add('hidden'); }
async function sendInvite() {
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

// ══════════════════════════════════════════════════════════
//  SETTINGS — EKİP YÖNETİMİ (local FIRMS objesi)
// ══════════════════════════════════════════════════════════
function renderSettingsTeams() {
  ['inventist','assos'].forEach(firm => {
    const el = document.getElementById(`${firm}-teams-display`);
    if (!el) return;
    el.innerHTML = FIRMS[firm].teams.map(t => {
      const tid = FIRMS[firm].teamIds[t] || '';
      return `<span class="pill-tag" onclick="removeTeam('${firm}','${t}',${tid})">${t} <span class="rm">×</span></span>`;
    }).join('');
  });
  renderBackupTypes();
}
async function addTeam(firm) {
  const inp = document.getElementById(`${firm}-new-team`); const val = inp.value.trim(); if (!val) return;
  if (FIRMS[firm].teams.includes(val)) { inp.value = ''; return; }
  const fid = FIRMS[firm].id;
  if (!fid) { showToast('err','Firma ID bulunamadı'); return; }
  try {
    const res = await fetch(`/api/firms/${fid}/teams`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:val}) });
    if (!res.ok) { showToast('err','Ekip eklenemedi'); return; }
    const t = await res.json();
    FIRMS[firm].teams.push(t.name);
    FIRMS[firm].teamIds[t.name] = t.id;
    showToast('ok',`"${val}" eklendi`);
  } catch(e) { showToast('err','Hata: '+e.message); }
  inp.value = ''; renderSettingsTeams();
}
async function removeTeam(firm, team, tid) {
  if (!tid) { showToast('err','Ekip ID bulunamadı'); return; }
  if (!confirm(`"${team}" ekibini silmek istediğinize emin misiniz?\nBu ekibe atanmış görevlerden ekip bilgisi kaldırılır.`)) return;
  try {
    const res = await fetch(`/api/teams/${tid}`, { method:'DELETE' });
    if (!res.ok) { showToast('err','Ekip silinemedi'); return; }
    FIRMS[firm].teams = FIRMS[firm].teams.filter(t => t !== team);
    delete FIRMS[firm].teamIds[team];
    showToast('ok',`"${team}" kaldırıldı`);
  } catch(e) { showToast('err','Hata: '+e.message); }
  renderSettingsTeams();
}
function renderBackupTypes() {
  document.getElementById('backup-types-display').innerHTML = BACKUP_TYPES.map(t => `<span class="pill-tag" onclick="removeBackupType('${t}')">${t} <span class="rm">×</span></span>`).join('');
}
function addBackupType() {
  const inp = document.getElementById('backup-new-type'); let val = inp.value.trim(); if (!val) return;
  if (!val.startsWith('.')) val = '.' + val;
  if (!BACKUP_TYPES.includes(val)) { BACKUP_TYPES.push(val); showToast('ok',`${val} eklendi`); }
  inp.value = ''; renderBackupTypes();
}
function removeBackupType(t) { const idx = BACKUP_TYPES.indexOf(t); if (idx > -1) BACKUP_TYPES.splice(idx,1); renderBackupTypes(); }

// ══════════════════════════════════════════════════════════
//  TOAST
// ══════════════════════════════════════════════════════════
function showToast(type, msg) {
  const wrap = document.getElementById('toast-wrap');
  const t = document.createElement('div'); t.className = `toast ${type}`;
  t.innerHTML = `<span>${type==='ok'?'✓':'✗'}</span> ${msg}`;
  wrap.appendChild(t); setTimeout(() => t.remove(), 3500);
}

// ══════════════════════════════════════════════════════════
//  TARİH YARDIMCILARI
// ══════════════════════════════════════════════════════════
function formatDateTR(dateStr) {
  if (!dateStr) return '—';
  const [y, m, d] = dateStr.split('-');
  const aylar = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  return `${parseInt(d)} ${aylar[parseInt(m)-1]} ${y}`;
}
function setDateDisplay(dayId, fullId) {
  const now = new Date();
  const gunler = ['Pazar','Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi'];
  const aylar  = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  const de = document.getElementById(dayId); const fe = document.getElementById(fullId);
  if (de) de.textContent = now.getDate();
  if (fe) fe.textContent = `${aylar[now.getMonth()]} ${now.getFullYear()} · ${gunler[now.getDay()]}`;
}

// ══════════════════════════════════════════════════════════
//  BİLDİRİM SİSTEMİ
// ══════════════════════════════════════════════════════════
let notifications = [];

// v4.9 — Bildirimler artık backend /api/notifications/preview üzerinden gelir
// (rutin gecikmeleri + tüm overdue + SLA warning + SLA breach). Yerel rutin
// scan'i fallback olarak kalır; backend cevapsızsa kullanıcı yine bilgilendirilir.
const NOTIF_READ_KEY = 'itt_notif_read_v1';
function _getReadIds() {
  try { return new Set(JSON.parse(sessionStorage.getItem(NOTIF_READ_KEY) || '[]')); }
  catch(e) { return new Set(); }
}
function _saveReadIds(set) {
  try { sessionStorage.setItem(NOTIF_READ_KEY, JSON.stringify([...set])); }
  catch(e) {}
}

async function buildNotifications() {
  notifications = [];
  const readIds = _getReadIds();

  let backendOk = false;
  try {
    const r = await fetch('/api/notifications/preview');
    if (r.ok) {
      const data = await r.json();
      backendOk = true;
      // Sıralama: breached → overdue → warning
      (data.sla_breached || []).forEach(t => notifications.push({
        id:'sb'+t.id, type:'danger', title:t.title,
        meta:`SLA AŞILDI · ${t.firm||''} ${t.team?'· '+t.team:''}`,
        tag:'late', tagLabel:'SLA AŞILDI', taskId:t.id,
        read: readIds.has('sb'+t.id), mailSent:false, _sortKey:0
      }));
      (data.overdue || []).forEach(t => notifications.push({
        id:'ov'+t.id, type:'danger', title:t.title,
        meta:`${t.days_late||'?'} gün gecikti · ${t.firm||''} ${t.team?'· '+t.team:''}`,
        tag:'late', tagLabel:`${t.days_late||'?'}g gecikti`, taskId:t.id,
        read: readIds.has('ov'+t.id), mailSent:false, _sortKey:1
      }));
      (data.sla_warning || []).forEach(t => {
        const rh = t.sla_remaining_hours;
        const rem = (typeof rh === 'number')
          ? (rh >= 24 ? `${(rh/24).toFixed(1)}g kaldı` : `${rh.toFixed(1)}s kaldı`)
          : 'süresi azaldı';
        notifications.push({
          id:'sw'+t.id, type:'warn', title:t.title,
          meta:`SLA: ${rem} · ${t.firm||''} ${t.team?'· '+t.team:''}`,
          tag:'due', tagLabel:'SLA YAKIN', taskId:t.id,
          read: readIds.has('sw'+t.id), mailSent:false, _sortKey:2
        });
      });
      notifications.sort((a,b) => a._sortKey - b._sortKey);
    }
  } catch(e) { /* sessizce fallback */ }

  if (!backendOk) {
    // Fallback: önceki yerel rutin tarama
    const routines = tasks.filter(t => t.cat === 'routine' && !t.done);
    routines.forEach(t => {
      if (!t.deadline) return;
      const diff = Math.round((new Date(t.deadline) - new Date(TODAY)) / 86400000);
      const id = 'n'+t.id;
      if (diff < -3) {
        notifications.push({ id, type:'danger', title:t.title,
          meta:`${Math.abs(diff)} gün gecikti · ${t.team} · ${(FIRMS[t.firm]||{}).label||t.firm}`,
          tag:'late', tagLabel:`${Math.abs(diff)}g gecikti`, taskId:t.id, read:readIds.has(id), mailSent:t.mailSent||false, diff });
      } else if (diff <= 0 && diff >= -3) {
        notifications.push({ id, type:'warn', title:t.title,
          meta: diff===0 ? 'Bugün tamamlanması gereken görev' : `${Math.abs(diff)} gün gecikti`,
          tag:'due', tagLabel: diff===0?'BUGÜN':'Yakın Gecikme', taskId:t.id, read:readIds.has(id), mailSent:t.mailSent||false, diff });
      } else if (diff === 1) {
        notifications.push({ id, type:'info', title:t.title,
          meta:`Yarın tamamlanması gerekiyor · ${t.team}`,
          tag:'upcoming', tagLabel:'Yarın', taskId:t.id, read:readIds.has(id), mailSent:false, diff });
      }
    });
  }
  updateNotifUI();
}

function updateNotifUI() {
  const unread = notifications.filter(n => !n.read).length;
  const dot = document.getElementById('notif-dot');
  if (dot) dot.style.display = unread > 0 ? 'block' : 'none';
  const overdueCount = tasks.filter(t => t.cat==='routine' && !t.done && t.deadline && t.deadline < TODAY).length;
  const nb = document.getElementById('sched-nav-badge');
  if (nb) { nb.textContent = overdueCount; nb.style.display = overdueCount > 0 ? 'inline-flex' : 'none'; }
  renderNotifList();
}

function renderNotifList() {
  const el = document.getElementById('notif-list'); if (!el) return;
  if (!notifications.length) { el.innerHTML = '<div class="notif-empty">🎉 Tüm rutin görevler zamanında!<br>Gecikme veya uyarı yok.</div>'; return; }
  el.innerHTML = notifications.map(n => `
    <div class="notif-item ${n.read?'':'unread'}" onclick="notifClick('${n.id}',${n.taskId})">
      <div class="notif-icon ${n.type==='danger'?'ndanger':n.type==='warn'?'nwarn':'ninfo'}">${n.type==='danger'?'🔴':n.type==='warn'?'⚠️':'🔔'}</div>
      <div style="flex:1">
        <div class="notif-body-title">${n.title}</div>
        <div class="notif-body-meta">${n.meta}</div>
        <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:3px">
          <span class="notif-tag ${n.tag}">${n.tagLabel}</span>
          ${n.mailSent?'<span class="mail-sent-badge">📧 Mail gönderildi</span>':''}
        </div>
      </div>
    </div>`).join('');
}

function notifClick(notifId, taskId) {
  const n = notifications.find(x => x.id === notifId); if (n) n.read = true;
  const r = _getReadIds(); r.add(notifId); _saveReadIds(r);
  updateNotifUI(); closeNotifDropdown(); openEditTask(taskId);
}
function clearAllNotifs() {
  const r = _getReadIds();
  notifications.forEach(n => { n.read = true; r.add(n.id); });
  _saveReadIds(r);
  updateNotifUI();
}
function toggleNotifDropdown() {
  const dd = document.getElementById('notif-dropdown'); if (!dd) return;
  dd.classList.toggle('hidden');
  if (!dd.classList.contains('hidden')) buildNotifications(); // async — fire & forget
}
function closeNotifDropdown() { document.getElementById('notif-dropdown')?.classList.add('hidden'); }
document.addEventListener('click', e => {
  const wrap = document.getElementById('notif-wrap');
  if (wrap && !wrap.contains(e.target)) closeNotifDropdown();
});

// ══════════════════════════════════════════════════════════
//  ZAMANLANMIŞ GÖREVLER SAYFASI
// ══════════════════════════════════════════════════════════
function renderScheduledPage() {
  setDateDisplay('sched-date-day', 'sched-date-full');
  const routines = tasks.filter(t => t.cat === 'routine');

  // Gruplama — renderScheduledList ile birebir aynı mantık
  const _todayMidnight = new Date(TODAY + 'T00:00:00');
  let _active = [], _done = [];
  routines.forEach(t => {
    const nd = t.next_due       ? new Date(t.next_due + 'T00:00:00') : null;
    const lc = t.last_completed ? new Date(t.last_completed)          : null;
    if (lc && nd && nd > _todayMidnight) _done.push(t);
    else                                  _active.push(t);
  });

  const overdue  = _active.filter(t => t.deadline && t.deadline < TODAY).length;
  const dueSoon  = _active.filter(t => t.deadline && t.deadline >= TODAY &&
    Math.round((new Date(t.deadline)-new Date(TODAY))/86400000) <= 3).length;
  const done     = _done.length;
  document.getElementById('sched-kpi-row').innerHTML = `
    <div class="kpi c-purple" style="animation-delay:.04s"><div class="kpi-icon">🔁</div><div class="kpi-label">Toplam Rutin</div><div class="kpi-value" style="color:var(--accent3)">${routines.length}</div><div class="kpi-sub">Zamanlanmış görev</div></div>
    <div class="kpi c-orange" style="animation-delay:.08s"><div class="kpi-icon">🔴</div><div class="kpi-label">Geciken</div><div class="kpi-value" style="color:var(--danger)">${overdue}</div><div class="kpi-sub">${overdue>0?'Dikkat gerekiyor':'Gecikme yok'}</div></div>
    <div class="kpi c-gold"   style="animation-delay:.12s"><div class="kpi-icon">⚡</div><div class="kpi-label">Bugün / Yakın</div><div class="kpi-value" style="color:var(--gold)">${dueSoon}</div><div class="kpi-sub">3 gün içinde bitmeli</div></div>
    <div class="kpi c-green"  style="animation-delay:.16s"><div class="kpi-icon">✅</div><div class="kpi-label">Tamamlanan</div><div class="kpi-value" style="color:var(--green)">${done}</div><div class="kpi-sub">Bu dönem</div></div>`;
  const periods = {Günlük:0,Haftalık:0,Aylık:0,Yıllık:0};
  routines.forEach(t => { if (periods[t.period] !== undefined) periods[t.period]++; });
  const maxP = Math.max(...Object.values(periods), 1);
  const pColors = {Günlük:'var(--accent3)',Haftalık:'var(--accent)',Aylık:'var(--gold)',Yıllık:'var(--accent2)'};
  document.getElementById('sched-period-dist').innerHTML = Object.entries(periods).map(([k,v]) => `
    <div class="progress-wrap" style="margin-bottom:10px">
      <div class="progress-label"><span>${k}</span><span style="color:${pColors[k]}">${v}</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${v/maxP*100}%;background:${pColors[k]}"></div></div>
    </div>`).join('');
  if (schedView === 'calendar') renderCalendar();
  else renderScheduledList();
}

function renderScheduledList() {
  const periodF = document.getElementById('sf-period')?.value || '';
  const firmF   = document.getElementById('sf-firm')?.value   || '';

  const today = new Date(TODAY);
  const soon  = new Date(TODAY); soon.setDate(soon.getDate() + 7); // 7 gün içi = aktif

  // Tüm rutin görevleri al
  let all = tasks.filter(t => t.cat === 'routine');
  if (periodF) all = all.filter(t => t.period === periodF);
  if (firmF)   all = all.filter(t => t.firm   === firmF);

  // 3 gruba ayır
  const active   = [];  // deadline <= bugün+7 VE tamamlanmamış
  const done     = [];  // last_completed bu periyotta var (is_done=false ama son tamamlanma var)
  const upcoming = [];  // next_due > bugün+7

  const todayMidnight = new Date(TODAY + 'T00:00:00');

  all.forEach(t => {
    const nd = t.next_due       ? new Date(t.next_due + 'T00:00:00') : null;
    const lc = t.last_completed ? new Date(t.last_completed)          : null;

    // Kural 1: TAMAMLANDI (bu periyot bitti)
    // last_completed var VE next_due ileriye atladı (bugünden büyük)
    if (lc && nd && nd > todayMidnight) {
      done.push(t);
    }
    // Kural 2: AKTİF — last_completed yok (hiç yapılmamış) VEYA next_due geçti
    // Yeni eklenen görevler, vadelenenler, gecikenler hepsi buraya
    else {
      active.push(t);
    }
    // NOT: "Gelecek dönem" artık kullanılmıyor — tüm aktif görevler listede görünür
    // next_due tarihi zaten görevde gösteriliyor
  });

  // Sırala
  active.sort((a,b) => {
    const da = a.deadline ? new Date(a.deadline) : new Date('9999-01-01');
    const db2 = b.deadline ? new Date(b.deadline) : new Date('9999-01-01');
    return da - db2;
  });
  upcoming.sort((a,b) => {
    const da = a.next_due ? new Date(a.next_due) : new Date('9999-01-01');
    const db2 = b.next_due ? new Date(b.next_due) : new Date('9999-01-01');
    return da - db2;
  });
  done.sort((a,b) => new Date(b.last_completed) - new Date(a.last_completed));

  // Sayaçlar
  document.getElementById('sched-count-label').textContent = `${active.length} aktif`;
  _setSchedBadge('active',   active.length,   active.filter(t => t.deadline && t.deadline < TODAY).length > 0 ? 'danger' : 'normal');
  _setSchedBadge('done',     done.length,     'done');
  _setSchedBadge('upcoming', upcoming.length, 'upcoming');

  // ── AKTİF ──
  const activeBody = document.getElementById('sched-list-body');
  if (activeBody) {
    if (!active.length) {
      activeBody.innerHTML = '<div class="sched-section-empty">🎉 Bu dönemde tüm görevler tamamlandı veya henüz vakti gelmedi.</div>';
    } else {
      activeBody.innerHTML = active.map(t => _renderSchedRow(t)).join('');
    }
  }

  // ── TAMAMLANDI ──
  const doneBody = document.getElementById('sched-list-done');
  if (doneBody) {
    if (!done.length) {
      doneBody.innerHTML = '<div class="sched-section-empty">Henüz bu periyotta tamamlanan görev yok.</div>';
    } else {
      doneBody.innerHTML = done.map(t => {
        const lcDate = t.last_completed ? new Date(t.last_completed).toLocaleDateString('tr-TR',{day:'numeric',month:'long'}) : '—';
        const nextDate = t.next_due ? formatDateTR(t.next_due) : '—';
        return `<div class="sched-done-row">
          <div>
            <div class="sched-done-title">${t.title}</div>
            <div class="sched-done-meta">${firmChip(t.firm)} · ${t.team||''} · ${t.period||''}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
            <span class="last-done-chip">✓ ${lcDate}</span>
            <span style="font-size:9px;color:var(--text-dim)">Sonraki: ${nextDate}</span>
          </div>
        </div>`;
      }).join('');
    }
  }

  // ── GELECEK ──
  const upcomingBody = document.getElementById('sched-list-upcoming');
  if (upcomingBody) {
    if (!upcoming.length) {
      upcomingBody.innerHTML = '<div class="sched-section-empty">Yakın vadede bekleyen görev yok.</div>';
    } else {
      upcomingBody.innerHTML = upcoming.map(t => {
        const nd = t.next_due ? new Date(t.next_due) : null;
        const diffDays = nd ? Math.round((nd - new Date(TODAY)) / 86400000) : null;
        const opensIn = diffDays !== null
          ? (diffDays === 0 ? 'Bugün açılır' : diffDays === 1 ? 'Yarın açılır' : `${diffDays} gün sonra açılır`)
          : '—';
        const lcDate = t.last_completed ? new Date(t.last_completed).toLocaleDateString('tr-TR',{day:'numeric',month:'long'}) : null;
        return `<div class="sched-upcoming-row">
          <div>
            <div class="sched-upcoming-title">${t.title}</div>
            <div class="sched-upcoming-meta">${firmChip(t.firm)} · ${t.team||''} · ${t.period||''}
              ${lcDate ? `· <span style="color:var(--accent);font-size:9px">✓ Son: ${lcDate}</span>` : ''}
            </div>
          </div>
          <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
            <span class="opens-in-chip">📅 ${opensIn}</span>
            <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" onclick="openEditTask(${t.id})">&#9998;</button>
          </div>
        </div>`;
      }).join('');
    }
  }
}

function _setSchedBadge(section, count, type) {
  const el = document.getElementById('sched-badge-' + section);
  if (!el) return;
  el.textContent = count;
  el.style.display = count > 0 ? 'inline-flex' : 'none';
  if (type === 'danger') { el.style.background = 'var(--danger)'; el.style.color = '#fff'; }
  else if (type === 'done') { el.style.background = 'rgba(63,185,80,.2)'; el.style.color = 'var(--green)'; }
  else if (type === 'upcoming') { el.style.background = 'var(--surface3)'; el.style.color = 'var(--text-muted)'; }
  else { el.style.background = 'var(--accent)'; el.style.color = '#000'; }
}

function toggleSchedSection(section) {
  const el = document.getElementById('sched-section-' + section);
  if (el) el.classList.toggle('collapsed');
}

function _renderSchedRow(t) {
  const diff    = t.deadline ? Math.round((new Date(t.deadline) - new Date(TODAY)) / 86400000) : null;
  const nrClass = t.done ? 'done' : diff === null ? 'upcoming' : diff < 0 ? 'overdue' : diff === 0 ? 'today' : 'upcoming';
  const nrText  = t.done ? 'Tamamlandı' : diff === null ? '—' : diff < 0 ? `${Math.abs(diff)}g gecikti` : diff === 0 ? 'BUGÜN' : diff === 1 ? 'Yarın' : formatDateTR(t.deadline);
  const rowClass = t.done ? '' : diff !== null && diff < 0 ? 'row-overdue' : diff !== null && diff <= 1 ? 'row-due' : '';
  const alarmOn  = t.alarm || false;
  const pColor = {Günlük:'var(--accent3)',Haftalık:'var(--accent)',Aylık:'var(--gold)',Yıllık:'var(--accent2)','Tek Seferlik':'var(--text-muted)'}[t.period]||'var(--text-muted)';
  const pBg    = {Günlük:'rgba(127,108,247,.15)',Haftalık:'rgba(0,229,192,.12)',Aylık:'rgba(244,185,66,.12)',Yıllık:'rgba(255,95,61,.12)','Tek Seferlik':'var(--surface2)'}[t.period]||'var(--surface2)';
  return `
  <div class="sched-row ${rowClass}" id="sr-${t.id}">
    <div class="cb ${t.done?'done':''}" role="checkbox" aria-checked="${t.done?'true':'false'}" aria-label="${t.done?'Geri al':'Tamamla'}: ${escapeHtml(t.title)}" tabindex="0" onclick="apiToggleTask(${t.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();apiToggleTask(${t.id})}" title="${t.done?'Geri al':'Tamamlandı işaretle'}"></div>
    <div style="min-width:0">
      <div style="font-size:13px;font-weight:500;${t.done?'text-decoration:line-through;color:var(--text-muted)':''};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.title}</div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:3px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        ${firmChip(t.firm)} <span>· ${t.team||''}</span>
        ${t.last_notified ? `<span title="Son bildirim: ${formatDateTR(t.last_notified.substring(0,10))}" style="color:var(--accent3);font-size:9px">📧 bildirildi</span>` : ''}
      </div>
    </div>
    <div>
      <div class="next-run-chip ${nrClass}">${nrText}</div>
      ${t.deadline?`<div style="font-size:9px;color:var(--text-dim);margin-top:3px;font-family:'IBM Plex Mono',monospace">${formatDateTR(t.deadline)}</div>`:''}
    </div>
    <div><span class="period-badge" style="background:${pBg};color:${pColor}">${t.period}</span></div>
    <div style="display:flex;flex-direction:column;gap:5px">
      <label class="alarm-toggle" onclick="toggleAlarm(${t.id})">
        <div class="alarm-switch ${alarmOn?'on':''}"></div>
        <span style="font-size:10px;color:var(--text-muted)">${alarmOn?'Açık':'Kapalı'}</span>
      </label>
      <button class="btn btn-outline btn-sm" style="padding:2px 8px;font-size:9px" onclick="openEditTask(${t.id})">&#9998; Düzenle</button>
    </div>
  </div>`;
}


async function toggleAlarm(taskId) {
  const t = tasks.find(t => t.id === taskId); if (!t) return;
  const next = !t.alarm;
  t.alarm = next;
  renderScheduledList(); buildNotifications();
  try {
    const r = await fetch(`/api/tasks/${taskId}/alarm`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alarm_enabled: next })
    });
    if (!r.ok) throw new Error((await r.json()).error || 'Sunucu hatası');
    showToast('ok', next ? `🔔 Alarm açıldı` : `Alarm kapatıldı`);
  } catch(err) {
    // Başarısızsa geri al
    t.alarm = !next;
    renderScheduledList(); buildNotifications();
    showToast('error', `Alarm değiştirilemedi: ${err.message}`);
  }
}

// ══════════════════════════════════════════════════════════
//  TAKVİM
// ══════════════════════════════════════════════════════════
let schedView = 'list';
let calYear  = new Date().getFullYear();
let calMonth = new Date().getMonth(); // 0-indexed

function toggleSchedView(view) {
  schedView = view;
  const listEl = document.getElementById('sched-list-view');
  const calEl  = document.getElementById('sched-cal-view');
  if (listEl) listEl.style.display = view === 'list' ? '' : 'none';
  if (calEl)  calEl.style.display  = view === 'calendar' ? '' : 'none';
  document.getElementById('sched-btn-list')?.classList.toggle('active', view === 'list');
  document.getElementById('sched-btn-cal')?.classList.toggle('active', view === 'calendar');
  if (view === 'calendar') renderCalendar();
}

function renderCalendar() {
  const routines = tasks.filter(t => t.cat === 'routine');
  const yr = calYear, mo = calMonth;
  const MONTHS_TR = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  const el = document.getElementById('cal-month-title');
  if (el) el.textContent = `${MONTHS_TR[mo]} ${yr}`;

  // Periyot filtresine göre filtrele (liste ile aynı filtreler)
  const periodF = document.getElementById('sf-period')?.value || '';
  const firmF   = document.getElementById('sf-firm')?.value   || '';
  let filtered = routines;
  if (periodF) filtered = filtered.filter(t => t.period === periodF);
  if (firmF)   filtered = filtered.filter(t => t.firm === firmF);

  // Görev tarih haritası: "YYYY-MM-DD" -> [{task, chipClass}]
  const taskMap = {};
  filtered.forEach(t => {
    // Her görevi deadline'ına yerleştir; yoksa next_due'ya
    const dateStr = t.deadline || t.next_due;
    if (!dateStr) return;
    if (!taskMap[dateStr]) taskMap[dateStr] = [];
    const diff = Math.round((new Date(dateStr) - new Date(TODAY)) / 86400000);
    const chipClass = t.done ? 'done' : diff < 0 ? 'overdue' : diff === 0 ? 'cal-today' : 'upcoming';
    taskMap[dateStr].push({ task: t, chipClass });
  });

  // Takvim ızgarası
  const firstDay  = new Date(yr, mo, 1);
  const lastDay   = new Date(yr, mo + 1, 0);
  const startDow  = (firstDay.getDay() + 6) % 7; // Pazartesi = 0
  const totalDays = lastDay.getDate();

  const cells = [];
  for (let i = startDow - 1; i >= 0; i--) {
    cells.push({ date: new Date(yr, mo, -i), otherMonth: true });
  }
  for (let d = 1; d <= totalDays; d++) {
    cells.push({ date: new Date(yr, mo, d), otherMonth: false });
  }
  const rem = cells.length % 7;
  if (rem > 0) {
    for (let i = 1; i <= 7 - rem; i++) {
      cells.push({ date: new Date(yr, mo + 1, i), otherMonth: true });
    }
  }

  const DOW = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
  let html = '<div class="cal-grid">';
  DOW.forEach(d => { html += `<div class="cal-dow">${d}</div>`; });

  cells.forEach(cell => {
    const ds = cell.date.toISOString().split('T')[0];
    const isToday = ds === TODAY;
    const dayTasks = taskMap[ds] || [];
    const cellCls = ['cal-cell',
      cell.otherMonth ? 'other-month' : '',
      isToday ? 'today' : '',
      dayTasks.length ? 'has-tasks' : ''
    ].filter(Boolean).join(' ');

    html += `<div class="${cellCls}">`;
    html += `<div class="cal-day-num">${cell.date.getDate()}</div>`;
    const MAX = 3;
    dayTasks.slice(0, MAX).forEach(({ task, chipClass }) => {
      html += `<div class="cal-task-chip ${chipClass}" onclick="openEditTask(${task.id})" title="${task.title.replace(/"/g,'&quot;')}">${task.title}</div>`;
    });
    if (dayTasks.length > MAX) {
      html += `<div class="cal-more">+${dayTasks.length - MAX} daha</div>`;
    }
    html += '</div>';
  });

  html += '</div>';
  const container = document.getElementById('cal-grid-container');
  if (container) container.innerHTML = html;
}

function calNavMonth(dir) {
  calMonth += dir;
  if (calMonth > 11) { calMonth = 0; calYear++; }
  if (calMonth < 0)  { calMonth = 11; calYear--; }
  renderCalendar();
}

function calGoToday() {
  calYear  = new Date().getFullYear();
  calMonth = new Date().getMonth();
  renderCalendar();
}

function renderDashUpcoming() {
  const upcoming = tasks.filter(t => t.cat==='routine' && !t.done && t.deadline).sort((a,b)=>new Date(a.deadline)-new Date(b.deadline)).slice(0,4);
  const cnt = document.getElementById('dash-sched-count'); if (cnt) cnt.textContent = upcoming.length;
  const el = document.getElementById('dash-upcoming-list'); if (!el) return;
  if (!upcoming.length) { el.innerHTML = '<div style="padding:12px 0;font-size:12px;color:var(--text-muted);text-align:center">Hepsi zamanında 🎉</div>'; return; }
  el.innerHTML = upcoming.map(t => {
    const diff = Math.round((new Date(t.deadline)-new Date(TODAY))/86400000);
    const cls  = diff<0?'late':diff<=1?'warn':'ok';
    const txt  = diff<0?`${Math.abs(diff)}g gecikti`:diff===0?'BUGÜN':`${diff}g kaldı`;
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px">
      <div style="flex:1;min-width:0"><div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.title}</div><div style="font-size:10px;color:var(--text-muted)">${t.period} · ${t.team||''}</div></div>
      <div class="dl-badge ${cls}" style="margin-left:8px;flex-shrink:0">${txt}</div>
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════════
const TODAY = new Date().toISOString().split('T')[0];
document.addEventListener('DOMContentLoaded', () => { const s = document.getElementById('new-start'); if (s) s.value = TODAY; });
const _startEl = document.getElementById('new-start'); if (_startEl) _startEl.value = TODAY;

setDateDisplay('topbar-date-day', 'topbar-date-full');
loadApp();

// ══════════════════════════════════════════════════════════
//  EDIT TASK MODAL — API bağlı
// ══════════════════════════════════════════════════════════
function openEditTask(id) {
  const t = tasks.find(t => t.id === id); if (!t) return;
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
  const isDirectorUp = currentUser.permission_level === 'super_admin' || currentUser.permission_level === 'it_director';
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
function updateEditTeamOptions() {
  const firm = document.getElementById('edit-task-firm').value;
  const sel  = document.getElementById('edit-task-team');
  sel.innerHTML = '';
  if (FIRMS[firm]) FIRMS[firm].teams.forEach(name => {
    const o = document.createElement('option'); o.value = name; o.textContent = name; sel.appendChild(o);
  });
}
async function saveEditTask() {
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
  const isDirectorUp = currentUser.permission_level === 'super_admin' || currentUser.permission_level === 'it_director';
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
    const idx = tasks.findIndex(t => t.id === id);
    if (idx > -1) tasks[idx] = normalizeTask(updated);
    closeEditTaskModal();
    renderDashboardTaskList();
    renderFullList(tasks);
    renderDashUpcoming();
    buildNotifications();
    showToast('ok', 'Görev güncellendi ✓');
  } catch(e) { showToast('err', 'Güncelleme hatası: ' + e.message); }
}
async function saveAndCompleteTask() {
  const id = parseInt(document.getElementById('edit-task-id').value);
  const t  = tasks.find(t => t.id === id);
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
    const idx = tasks.findIndex(t => t.id === id);
    if (idx > -1) tasks[idx] = normalizeTask(updated);
    closeEditTaskModal();
    renderDashboardTaskList();
    renderFullList(tasks);
    if (document.getElementById('page-scheduled')?.classList.contains('active')) renderScheduledPage();
    if (document.getElementById('page-projects')?.classList.contains('active'))  renderProjectsPage();
    renderDashUpcoming();
    buildNotifications();
    showToast('ok', '✓ Görev kaydedildi ve tamamlandı');
  } catch(e) { showToast('err', 'Hata: ' + e.message); }
}

async function deleteTask() {
  const id = parseInt(document.getElementById('edit-task-id').value);
  if (!confirm('Bu görevi silmek istediğinizden emin misiniz?')) return;
  try {
    const res = await fetch(`/api/tasks/${id}`, { method:'DELETE' });
    if (!res.ok) throw new Error('Silme hatası');
    tasks.splice(tasks.findIndex(t => t.id === id), 1);
    closeEditTaskModal();
    renderDashboardTaskList();
    renderFullList(tasks);
    renderDashUpcoming();
    buildNotifications();
    if (document.getElementById('page-backups')?.classList.contains('active')) renderBackupList();
    if (document.getElementById('page-projects')?.classList.contains('active')) renderProjectsPage();
    showToast('ok', 'Görev silindi');
  } catch(e) { showToast('err', e.message); }
}
function closeEditTaskModal() { document.getElementById('edit-task-modal').classList.add('hidden'); }

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
          <div style="font-size:11px;font-weight:600;color:var(--gold);font-family:'IBM Plex Mono',monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${b.filename}</div>
          <div style="font-size:9px;color:var(--text-muted)">${sizeStr}${b.device?' · '+b.device:''} · ${date}</div>
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0">
          <button class="btn btn-sm" style="padding:2px 8px;font-size:9px;background:var(--gold-dim);border:1px solid rgba(244,185,66,.25);color:var(--gold)" onclick="downloadBackup(${b.id})">&#8595;</button>
          <button class="btn btn-sm btn-danger" style="padding:2px 8px;font-size:9px" onclick="deleteBackupFile(${b.id}, ${taskId})">&#10005;</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML = '<div style="font-size:11px;color:var(--danger)">Yüklenemedi</div>'; }
}

async function deleteBackupFile(backupId, taskId) {
  if (!confirm('Bu dosyayı silmek istediğinizden emin misiniz?')) return;
  try {
    const res = await fetch(`/api/backups/${backupId}`, { method:'DELETE' });
    if (!res.ok) throw new Error('Silme hatası');
    showToast('ok', 'Dosya silindi');
    loadTaskBackups(taskId);
    if (document.getElementById('page-backups')?.classList.contains('active')) renderBackupList();
  } catch(e) { showToast('err', e.message); }
}

async function uploadBackupToTask() {
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

// ══════════════════════════════════════════════════════════
//  EDIT USER MODAL — API bağlı
// ══════════════════════════════════════════════════════════
function openEditUser(id) {
  id = parseInt(id);
  const u = USERS.find(u => u.id === id); if (!u) return;
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
  const canAssignTop = (currentUser.permission_level === 'super_admin');
  if (saOpt) saOpt.style.display = canAssignTop ? '' : 'none';
  if (dirOpt) dirOpt.style.display = canAssignTop ? '' : 'none';
  // IT Müdürü düzenleniyorsa ve ben SA değilsem modalı açma
  if (u.permission_level === 'it_director' && !canAssignTop) {
    showToast('err', 'IT Müdürü kullanıcısını düzenleme yetkiniz yok');
    return;
  }
  // Super Admin düzenleniyorsa ve ben SA değilsem modalı açma
  if (u.permission_level === 'super_admin' && currentUser.permission_level !== 'super_admin') {
    showToast('err', 'Super Admin kullanıcısını düzenleme yetkiniz yok');
    return;
  }
  // Board erişim checkbox
  document.getElementById('edit-user-board-access').checked = !!u.can_access_board;
  // Board toggle sadece super_admin'e görünür
  document.getElementById('edit-user-board-group').style.display = (currentUser.permission_level === 'super_admin') ? '' : 'none';
  document.getElementById('edit-user-modal').classList.remove('hidden');
}
async function saveEditUser() {
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
  if (currentUser.permission_level === 'super_admin') {
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
function closeEditUserModal() {
  document.getElementById('edit-user-modal').classList.add('hidden');
}

// ══════════════════════════════════════════════════════════
//  YEDEKLER SAYFASI
// ══════════════════════════════════════════════════════════
function getBackupTasks() {
  return tasks.filter(t => t.cat === 'backup' && t.backup);
}

function formatFileSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

async function renderBackupList() {
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
        <div style="font-size:13px;font-weight:500">${b.task_title || '—'}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:4px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          ${firmChip(b.firm||'')}
          <span>· ${b.team||''}</span>
          <span>· ${uploadDate}</span>
        </div>
        <div style="margin-top:6px;display:flex;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--border2);border-radius:6px;padding:6px 10px;width:fit-content">
          <span style="font-size:18px">💾</span>
          <div>
            <div style="font-size:11px;font-weight:600;color:var(--gold);font-family:'IBM Plex Mono',monospace">${b.filename}</div>
            <div style="font-size:9px;color:var(--text-muted)">${sizeStr}${b.device?' · '+b.device:''}</div>
          </div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:5px;align-items:flex-end;min-width:80px">
        <button class="btn btn-outline btn-sm" style="padding:3px 9px;font-size:10px;width:80px" onclick="openEditTask(${b.task_id})">&#9998; Görev</button>
        <button class="btn btn-sm" style="padding:3px 9px;font-size:10px;width:80px;background:var(--gold-dim);border:1px solid rgba(244,185,66,.25);color:var(--gold)" onclick="downloadBackup(${b.id})">&#8595; İndir</button>
      </div>
    </div>`;
  }).join('');
}

function filterBackups() {
  renderBackupList();
}

function downloadBackup(backupId) {
  window.location.href = '/api/backups/' + backupId + '/download';
}



// ══════════════════════════════════════════════════════════
//  SETTINGS SAVE — Backend'e bağlı
// ══════════════════════════════════════════════════════════

// Ayarlar sayfası açılınca sunucudan gerçek verileri yükle
async function loadSettingsFromServer() {
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

async function saveUserSettings() {
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
    // USERS dizisini güncelle
    const me = USERS.find(u => u.username === 'lmc' || u.id === 1);
    if (me) { me.name = data.full_name; me.username = data.username; me.email = data.email; me.role = data.role; }
    showToast('ok', 'Kullanici bilgileri kaydedildi — yeni kullanici adi: ' + data.username);
    renderUserTable();
  } catch(e) {
    showToast('err', 'Sunucu hatasi: ' + e.message);
  }
}

async function saveSmtpSettings() {
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

async function testSmtp() {
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

// ══════════════════════════════════════════════════════════
//  BİLDİRİM AYARLARI (v4.6)
// ══════════════════════════════════════════════════════════
async function loadNotificationsPage() {
  // Preview alanını temizle
  const box = document.getElementById('notify-preview');
  if (box) { box.style.display = 'none'; box.innerHTML = ''; }
  try {
    const nRes = await fetch('/api/notifications/settings');
    if (!nRes.ok) return;
    const n = await nRes.json();
    const o = document.getElementById('notify-overdue');
    const s = document.getElementById('notify-sla-warning');
    const d = document.getElementById('notify-daily-digest');
    if (o) o.checked = !!n.notify_overdue;
    if (s) s.checked = !!n.notify_sla_warning;
    if (d) d.checked = !!n.notify_daily_digest;
  } catch(e) { console.warn('Bildirim ayarları yüklenemedi:', e); }
}

async function saveNotificationSettings() {
  const body = {
    notify_overdue:      document.getElementById('notify-overdue')?.checked ?? true,
    notify_sla_warning:  document.getElementById('notify-sla-warning')?.checked ?? true,
    notify_daily_digest: document.getElementById('notify-daily-digest')?.checked ?? true,
  };
  try {
    const r = await fetch('/api/notifications/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Kaydedilemedi');
    showToast('ok', 'Bildirim tercihleri kaydedildi');
  } catch(e) {
    showToast('err', 'Hata: ' + e.message);
  }
}

async function previewNotifications() {
  const box = document.getElementById('notify-preview');
  if (box) { box.style.display='block'; box.textContent = 'Yükleniyor…'; }
  try {
    const r = await fetch('/api/notifications/preview');
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Hata');
    if (!j.total) {
      box.textContent = 'Şu an bildirim gerektiren bir göreviniz yok.';
      return;
    }
    const lines = [];
    lines.push(`Toplam ${j.total} uyarı:`);
    if (j.overdue.length)      lines.push(`• ${j.overdue.length} geciken görev`);
    if (j.sla_breached.length) lines.push(`• ${j.sla_breached.length} SLA aşan destek`);
    if (j.sla_warning.length)  lines.push(`• ${j.sla_warning.length} SLA uyarısı destek`);
    lines.push('');
    const listAll = [...j.overdue.map(t=>`#${t.id} ${t.title} — ${t.days_late}g gecikme`),
                     ...j.sla_breached.map(t=>`#${t.id} ${t.title} — SLA AŞILDI`),
                     ...j.sla_warning.map(t=>`#${t.id} ${t.title} — ${t.sla_remaining_hours}s kaldı`)];
    box.innerHTML = lines.map(escapeHtml).join('<br>') + '<br>' + listAll.map(escapeHtml).join('<br>');
  } catch(e) {
    if (box) box.textContent = 'Hata: ' + e.message;
  }
}

async function runNotificationTest() {
  if (!confirm('Test maili şimdi adresinize gönderilecek. Onaylıyor musunuz?')) return;
  showToast('ok', 'Test maili gönderiliyor…');
  try {
    const r = await fetch('/api/notifications/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Hata');
    const row = (j.results || [])[0];
    if (!row) { showToast('ok', 'Job çalıştı ama kayıt döndürmedi'); return; }
    if (row.skipped) showToast('ok', 'Şu an bildirilecek göreviniz yok (mail atılmadı).');
    else if (row.sent) showToast('ok', `Mail gönderildi: ${row.count} uyarı`);
    else showToast('err', `Gönderim hatası: ${row.error || 'bilinmiyor'}`);
  } catch(e) {
    showToast('err', 'Hata: ' + e.message);
  }
}

// ══════════════════════════════════════════════════════════
//  RAPOR SAYFASI
// ══════════════════════════════════════════════════════════
const MONTH_TR_JS = {1:'Ocak',2:'Şubat',3:'Mart',4:'Nisan',5:'Mayıs',6:'Haziran',
                     7:'Temmuz',8:'Ağustos',9:'Eylül',10:'Ekim',11:'Kasım',12:'Aralık'};
const CAT_LABELS_JS = {routine:'Rutin',support:'Destek',infra:'Altyapı',backup:'Config Backup',other:'Diğer'};

// Alıcı mail — oturumda sakla, sayfa yenilenmesinde sıfırlanmaz
let _reportToMail = '';

function initReportPage() {
  // Ay seçiciyi doldur (son 12 ay)
  const sel = document.getElementById('report-month-sel');
  if (!sel) return;
  sel.innerHTML = '';
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const m = d.getMonth() + 1;
    const y = d.getFullYear();
    const opt = document.createElement('option');
    opt.value = `${y}-${m}`;
    opt.textContent = `${MONTH_TR_JS[m]} ${y}`;
    sel.appendChild(opt);
  }
  // Alıcı mail: daha önce girilmişse onu koru, yoksa /api/me'den çek
  const toEl = document.getElementById('report-to');
  if (_reportToMail) {
    if (toEl) toEl.value = _reportToMail;
  } else {
    fetch('/api/me').then(r => r.json()).then(u => {
      _reportToMail = u.email || '';
      if (toEl && !toEl.value) toEl.value = _reportToMail;
    }).catch(() => {});
  }
  onReportMonthChange();
}

// Alıcı mail her değiştiğinde sakla
document.addEventListener('input', e => {
  if (e.target && e.target.id === 'report-to') {
    _reportToMail = e.target.value;
  }
});

function _getSelectedMonthYear() {
  const sel = document.getElementById('report-month-sel');
  if (!sel || !sel.value) return null;
  const [y, m] = sel.value.split('-').map(Number);
  return { month: m, year: y };
}

async function onReportMonthChange() {
  const my = _getSelectedMonthYear();
  if (!my) return;
  const sub = document.getElementById('report-sub');
  if (sub) sub.textContent = `${MONTH_TR_JS[my.month]} ${my.year} · Gerçek veriler yükleniyor...`;
  const body = document.getElementById('report-stats-body');
  if (body) body.innerHTML = '<div style="padding:24px;text-align:center;font-size:12px;color:var(--text-muted)">Yükleniyor...</div>';
  try {
    const userParam = selectedUserId ? `&user_id=${selectedUserId}` : '';
    const res = await fetch(`/api/tasks?month=${my.month}&year=${my.year}${userParam}`);
    const taskList = await res.json();
    renderReportStats(taskList, my.month, my.year);
  } catch(e) {
    if (body) body.innerHTML = `<div style="padding:24px;text-align:center;font-size:12px;color:var(--danger)">API hatası: ${e.message}</div>`;
  }
}

function renderReportStats(taskList, month, year) {
  const sub = document.getElementById('report-sub');
  if (sub) sub.textContent = `${MONTH_TR_JS[month]} ${year} · ${taskList.length} görev`;
  const body = document.getElementById('report-stats-body');
  if (!body) return;
  if (!taskList.length) {
    body.innerHTML = '<div style="padding:24px;text-align:center;font-size:12px;color:var(--text-muted)">Bu ay için kayıt bulunamadı.</div>';
    return;
  }
  const done = taskList.filter(t => t.is_done).length;
  const total = taskList.length;
  const rate = total ? Math.round(done/total*100) : 0;
  const cats = ['routine','support','infra','backup','other'];
  const catColors = {routine:'var(--accent)',support:'var(--accent3)',infra:'var(--accent2)',backup:'var(--gold)',other:'var(--text-muted)'};
  const catRows = cats.map(c => {
    const all  = taskList.filter(t => t.category === c);
    const comp = all.filter(t => t.is_done).length;
    if (!all.length) return '';
    const pct = Math.round(comp/all.length*100);
    return `<div class="progress-wrap">
      <div class="progress-label"><span>${CAT_LABELS_JS[c]||c}</span><span style="color:${catColors[c]}">${comp}/${all.length}</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${catColors[c]}"></div></div>
    </div>`;
  }).join('');
  body.innerHTML = catRows + `
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
      <div class="progress-wrap">
        <div class="progress-label"><span style="font-weight:600">Genel İlerleme</span><span style="color:var(--green)">${rate}%</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${rate}%;background:var(--green)"></div></div>
      </div>
    </div>`;
}

function previewReportPdf() {
  const my = _getSelectedMonthYear();
  if (!my) { showToast('err', 'Lütfen önce ay seçin'); return; }
  const userParam = selectedUserId ? `&user_id=${selectedUserId}` : '';
  window.open(`/api/report/pdf?month=${my.month}&year=${my.year}${userParam}`, '_blank');
}

async function sendReportMail() {
  const my = _getSelectedMonthYear();
  if (!my) { showToast('err', 'Lütfen önce ay seçin'); return; }
  const to = document.getElementById('report-to')?.value?.trim();
  const cc = document.getElementById('report-cc')?.value?.trim();
  if (!to) { showToast('err', 'Alıcı mail adresi boş olamaz'); return; }
  showToast('ok', 'Mail gönderiliyor, lütfen bekleyin...');
  try {
    const res  = await fetch('/api/report/send', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ month: my.month, year: my.year, cc: cc||null, user_id: selectedUserId || null })
    });
    const data = await res.json();
    if (data.ok) {
      showMailResultModal(true, data.message || 'Mail başarıyla gönderildi', null);
    } else {
      showMailResultModal(false, data.error || 'Bilinmeyen hata', my);
    }
  } catch(e) {
    showMailResultModal(false, `Bağlantı hatası: ${e.message}`, my);
  }
}

function showMailResultModal(success, message, my) {
  const modal = document.getElementById('mail-error-modal');
  const title = document.getElementById('mail-error-title');
  const msgEl = document.getElementById('mail-error-body');
  const hint  = document.getElementById('mail-error-hint');
  if (!modal) return;
  title.textContent = success ? '✅ Mail Gönderildi' : '❌ Mail Gönderilemedi';
  title.style.color = success ? 'var(--green)' : 'var(--danger)';
  msgEl.textContent = message;
  msgEl.style.color = success ? 'var(--text)' : 'var(--danger)';
  // Hata türüne göre ipucu göster
  if (!success) {
    hint.style.display = 'block';
    if (message.includes('kimlik') || message.includes('Authentication') || message.includes('App Password')) {
      hint.textContent = '💡 Office 365 kullanıyorsanız: Ayarlar > SMTP\'de şifre olarak normal şifre yerine uygulama şifresi (App Password) kullanmanız gerekebilir. Azure AD > Kullanıcı > Kimlik Doğrulama bölümünden App Password oluşturabilirsiniz.';
    } else if (message.includes('bağlanam') || message.includes('Connect') || message.includes('Ağ')) {
      hint.textContent = '💡 Sunucuya ulaşılamıyor. SMTP host ve port ayarlarını kontrol edin. Office 365 için: smtp.office365.com:587';
    } else if (message.includes('eksik') || message.includes('SMTP ayar')) {
      hint.textContent = '💡 Ayarlar > SMTP bölümünden SMTP Host, Port, Kullanıcı Adı ve Şifre bilgilerini doldurun.';
    } else {
      hint.textContent = '💡 Hatayı kopyalayarak SMTP sağlayıcınızın destek ekibiyle paylaşabilir veya sistem yöneticinize danışabilirsiniz.';
    }
  } else {
    hint.style.display = 'none';
  }
  modal.classList.remove('hidden');
}

// ══════════════════════════════════════════════════════════
//  CHECKLİST FONKSİYONLARI
// ══════════════════════════════════════════════════════════

// Yeni görev formu — checklist
function _getNewChecklistItems() {
  const items = [];
  document.querySelectorAll('#checklist-items .checklist-item').forEach(el => {
    const lbl = el.querySelector('.checklist-label');
    if (lbl && lbl.textContent.trim()) items.push(lbl.textContent.trim());
  });
  return items;
}

function addChecklistItem() {
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

// Edit modal checklist
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

function addEditChecklistItem() {
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

function saveTeams() { showToast('ok', 'Ekip değişiklikleri otomatik kaydedildi.'); }

// ══════════════════════════════════════════════════════════
//  ORTAK ALAN (BOARD) — Trello Kanban
// ══════════════════════════════════════════════════════════
let boardCards = [];
let boardUsers = [];
const BOARD_COLS = ['todo','in_progress','review','done'];
const COL_LABELS = {todo:'Yapılacak', in_progress:'Devam Eden', review:'İnceleme', done:'Tamamlandı'};

async function renderBoard() {
  try {
    const [cardsRes, usersRes] = await Promise.all([
      fetch('/api/board/cards'),
      fetch('/api/board/users')
    ]);
    if (!cardsRes.ok) { showToast('err','Board yuklenemedi'); return; }
    boardCards = await cardsRes.json();
    if (usersRes.ok) boardUsers = await usersRes.json();
  } catch(e) { showToast('err', e.message); return; }

  BOARD_COLS.forEach(col => {
    const cards = boardCards.filter(c => c.column === col);
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

async function openBoardCardModal(id) {
  const card = boardCards.find(c => c.id === id);
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

function openNewCardModal(col) {
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

function closeBoardCardModal() {
  document.getElementById('board-card-modal').classList.add('hidden');
}

function setBCardColor(c) {
  _bCardColor = c;
  document.querySelectorAll('#bcard-colors .color-pick').forEach(el => {
    el.classList.toggle('active', el.dataset.c === c);
  });
}

function setBCardCol(c) {
  _bCardCol = c;
  document.querySelectorAll('#bcard-col-btns button').forEach(el => {
    el.classList.toggle('active-col', el.dataset.col === c);
  });
}

function populateBCardAssigned(selectedId) {
  const sel = document.getElementById('bcard-assigned');
  sel.innerHTML = '<option value="">— Kimse —</option>' +
    boardUsers.map(u => `<option value="${u.id}" ${u.id===selectedId?'selected':''}>${u.full_name}</option>`).join('');
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

function toggleBCardCL(i) {
  while (_bCardChecklistDone.length < _bCardChecklist.length) _bCardChecklistDone.push(false);
  _bCardChecklistDone[i] = !_bCardChecklistDone[i];
  renderBCardChecklist();
}

function removeBCardCL(i) {
  _bCardChecklist.splice(i, 1);
  _bCardChecklistDone.splice(i, 1);
  renderBCardChecklist();
}

function addBCardChecklistItem() {
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

async function addBCardComment() {
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
async function saveBoardCard() {
  const mode = document.getElementById('bcard-mode').value;
  const title = document.getElementById('bcard-title').value.trim();
  if (!title) { showToast('err', 'Baslik zorunlu'); return; }
  const assigned = document.getElementById('bcard-assigned').value;
  const body = {
    title, description: document.getElementById('bcard-desc').value,
    column: _bCardCol, color: _bCardColor,
    checklist: _bCardChecklist, checklist_done: _bCardChecklistDone,
    assigned_to: assigned ? parseInt(assigned) : null,
    firm: currentUser.firm || '',
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
async function deleteBoardCard() {
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

// PWA — Service Worker kaydı
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
