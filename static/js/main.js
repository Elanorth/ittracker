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

// ESM kanalının yüklendiğini işaretle (doğrulama + ileride bootstrap guard).
window.__esmReady = true;
