// IT Tracker — main client bundle (v5.0)
// templates/app.html içinden çıkarıldı (v5.0 madde #17). Davranış değişmedi.

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
// CAT_LABELS → static/js/utils.js (v5.39)

// ── Uygulama durumu ──
// tasks → state.js (ESM Faz 2c-2, window.state)
// USERS → state.js (ESM Faz 2c-1, window.state)
// currentUser → state.js (ESM Faz 2c-1, window.state)
// selectedUserId → state.js (ESM Faz 2b, window.state)
// firmUsers → state.js (ESM Faz 2c-1, window.state)
let _addReturnPage = 'tasks';  // v5.21 — 'Yeni Görev'e girmeden önceki sayfa; kayıt sonrası buraya dön

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
async function initFirmUserFilter() {
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

async function onFirmUserChange() {
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

async function loadTasks(month, year) {
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
function normalizeTask(t) {
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

function showPage(name, opts = {}) {
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
    if (cur && cur !== 'add') _addReturnPage = cur;
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
function onFileSelected(input) {
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

// ══════════════════════════════════════════════════════════
//  PROJELER SAYFASI
// ══════════════════════════════════════════════════════════
function renderProjectsPage() {
  const firmFilter = document.getElementById('proj-filter-firm')?.value || '';
  let projs = state.tasks.filter(t => t.cat === 'project');
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
      ? `<div class="proj-status-note">📌 ${escapeHtml(t.project_status)}</div>`
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
          <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px;${t.done?'text-decoration:line-through;opacity:.5':''}">${escapeHtml(t.title)}</div>
          <div style="font-size:10px;color:var(--text-muted);display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            ${firmChip(t.firm)}
            <span>${escapeHtml(t.team || '')}</span>
            ${isOverdue ? '<span style="color:var(--danger);font-weight:600">⚠ Gecikti</span>' : ''}
          </div>
          ${statusNote}${clNote}
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;min-width:80px">
          <div style="font-size:10px;color:${dlColor};font-family:'IBM Plex Mono',monospace">${dlStr}</div>
          <div style="display:flex;gap:4px">
            <div class="cb ${t.done?'done':''}" role="checkbox" aria-checked="${t.done?'true':'false'}" aria-label="${t.done?'Geri al':'Tamamla'}: ${escapeHtml(t.title)}${_periodCompletionLabel(t) ? ' — ' + _periodCompletionLabel(t) : ''}" tabindex="0" onclick="apiToggleTask(${t.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();apiToggleTask(${t.id})}" style="width:16px;height:16px;border-radius:4px"></div>
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
  t.innerHTML = `<span>${type==='ok'?'✓':'✗'}</span> ${escapeHtml(msg)}`;
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

// ══════════════════════════════════════════════════════════
//  YEDEKLER SAYFASI
// ══════════════════════════════════════════════════════════
function getBackupTasks() {
  return state.tasks.filter(t => t.cat === 'backup' && t.backup);
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
        <div style="font-size:13px;font-weight:500">${escapeHtml(b.task_title || '—')}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:4px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          ${firmChip(b.firm||'')}
          <span>· ${b.team||''}</span>
          <span>· ${uploadDate}</span>
        </div>
        <div style="margin-top:6px;display:flex;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--border2);border-radius:6px;padding:6px 10px;width:fit-content">
          <span style="font-size:18px">💾</span>
          <div>
            <div style="font-size:11px;font-weight:600;color:var(--gold);font-family:'IBM Plex Mono',monospace">${escapeHtml(b.filename)}</div>
            <div style="font-size:9px;color:var(--text-muted)">${sizeStr}${b.device?' · '+escapeHtml(b.device):''}</div>
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
//  PORTAL OTOMATİK ATAMA → static/js/settings.js (ESM Faz 4f-4)
// ══════════════════════════════════════════════════════════

// TEAMS BİLDİRİMLERİ → static/js/settings.js (ESM Faz 4f-4)

// ══════════════════════════════════════════════════════════
//  CASE ARŞİVİ (v5.27) — ay-bağımsız destek talebi arama
// ══════════════════════════════════════════════════════════
let _archPage = 1, _archT = null;

function loadArchivePage() {
  // Firma dropdown'unu doldur (bir kez)
  const fs = document.getElementById('arch-firm');
  if (fs && fs.options.length <= 1) {
    Object.entries(FIRMS).forEach(([slug, f]) => {
      const o = document.createElement('option'); o.value = slug; o.textContent = f.label || slug;
      fs.appendChild(o);
    });
  }
  _archPage = 1;
  archSearch();
}

function archSearchDebounced() { clearTimeout(_archT); _archT = setTimeout(() => { _archPage = 1; archSearch(); }, 300); }

async function archSearch() {
  const box = document.getElementById('arch-list');
  const pager = document.getElementById('arch-pager');
  if (!box) return;
  const params = new URLSearchParams({ page: String(_archPage) });
  const q = document.getElementById('arch-q').value.trim();
  const firm = document.getElementById('arch-firm').value;
  const status = document.getElementById('arch-status').value;
  if (q) params.set('q', q);
  if (firm) params.set('firm', firm);
  if (status && status !== 'all') params.set('status', status);
  try {
    const r = await fetch('/api/archive?' + params.toString());
    if (!r.ok) throw new Error();
    const d = await r.json();
    if (!d.items.length) {
      box.innerHTML = '<div style="padding:26px;text-align:center;color:var(--text-muted);font-size:12.5px">Eşleşen talep yok.</div>';
      pager.innerHTML = '';
      return;
    }
    box.innerHTML = d.items.map(i => {
      const st = i.status === 'resolved'
        ? '<span class="prio-badge low" style="background:rgba(40,180,135,.14);color:var(--green);border-color:rgba(40,180,135,.4)">✓ Çözüldü</span>'
        : '<span class="prio-badge med">Açık</span>';
      const owner = i.owner ? escapeHtml(i.owner) : '<span style="color:var(--text-muted)">🫧 havuz</span>';
      const dt = i.created_at ? formatDateTR(i.created_at.slice(0, 10)) : '';
      const code = i.case_code ? `<span class="prio-badge low" style="background:rgba(0,229,192,.12);color:var(--accent);border-color:rgba(0,229,192,.3)">🌐 ${escapeHtml(i.case_code)}</span>` : '';
      return `<div class="task-item" style="align-items:center;cursor:pointer" onclick="openEditTask(${i.id})">
        <div style="font-size:15px">🗄️</div>
        <div>
          <div class="task-title">${escapeHtml(i.title)}</div>
          <div class="task-meta">${code} ${st} ${firmChip(i.firm)}
            <span style="color:var(--text-muted);font-size:10px">· ${escapeHtml(i.reporter_name || '')} ${i.reporter_email ? '&lt;' + escapeHtml(i.reporter_email) + '&gt;' : ''} · ${dt} · Atanan: ${owner}</span></div>
        </div>
        <div></div><div></div>
      </div>`;
    }).join('');
    pager.innerHTML = d.pages > 1 ? `
      <button class="btn btn-outline btn-sm" ${d.page <= 1 ? 'disabled' : ''} onclick="_archPage--;archSearch()">‹ Önceki</button>
      <span>${d.page} / ${d.pages} · ${d.total} kayıt</span>
      <button class="btn btn-outline btn-sm" ${d.page >= d.pages ? 'disabled' : ''} onclick="_archPage++;archSearch()">Sonraki ›</button>` : `<span>${d.total} kayıt</span>`;
  } catch (e) {
    box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--danger);font-size:12px">Arşiv yüklenemedi.</div>';
  }
}

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

function saveTeams() { showToast('ok', 'Ekip değişiklikleri otomatik kaydedildi.'); }

// ══════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════
//  ORTAK ALAN (BOARD/Kanban) → static/js/board.js (ESM Faz 4b)
// ══════════════════════════════════════════════════════════

// PWA — Service Worker kaydı
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
