// ══════════════════════════════════════════════════════════
//  main.js — ES-Module giriş noktası (v5.79, ESM Faz 5 TAMAM)
//
//  static/js/ ES-module dönüşümünün TEK entry'si (`<script type="module">`).
//  Tüm frontend artık ESM. Modüller birbirini gerçek `import` ile çağırır;
//  window köprüsü (bridge.js expose/exposeAll) KALDIRILDI. Etkileşimler
//  events.js delegation üzerinden (inline on* handler yok).
//
//  main.js'in tek işi: modül grafiğini değerlendirip (import → her modülün
//  event-delegation register bloğu çalışır) app.js çekirdeğini bootstrap etmek.
// ══════════════════════════════════════════════════════════
import * as appCore from '../app.js'; // app.js ÇEKİRDEK (tüm feature modüllerini import eder)

// app.js zaten tüm feature modüllerini + state/utils/events'i import ettiği için
// import grafiği burada tam değerlendirilmiş olur (registrasyonlar + state kurulu).

// Uygulama BOOTSTRAP'ı: import grafiği tamam → app.js export'ları hazır.
appCore.setDateDisplay('topbar-date-day', 'topbar-date-full');
appCore.loadApp();

// ESM kanalının yüklendiğini işaretle (doğrulama).
window.__esmReady = true;
