// ══════════════════════════════════════════════════════════
//  events.js — Event delegation hub (v5.68, ESM Faz 5)
//
//  Inline on* handler'ları (onclick/onchange/oninput) kademeli olarak buraya
//  taşınıyor. Saf ALTYAPI: hiçbir feature modülü import etmez → döngü riski yok.
//  Modüller `onClick/onChange/onInput` import edip kendi aksiyonlarını register
//  eder; delegated listener document seviyesinde tek sefer bağlanır.
//
//  Kullanım:
//    import { onClick } from './events.js';
//    onClick('nav', el => showPage(el.dataset.page));
//  HTML:
//    <div data-click="nav" data-page="dashboard">…</div>
//
//  Faz 5 tamamlanınca window köprüsü (bridge.js expose/exposeAll) kalkacak;
//  o zamana kadar inline handler'lar + delegation birlikte yaşar.
// ══════════════════════════════════════════════════════════
const registry = { click: {}, change: {}, input: {}, enter: {} };

export function onClick(action, fn)  { registry.click[action]  = fn; }
export function onChange(action, fn) { registry.change[action] = fn; }
export function onInput(action, fn)  { registry.input[action]  = fn; }
// Enter tuşu delegation'ı: <input data-enter="action"> — Enter'a basınca fn(el,e)
// çağrılır (preventDefault otomatik: aksiyon varsayılan davranışın yerine geçer).
export function onEnter(action, fn)  { registry.enter[action]  = fn; }

function bind(type, attr) {
  document.addEventListener(type, e => {
    const el = e.target.closest('[' + attr + ']');
    if (!el) return;
    const fn = registry[type][el.getAttribute(attr)];
    if (fn) fn(el, e);
  });
}

bind('click',  'data-click');
bind('change', 'data-change');
bind('input',  'data-input');

// Enter kanalı ayrı: yalnız Enter tuşunda + preventDefault ile
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const el = e.target.closest('[data-enter]');
  if (!el) return;
  const fn = registry.enter[el.getAttribute('data-enter')];
  if (fn) { e.preventDefault(); fn(el, e); }
});
