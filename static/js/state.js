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

  // ── 2c-1: Çekirdek veri state'i (collision'sız cluster) ──
  currentUser: {},   // /api/me — audit.js + managed-firms.js de okur
  USERS: [],         // /api/admin/users
  firmUsers: [],     // v4.2 — kapsamdaki kullanıcılar; audit.js de okur
  INVITATIONS: [],   // /api/admin/invitations
  boardCards: [],    // /api/board/cards
  boardUsers: [],    // board kullanıcı listesi

  // ── 2c-2: En yaygın veri (string-collision'lı → lexer ile taşındı) ──
  tasks: [],         // /api/tasks — en yaygın (50 kullanım)
  notifications: [], // /api/notifications/preview

  // ── 4d-3: Anlık Görevler (full list) filtre state'i (app.js showPage + tasks.js) ──
  ftFirm: '',
  ftCat: '',
  ftSearch: '',

  // ── 4f-son: 'Yeni Görev'e girmeden önceki sayfa (app.js showPage yazar, tasks.js addTask okur) ──
  addReturnPage: 'tasks',
};
// ESM Faz 5 TAMAM: window.state köprüsü kaldırıldı — tüm modüller `import { state }`.
