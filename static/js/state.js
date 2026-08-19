// ══════════════════════════════════════════════════════════
//  state.js — Paylaşılan uygulama state'i (v5.43, ESM Faz 2)
//
//  app.js'in top-level `let` state'i buraya TEK NESNE olarak taşınıyor. Kritik:
//  **property assignment** (`state.tasks = …`) hem klasik app.js (window.state.tasks)
//  hem ESM modülleri (import { state }) tarafında AYNI nesneyi yazar → ESM'in
//  "import edilen binding başka modülden reassign edilemez" sorununu atlar.
//
//  Klasik app.js, `window.state` (aşağıda) üzerinden global `state` olarak erişir;
//  gelecek ESM modülleri `import { state } from './state.js'` kullanır.
//  main.js bu modülü import ederek çalıştırır (window.state kurulur).
//
//  Faz 2 alt-adımları state'i cluster cluster buraya taşır:
//    2a (bu): takvim/scheduler view state (schedView, calYear, calMonth)
//    2b: dashboard/filtre state (currentFilter, dashPage, ...)
//    2c: çekirdek veri state (tasks, USERS, currentUser, ...)
//  Ayrıntı: docs/js-esm-migration-plan.md
// ══════════════════════════════════════════════════════════

export const state = {
  // ── 2a: Takvim / scheduler görünüm state'i ──
  schedView: 'list',
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth(), // 0-indexed

  // ── 2b: Dashboard / filtre state'i ──
  selectedUserId: null,       // v4.2 — director+'in görüntülediği kullanıcı (null = kendim)
  currentFilter: 'all',       // BUGÜNÜN GÖREVLERİ durum filtresi (all/open/done)
  dashPage: 0,                // BUGÜNÜN GÖREVLERİ pagination sayfası
  currentCategoryFilter: '',  // BUGÜNÜN GÖREVLERİ kategori filtresi
};

// Klasik app.js (ve inline handler'lar) için global köprü.
window.state = state;
