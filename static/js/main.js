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

// Köprüyü geçiş boyunca erişilebilir kıl (Faz 3+ modülleri window.expose kullanır).
window.expose = expose;
window.exposeAll = exposeAll;

// ESM kanalının yüklendiğini işaretle (doğrulama + ileride bootstrap guard).
window.__esmReady = true;
