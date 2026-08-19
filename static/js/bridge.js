// ══════════════════════════════════════════════════════════
//  bridge.js — ESM ↔ inline-handler köprüsü (v5.42, ESM Faz 1)
//
//  CSP `script-src 'self' 'unsafe-inline'` sayesinde inline `onclick="foo()"`
//  çalışır — YETER Kİ `foo` global olsun. ES modülleri fonksiyonu module-scope'ta
//  tutar; bu köprü, inline handler'ların çağırdığı fonksiyonları window'a bağlar.
//  Böylece 183 inline handler'ı bir kerede yeniden yazmadan ESM'e geçilir.
//
//  Faz 5'te inline handler'lar event delegation'a çevrilince bu köprü KALDIRILIR.
//  Ayrıntı: docs/js-esm-migration-plan.md
// ══════════════════════════════════════════════════════════

/** Tek bir fonksiyonu/değeri inline handler'lar için global yapar. */
export function expose(name, fn) {
  window[name] = fn;
}

/** {isim: fn} nesnesindeki tümünü tek çağrıda global yapar. */
export function exposeAll(obj) {
  for (const [name, fn] of Object.entries(obj)) window[name] = fn;
}
