// ══════════════════════════════════════════════════════════
//  main.js — ES-Module giriş noktası (v5.42, ESM Faz 1)
//
//  static/js/ ES-module dönüşümünün TEK entry'si (`<script type="module">`).
//  Şu an klasik script'lerin (app.js, utils.js, audit.js, managed-firms.js)
//  YANINDA yüklenir; sonraki fazlarda o modüller buradan import edilip başlatılır
//  ve klasik <script> etiketleri kaldırılır.
//
//  Faz 1 kapsamı: ESM yükleme kanalını + köprüyü kurmak (CSP/sw.js altında
//  çalıştığını doğrulamak). Henüz davranış taşınmadı — app.js kendini bootstrap
//  etmeye devam ediyor. Plan: docs/js-esm-migration-plan.md
// ══════════════════════════════════════════════════════════
import { expose, exposeAll } from './bridge.js';
import './state.js'; // paylaşılan state'i kurar (window.state) — ESM Faz 2
import * as utils from './utils.js'; // ESM Faz 3a — leaf modülü
import * as audit from './audit.js'; // ESM Faz 3b — Denetim Kayıtları modülü
import * as managedFirms from './managed-firms.js'; // ESM Faz 3c — Yönettiğim Firmalar
import * as notifications from './notifications.js'; // ESM Faz 4a — bildirim çanı + ayarları
import * as board from './board.js'; // ESM Faz 4b — Ortak Alan / Kanban
import * as admin from './admin.js'; // ESM Faz 4c — kullanıcı yönetimi

// Köprüyü geçiş boyunca erişilebilir kıl (Faz 3+ modülleri window.expose kullanır).
window.expose = expose;
window.exposeAll = exposeAll;

// ESM Faz 3a: utils artık gerçek ESM modülü. Klasik app.js/audit.js/managed-firms.js
// ve inline onclick'ler için tüm export'ları window'a bağla (escapeHtml, TODAY,
// catLabel, dlClass/dlText, *Badge, _cssVar/_chartTheme/_centerTextPlugin, ...).
exposeAll(utils);

// ESM Faz 3b: audit.js public fonksiyonları (initAuditPage/setAuditRange/
// resetAuditFilters/exportAuditCsv/loadAuditLog) → window (inline + app.js için).
exposeAll(audit);

// ESM Faz 3c: managed-firms public fonksiyonları (loadManagedFirmsPage/setMfPeriod/
// expandManagedFirms/_mfGotoTasks/_mfGotoAdd) → window. Faz 3 tamamlandı.
exposeAll(managedFirms);

// ESM Faz 4a: bildirim fonksiyonları (buildNotifications/notifClick/toggleNotifDropdown/
// clearAllNotifs/closeNotifDropdown/loadNotificationsPage/save/preview/test) → window.
// Bootstrap'tan ÖNCE: loadApp `setTimeout(buildNotifications)` çağırır.
exposeAll(notifications);

// ESM Faz 4b: board (Kanban) public fonksiyonları → window (inline onclick + app.js).
exposeAll(board);

// ESM Faz 4c: admin (kullanıcı yönetimi) public fonksiyonları → window.
exposeAll(admin);

// ESM kanalının yüklendiğini işaretle (doğrulama + ileride bootstrap guard).
window.__esmReady = true;

// ESM Faz 3c — Uygulama BOOTSTRAP'ı burada (klasik app.js top-level'dan taşındı).
// main.js bu noktada çalıştığında import grafiği tamamen değerlendirilmiştir:
// window.state kurulu + tüm modüller exposeAll edilmiş. Böylece loadApp'ın
// state/utils kullanımı güvenli (eski "state is not defined" yarışı biter).
// setDateDisplay/loadApp klasik app.js'te tanımlı globaller (app.js main.js'ten önce çalışır).
if (typeof window.setDateDisplay === 'function') window.setDateDisplay('topbar-date-day', 'topbar-date-full');
if (typeof window.loadApp === 'function') window.loadApp();
