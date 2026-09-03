// IT Tracker — main client bundle (v5.0)
// templates/app.html içinden çıkarıldı (v5.0 madde #17). Davranış değişmedi.
import { state } from './js/state.js';
import { TODAY, _appVersionSuffix, escapeHtml, CAT_LABELS, _centerTextPlugin, _chartTheme, _cssVar, _periodCompletionBadge, _periodCompletionLabel, _routineOverdueLabel } from './js/utils.js';
import { loadAndRenderUsers } from './js/admin.js';
import { loadArchivePage } from './js/archive.js';
import { initAuditPage, loadAuditLog } from './js/audit.js';
import { renderBackupList } from './js/backup.js';
import { renderBoard } from './js/board.js';
import { renderDashUpcoming, renderDashboard, updateSupportNavBadge } from './js/dashboard.js';
import { loadKb } from './js/kb.js';
import { loadManagedFirmsPage } from './js/managed-firms.js';
import { buildNotifications, closeNotifDropdown, loadNotificationsPage } from './js/notifications.js';
import { loadPoolPage, updatePoolBadge } from './js/pool.js';
import { renderProjectsPage } from './js/projects.js';
import { initReportPage } from './js/report.js';
import { renderScheduledPage } from './js/scheduled.js';
import { loadAutoAssign, loadSettingsFromServer, loadTeamsSettings } from './js/settings.js';
import { firmChip, renderFullList, taskRow, taskTiming } from './js/tasks.js';
import { onClick, onChange, onEnter } from './js/events.js'; // ESM Faz 5 — event delegation

// ESM Faz 5 — Sidebar/genel navigasyon: <... data-click="nav" data-page="X">
onClick('nav', el => showPage(el.dataset.page));
// ESM Faz 5 — Sidebar aç/kapa (mobil): data-click="toggleSidebar" [data-close]
onClick('toggleSidebar', el => toggleSidebar(el.dataset.close === 'true'));
// ESM Faz 5 — auth + ekip/backup + genel yardımcı aksiyonlar
onClick('o365Login',     () => o365Login());
onClick('manualLogin',   () => manualLogin());
onClick('addTeam',       el => addTeam(el.dataset.firm));
onClick('addBackupType', () => addBackupType());
onClick('saveTeams',     () => saveTeams());
// Genel: bilgilendirme toast'u (data-type varsayılan 'ok', data-msg metin)
onClick('toast',    el => showToast(el.dataset.type || 'ok', el.dataset.msg || ''));
// Genel: bir modalı gizle (data-modal = element id)
onClick('hideModal', el => { const m = document.getElementById(el.dataset.modal); if (m) m.classList.add('hidden'); });
// Genel: sayfaya git + bir modalı gizle (data-page + data-modal)
onClick('navHideModal', el => { showPage(el.dataset.page); const m = document.getElementById(el.dataset.modal); if (m) m.classList.add('hidden'); });
// Yeni Görev sayfasına git + kategori ön-seç (data-cat) → onCatChange
onClick('newTaskCat', el => { showPage('add'); const c = document.getElementById('new-cat'); if (c) { c.value = el.dataset.cat; onCatChange(); } });
// ESM Faz 5 — onchange (data-change) + Enter (data-enter) aksiyonları
onChange('onCatChange',      () => onCatChange());
onChange('onFileSelected',   el => onFileSelected(el));
onChange('onFirmUserChange', () => onFirmUserChange());
onChange('updateTeamOptions', () => updateTeamOptions());
onEnter('manualLogin',       () => manualLogin());
// generated-string (ekip / backup-type pill "×" ile sil)
onClick('removeTeam',       el => removeTeam(el.dataset.firm, el.dataset.team, +el.dataset.tid));
onClick('removeBackupType', el => removeBackupType(el.dataset.type));


// ══════════════════════════════════════════════════════════
//  KULLANICI FİRMA BAZLI TEMA (v3)
// ══════════════════════════════════════════════════════════
// Sürüm TEK KAYNAK: Flask APP_VERSION (VERSION dosyası) app.html'de logo-sub-text
// data-app-version'a enjekte edilir; buradan okunur. Eskiden 3 string'de elle 'v5.0'
// yazılıydı ve sürüm bump'larında güncellenmiyordu (prod'da v5.11 sekmesi + v5.0 logo).
// _appVersionSuffix → static/js/utils.js (v5.39)

function applyThemeForFirm(firmSlug) {
  const f = (firmSlug || '').toLowerCase();
  const vs = _appVersionSuffix();
  let theme = null;
  let logoText = 'İnventist & Assos' + vs;

  if (f.includes('assos')) {
    theme = 'assos';
    logoText = 'Assos Pharma' + vs;
  } else if (f.includes('inventist')) {
    theme = 'inventist';
    logoText = 'İnventist' + vs;
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
  const showBoard = state.currentUser.can_access_board || state.currentUser.permission_level === 'super_admin';
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
  const level = (state.currentUser.permission_level || 'junior');
  const smtpCard = document.getElementById('settings-card-smtp');
  const backupCard = document.getElementById('settings-card-backup');
  if (smtpCard) smtpCard.style.display = (level === 'super_admin') ? '' : 'none';
  if (backupCard) backupCard.style.display = (level === 'super_admin') ? '' : 'none';
  // v5.32 — Teams bildirimleri kartı: yalnız super_admin
  const teamsCard = document.getElementById('settings-card-teams');
  if (teamsCard) teamsCard.style.display = (level === 'super_admin') ? '' : 'none';
  // v5.19 — Otomatik atama kartı: director+ kural yönetir; master toggle super_admin.
  const aaCard = document.getElementById('settings-card-autoassign');
  const isDirPlus = (level === 'super_admin' || level === 'it_director');
  if (aaCard) aaCard.style.display = isDirPlus ? '' : 'none';
  const aaToggle = document.getElementById('aa-toggle');
  const aaHint = document.getElementById('aa-toggle-hint');
  if (aaToggle) {
    aaToggle.disabled = (level !== 'super_admin');
    if (aaHint) aaHint.textContent = (level !== 'super_admin')
      ? 'Ana anahtarı yalnızca süper yönetici açıp kapatabilir; kuralları düzenleyebilirsiniz.' : '';
  }
}

function applyJuniorTaskRestrictions() {
  const level = (state.currentUser.permission_level || 'junior');
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
    if (state.currentUser.firm) {
      firmSel.value = state.currentUser.firm;
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
const JUNIOR_ALLOWED_PAGES = ['dashboard', 'tasks', 'add', 'board', 'pool', 'archive'];  // v5.27 — arşiv (kapsam sunucuda)

// ══════════════════════════════════════════════════════════
//  SABİT VERİLER
// ══════════════════════════════════════════════════════════
// FIRMS objesi — başlangıçta sabit, loadFirmsFromDB() ile DB'den güncellenir
export const FIRMS = {
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
// CAT_LABELS → static/js/utils.js (v5.39)

// ── Uygulama durumu ──
// tasks → state.js (ESM Faz 2c-2, window.state)
// USERS → state.js (ESM Faz 2c-1, window.state)
// currentUser → state.js (ESM Faz 2c-1, window.state)
// selectedUserId → state.js (ESM Faz 2b, window.state)
// firmUsers → state.js (ESM Faz 2c-1, window.state)

// ══════════════════════════════════════════════════════════
//  AUTH
// ══════════════════════════════════════════════════════════
export function showLoginScreen() { document.getElementById('login-screen').style.display = 'flex'; }
export function o365Login() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('sb-o365').style.display = 'inline-flex';
  showToast('ok','Microsoft 365 hesabı başarıyla bağlandı');
}
export function manualLogin() {
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
export async function loadApp() {
  try {
    const me = await fetch('/api/me').then(r => r.json());
    state.currentUser = me;
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
export async function initFirmUserFilter() {
  const level = state.currentUser.permission_level || 'junior';
  if (level !== 'super_admin' && level !== 'it_director') return;
  try {
    const res = await fetch('/api/firm/users');
    if (!res.ok) return;
    state.firmUsers = await res.json();
    const sel = document.getElementById('firm-user-filter');
    const wrap = document.getElementById('firm-user-filter-wrap');
    if (!sel || !wrap) return;
    // Options: kendim + diğer kullanıcılar (kendisini ayrı kategori "kendim" olarak sunuyoruz)
    const others = state.firmUsers.filter(u => u.id !== state.currentUser.id);
    sel.innerHTML = '<option value="">— Kendim —</option>' +
      others.map(u => `<option value="${u.id}">${escapeHtml(u.full_name)}${u.firm ? ' · '+escapeHtml(u.firm) : ''}</option>`).join('');
    wrap.style.display = others.length ? 'flex' : 'none';
    refreshAssignModeUI();
  } catch(e) { console.warn('firm users yüklenemedi', e); }
}

export async function onFirmUserChange() {
  const val = document.getElementById('firm-user-filter').value;
  state.selectedUserId = val ? parseInt(val) : null;
  refreshAssignModeUI();
  await loadTasks();
  renderDashboard();
  // Hangi sayfadaysak yeniden render et
  const activePage = document.querySelector('.page-section.active');
  if (activePage && activePage.id === 'page-tasks') renderFullList(state.tasks.filter(t => t.cat === 'task' || t.cat === 'backup'));
}

// v5.0 — Atama modu (director+ başka kullanıcıyı görüntülüyor) açıkken kategori default'u "support"
function applyAssignModeDefaults() {
  const isDirectorUp = state.currentUser.permission_level === 'super_admin' || state.currentUser.permission_level === 'it_director';
  const inAssignMode = isDirectorUp && state.selectedUserId && state.selectedUserId !== state.currentUser.id;
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
  const isDirectorUp = state.currentUser.permission_level === 'super_admin' || state.currentUser.permission_level === 'it_director';
  const banner = document.getElementById('assign-mode-banner');
  const target = document.getElementById('assign-target-name');
  const mnGroup = document.getElementById('new-manager-note-group');
  const assignTo = (isDirectorUp && state.selectedUserId && state.selectedUserId !== state.currentUser.id) ? state.selectedUserId : null;
  if (banner) {
    if (assignTo) {
      const u = state.firmUsers.find(u => u.id === assignTo);
      if (target) target.textContent = u ? u.full_name : '—';
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  }
  // IT Müdürü notu alanı: her zaman director+'a görünür
  if (mnGroup) mnGroup.classList.toggle('hidden', !isDirectorUp);
}

export async function loadTasks(month, year) {
  try {
    const now = new Date();
    const m = month || now.getMonth() + 1;
    const y = year  || now.getFullYear();
    // v4.2 — director+ başka kullanıcıyı görüntülüyorsa user_id eklenir
    const userParam = state.selectedUserId ? '&user_id=' + state.selectedUserId : '';
    const res = await fetch('/api/tasks?month=' + m + '&year=' + y + userParam);
    const data = await res.json();
    // API alanlarını frontend formatına normalize et
    state.tasks = data.map(normalizeTask);
  } catch(e) { console.error('Görevler yüklenemedi:', e); state.tasks = []; }
  // v5.2 — destek talebi sayısını sidebar nav badge'ine yansıt
  try { updateSupportNavBadge(); } catch(_) {}
  try { updatePoolBadge(); } catch(_) {}
}

// v4.2 — başka kullanıcının görevlerine yazma izni yok (yalnızca görüntüleme)
function isReadOnlyScope() { return !!state.selectedUserId && state.selectedUserId !== state.currentUser.id; }

// v4.3 — HTML escape (kırmızı not ve benzeri güvenli gösterim için)
// escapeHtml / _periodCompletionLabel / _periodCompletionBadge → static/js/utils.js (v5.38)

// ══════════════════════════════════════════════════════════
//  v4.4 — DENETİM KAYITLARI (audit) → static/js/audit.js (v5.40)
//  AUDIT_ACTION_LABELS/COLORS + initAuditPage/setAuditRange/resetAuditFilters/
//  _auditFilterParams/exportAuditCsv/loadAuditLog taşındı.
// ══════════════════════════════════════════════════════════

// API to_dict() → frontend format dönüşümü
export function normalizeTask(t) {
  return {
    id:       t.id,
    user_id:  t.user_id,       // v5.18 — havuz (null = atanmamış)
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
    // v5.15 — portal kaynaklı destek talepleri
    source:              t.source || 'manual',
    case_code:           t.case_code || null,
    reporter_email:      t.reporter_email || null,
    reporter_name:       t.reporter_name || null,
    reporter_anydesk:    t.reporter_anydesk || null,
    it_unread:           t.it_unread || false,   // v5.22 — yeni case / yeni yanıt rozeti
    // v5.1 — Rutin kanonik sinyaller (deadline/next_due donmuş alanları yerine)
    is_overdue:          t.is_overdue || false,
    overdue_periods:     t.overdue_periods || 0,
    current_period_label: t.current_period_label || null,
    next_period_date:    t.next_period_date || null,
  };
}

// v5.1 — Rutin görev gecikme rozeti metni (periyot sayısı bazlı).
// Diğer kategoriler deadline kullanmaya devam eder; bu yalnızca rutin içindir.
// _routineOverdueLabel → static/js/utils.js (v5.39)

// ══════════════════════════════════════════════════════════
//  NAVIGATION
// ══════════════════════════════════════════════════════════
// v5.0 BUG-2 — Mobil sidebar hamburger toggle.
// Desktop/tablet'te etkisi yok (>720px CSS sidebar her zaman görünür).
// Mobil'de .open class'ı sidebar'ı slide-in yapar, backdrop ile kapatılabilir.
export function toggleSidebar(forceClose) {
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

export function showPage(name, opts = {}) {
  // v5.4 — opts: { cat, firm, statusKind, activeNav }
  //   cat        → tasks sayfasında kategori filtresi ('support' vb.)
  //   firm       → tasks sayfasında firma filtresi (drill-down)
  //   statusKind → KPI jump (overdue/open/done/all)
  //   activeNav  → hangi sidebar item'ı aktif görünsün (default: name)
  // Tüm filtreler loadTasks().then içinde uygulanır → eski setTimeout race'i kalktı.
  // v5.0 BUG-2 — mobile'da menü item'a tıklayınca sidebar otomatik kapansın
  toggleSidebar(true);
  // Yetki guard: Junior sadece izinli sayfalara erişebilir
  const level = (state.currentUser.permission_level || 'junior');
  if (level === 'junior' && !JUNIOR_ALLOWED_PAGES.includes(name)) return;
  // Board guard: can_access_board veya super_admin
  if (name === 'board' && !state.currentUser.can_access_board && level !== 'super_admin') return;
  // v4.4 — Denetim sayfası yalnızca director+
  if (name === 'audit' && !(level === 'super_admin' || level === 'it_director')) return;
  // v5.24 — Bilgi Bankası yönetimi yalnızca director+
  if (name === 'kb' && !(level === 'super_admin' || level === 'it_director')) return;

  // v5.21 — 'Yeni Görev' sayfasına geçerken, GELDİĞİMİZ sayfayı hatırla ki kayıt
  // sonrası kullanıcı hep 'Anlık Görevler'e değil, açtığı menüye geri dönsün.
  if (name === 'add') {
    const curEl = document.querySelector('.page-section.active');
    const cur = curEl ? curEl.id.replace('page-', '') : '';
    if (cur && cur !== 'add') state.addReturnPage = cur;
  }

  document.querySelectorAll('.page-section').forEach(p => p.classList.remove('active'));
  document.getElementById('page-'+name)?.classList.add('active');
  // v5.0 BUG-3 fix: nav active highlight için onclick içinde tam showPage('name')
  // call'unu regex ile match et. Eski `.includes("'"+name+"'")` yöntemi başka
  // onclick'lerde aynı string parçasını içeren item'ları da yanlışlıkla aktif
  // bırakabiliyordu (örn. settings butonu içinde 'audit' modal kapama mantığı varsa).
  // v5.4 — Nav active: data-nav attribute öncelikli (Destek Talepleri gibi aynı
  // sayfaya giden ama ayrı item'lar için). Yoksa eski onclick-regex geri uyumlu.
  const activeNav = opts.activeNav || name;
  document.querySelectorAll('.nav-item').forEach(n => {
    let isActive;
    if (n.dataset.nav) {
      isActive = n.dataset.nav === activeNav;
    } else {
      const m = (n.getAttribute('onclick') || '').match(/showPage\(['"]([^'"]+)['"]/);
      isActive = !!(m && m[1] === activeNav);
    }
    n.classList.toggle('active', isActive);
    // a11y — ekran okuyucular için aktif sayfa işareti (CSS class'a ek)
    if (isActive) n.setAttribute('aria-current', 'page');
    else n.removeAttribute('aria-current');
  });
  if (name==='dashboard') renderDashboard();
  if (name==='tasks') {
    // v5.4 — Başlık moda göre (Destek Talepleri vs Anlık Görevler)
    const titleEl = document.getElementById('tasks-page-title');
    const subEl = document.getElementById('tasks-page-sub');
    if (titleEl && subEl) {
      if (opts.cat === 'support') {
        titleEl.innerHTML = 'Destek <span>Talepleri</span>';
        subEl.textContent = 'SLA takipli destek talepleri — öncelik ve süre yönetimi';
      } else {
        titleEl.innerHTML = 'Anlık <span>Görevler</span>';
        subEl.textContent = 'Tek seferlik işler — destek, kurulum, ayar, bakım';
      }
    }
    // v5.6 — Sağ üst "ekle" butonu da moda göre (bug: Destek modunda "Anlık Görev Ekle" diyordu)
    const addBtn = document.getElementById('tasks-add-btn');
    if (addBtn) {
      addBtn.dataset.cat = (opts.cat === 'support') ? 'support' : 'task';
      addBtn.textContent = (opts.cat === 'support') ? '＋ Destek Talebi Ekle' : '＋ Anlık Görev Ekle';
    }
    loadTasks().then(() => {
      const filterEl = document.getElementById('tasks-cat-filter');
      if (opts.cat === 'support') {
        state.ftCat = 'support';
        if (filterEl) filterEl.value = 'support';
        renderFullList(state.tasks.filter(t => t.cat === 'support'));
      } else if (opts.firm !== undefined) {
        // Firma drill-down — kategori bağımsız
        state.ftCat = '';
        if (filterEl) filterEl.value = '';
        renderFullList(state.tasks.filter(t => (t.firm || '') === opts.firm));
      } else if (opts.statusKind) {
        // KPI jump — durum filtresi, kategori bağımsız
        state.ftCat = '';
        if (filterEl) filterEl.value = '';
        const k = opts.statusKind;
        let list = state.tasks;
        if (k === 'overdue') list = state.tasks.filter(t => !t.done && t.deadline && t.deadline < TODAY);
        else if (k === 'open') list = state.tasks.filter(t => !t.done);
        else if (k === 'done') list = state.tasks.filter(t => t.done);
        renderFullList(list);
      } else {
        // Varsayılan: Anlık Görevler (task + backup)
        state.ftCat = 'task';
        if (filterEl) filterEl.value = 'task';
        renderFullList(state.tasks.filter(t => t.cat === 'task' || t.cat === 'backup'));
      }
    });
  }
  if (name==='projects')  { loadTasks().then(() => renderProjectsPage()); }
  if (name==='add')       { applyJuniorTaskRestrictions(); applyAssignModeDefaults(); onCatChange(); refreshAssignModeUI(); }
  if (name==='audit')     { initAuditPage(); }
  if (name==='managed-firms') { loadManagedFirmsPage(); }
  if (name==='backups')   renderBackupList();
  if (name==='admin')     loadAndRenderUsers();
  if (name==='settings')  { loadFirmsFromDB().then(() => renderSettingsTeams()); loadSettingsFromServer(); applySettingsPermissions(); loadAutoAssign(); loadTeamsSettings(); }
  if (name==='kb')        loadKb();
  if (name==='archive')   loadArchivePage();
  if (name==='notifications') loadNotificationsPage();
  if (name==='scheduled') { loadTasks().then(() => renderScheduledPage()); }
  if (name==='report')    initReportPage();
  if (name==='board')     renderBoard();
  if (name==='pool')      loadPoolPage();
}

// ══════════════════════════════════════════════════════════
//  DASHBOARD RENDER + KPI/trend + drill-down → static/js/dashboard.js (ESM Faz 4e-2c)
//  renderDashboard/loadKpiTrends/kpiJump/showTasksWith*/addTaskFromTasksView/updateSupportNavBadge
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
//  DESTEK HAVUZU → static/js/pool.js (ESM Faz 4f-5)
// ══════════════════════════════════════════════════════════

// v4.7 — KATEGORİ DAĞILIMI: gerçek verilerden pie chart
// ── v5.33 — Chart.js grafik altyapısı (CSS değişkenlerinden tema-duyarlı renk) ──
// _cssVar / _chartTheme / _centerTextPlugin → static/js/utils.js (v5.38)
// CHARTS (kategori pie / firma bar / aktivite / haftalık) → static/js/dashboard.js (ESM Faz 4e-2a)

// Yönetilen Firmalar Şeridi (loadDirectorFirmsStrip/onFirmStripClick) → static/js/dashboard.js (ESM Faz 4e-2c)

// ══════════════════════════════════════════════════════════
//  v5.0 — YÖNETTİĞİM FİRMALAR SAYFASI → static/js/managed-firms.js (v5.41)
//  _mfPeriod/_mfData/_mfShowAll + loadManagedFirmsPage/renderManagedFirms/
//  expandManagedFirms/setMfPeriod/_mfCardHtml/_mfTrendHtml/_mfCatBarsHtml/
//  _mfOverdueHtml/_mfUsersHtml/_mfGotoTasks/_mfGotoAdd taşındı.
// ══════════════════════════════════════════════════════════

// SLA KPI kartları (loadSlaKpi) → static/js/dashboard.js (ESM Faz 4e-2c)

// ══════════════════════════════════════════════════════════
//  CASCADING FIRM → TEAM
// ══════════════════════════════════════════════════════════
export function updateTeamOptions() {
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
export function onCatChange() {
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

  // v5.37 — Destek talebinde manuel bitiş tarihi yok; SLA notu göster
  document.getElementById('deadline-field')?.classList.toggle('hidden', isSupport);
  document.getElementById('sla-deadline-note')?.classList.toggle('hidden', !isSupport);

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
    // v5.37 — Destek: manuel son tarih yok, SLA notu göster
    document.getElementById('edit-deadline-field')?.classList.toggle('hidden', cat === 'support');
    document.getElementById('edit-sla-deadline-note')?.classList.toggle('hidden', cat !== 'support');
  }
});
function toggleBackupSection() { onCatChange(); }
function triggerUpload() { /* input[type=file] zaten tüm alanı kaplıyor */ }
export function onFileSelected(input) {
  const file = input.files[0]; if (!file) return;
  const el = document.getElementById('upload-filename');
  el.textContent = '💾 ' + file.name; el.style.display = 'block';
  document.getElementById('upload-zone').classList.add('has-file');
}

// ══════════════════════════════════════════════════════════
//  TASK HELPERS → static/js/tasks.js (ESM Faz 4e-1)
//  taskTiming / firmChip / taskRow (paylaşımlı satır-render, KANONİK tek kaynak)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
//  DASHBOARD TASK LIST + renderDashUpcoming → static/js/dashboard.js (ESM Faz 4e-2b)
// ══════════════════════════════════════════════════════════

// PROJELER SAYFASI → static/js/projects.js (ESM Faz 4f-6)

// ══════════════════════════════════════════════════════════
//  FULL TASK LIST → static/js/tasks.js (ESM Faz 4d-3a)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
//  GÖREV EKLE + TOGGLE → static/js/tasks.js (ESM Faz 4d-1)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
//  CHARTS (aktivite bar / haftalık akış) → static/js/dashboard.js (ESM Faz 4e-2a)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════
//  ADMIN — KULLANICI TABLOSU → static/js/admin.js (ESM Faz 4c)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
//  SETTINGS — EKİP YÖNETİMİ (local FIRMS objesi)
// ══════════════════════════════════════════════════════════
function renderSettingsTeams() {
  ['inventist','assos'].forEach(firm => {
    const el = document.getElementById(`${firm}-teams-display`);
    if (!el) return;
    el.innerHTML = FIRMS[firm].teams.map(t => {
      const tid = FIRMS[firm].teamIds[t] || '';
      return `<span class="pill-tag" data-click="removeTeam" data-firm="${firm}" data-team="${t}" data-tid="${tid}">${t} <span class="rm">×</span></span>`;
    }).join('');
  });
  renderBackupTypes();
}
export async function addTeam(firm) {
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
export async function removeTeam(firm, team, tid) {
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
  document.getElementById('backup-types-display').innerHTML = BACKUP_TYPES.map(t => `<span class="pill-tag" data-click="removeBackupType" data-type="${t}">${t} <span class="rm">×</span></span>`).join('');
}
export function addBackupType() {
  const inp = document.getElementById('backup-new-type'); let val = inp.value.trim(); if (!val) return;
  if (!val.startsWith('.')) val = '.' + val;
  if (!BACKUP_TYPES.includes(val)) { BACKUP_TYPES.push(val); showToast('ok',`${val} eklendi`); }
  inp.value = ''; renderBackupTypes();
}
export function removeBackupType(t) { const idx = BACKUP_TYPES.indexOf(t); if (idx > -1) BACKUP_TYPES.splice(idx,1); renderBackupTypes(); }

// ══════════════════════════════════════════════════════════
//  TOAST
// ══════════════════════════════════════════════════════════
export function showToast(type, msg) {
  const wrap = document.getElementById('toast-wrap');
  const t = document.createElement('div'); t.className = `toast ${type}`;
  t.innerHTML = `<span>${type==='ok'?'✓':'✗'}</span> ${escapeHtml(msg)}`;
  wrap.appendChild(t); setTimeout(() => t.remove(), 3500);
}

// ══════════════════════════════════════════════════════════
//  TARİH YARDIMCILARI
// ══════════════════════════════════════════════════════════
export function formatDateTR(dateStr) {
  if (!dateStr) return '—';
  const [y, m, d] = dateStr.split('-');
  const aylar = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  return `${parseInt(d)} ${aylar[parseInt(m)-1]} ${y}`;
}
export function setDateDisplay(dayId, fullId) {
  const now = new Date();
  const gunler = ['Pazar','Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi'];
  const aylar  = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
  const de = document.getElementById(dayId); const fe = document.getElementById(fullId);
  if (de) de.textContent = now.getDate();
  if (fe) fe.textContent = `${aylar[now.getMonth()]} ${now.getFullYear()} · ${gunler[now.getDay()]}`;
}

// ══════════════════════════════════════════════════════════
//  BİLDİRİM SİSTEMİ → static/js/notifications.js (ESM Faz 4a)
//  (çan/dropdown + click-outside listener; keydown/ESC app.js'te kaldı)
// ══════════════════════════════════════════════════════════

// a11y — ESC açık modalı (ve bildirim dropdown'unu) kapatır.
// Tüm modallar .modal-overlay + .hidden class'ı ile yönetiliyor; kapama
// fonksiyonlarının hepsi hidden eklemekten ibaret → generic kapatma güvenli.
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const openModal = document.querySelector('.modal-overlay:not(.hidden)');
  if (openModal) { openModal.classList.add('hidden'); return; }
  closeNotifDropdown();
});

// ══════════════════════════════════════════════════════════
//  ZAMANLANMIŞ GÖREVLER + TAKVİM → static/js/scheduled.js (ESM Faz 4f-2)
// ══════════════════════════════════════════════════════════

// renderDashUpcoming → static/js/dashboard.js (ESM Faz 4e-2b)

// ══════════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════════
// TODAY → static/js/utils.js (v5.39)
// v5.47 — new-start başlangıç değeri yalnız DOMContentLoaded'da (ESM: TODAY main.js
// expose'undan sonra hazır; eski top-level senkron satır kaldırıldı).
document.addEventListener('DOMContentLoaded', () => { const s = document.getElementById('new-start'); if (s) s.value = TODAY; });

// v5.49 (ESM Faz 3c) — Bootstrap (setDateDisplay + loadApp) main.js'e TAŞINDI.
// Neden: loadApp `await fetch('/api/me')` sonrası state/utils kullanır; app.js
// top-level'dan çağrılınca, main.js'in (büyüyen) import grafiği window.state'i
// kurmadan önce /api/me yarışı kazanıp "state is not defined" veriyordu. main.js
// tüm import+exposeAll bittikten SONRA bootstrap eder → yarış yok.

// ══════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════
//  EDIT TASK MODAL + CASE MESAJ + BACKUP → static/js/tasks.js (ESM Faz 4d-2)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════
//  EDIT USER MODAL → static/js/admin.js (ESM Faz 4c)
// ══════════════════════════════════════════════════════════

// YEDEKLER SAYFASI → static/js/backup.js (ESM Faz 4f-6)



// ══════════════════════════════════════════════════════════
//  PORTAL OTOMATİK ATAMA → static/js/settings.js (ESM Faz 4f-4)
// ══════════════════════════════════════════════════════════

// TEAMS BİLDİRİMLERİ → static/js/settings.js (ESM Faz 4f-4)

// CASE ARŞİVİ → static/js/archive.js (ESM Faz 4f-6)

// ══════════════════════════════════════════════════════════
//  BİLGİ BANKASI → static/js/kb.js (ESM Faz 4f-3)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════

// Ayarlar sayfası açılınca sunucudan gerçek verileri yükle
// KULLANICI + SMTP AYARLARI → static/js/settings.js (ESM Faz 4f-4)

// ══════════════════════════════════════════════════════════
//  BİLDİRİM AYARLARI → static/js/notifications.js (ESM Faz 4a)
// ══════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════
//  RAPOR SAYFASI → static/js/report.js (ESM Faz 4f-1)
// ══════════════════════════════════════════════════════════

// CHECKLİST FONKSİYONLARI → static/js/tasks.js (ESM Faz 4d-3b)

export function saveTeams() { showToast('ok', 'Ekip değişiklikleri otomatik kaydedildi.'); }

// ══════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════
//  ORTAK ALAN (BOARD/Kanban) → static/js/board.js (ESM Faz 4b)
// ══════════════════════════════════════════════════════════

// PWA — Service Worker kaydı
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
