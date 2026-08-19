# Frontend JS — ES-Module Dönüşüm Planı

> Durum: **PLAN** (henüz uygulanmadı). Hazırlık: 2026-08-18, develop v5.41.
> Bağlam: app.js modülerleştirmesi v5.38–v5.41 arası "klasik script + global namespace"
> deseniyle ilerledi (utils.js, audit.js, managed-firms.js ayrıştı; app.js 4387→3948).
> Bu yöntem **leaf** modüllerde işe yaradı ama merkezî/entangled alanlar (özellikle
> dashboard chart'ları) için sürdürülebilir değil — bu plan ESM'e geçişi tanımlar.

## 1. Neden ESM?

Klasik global-script yöntemi tıkanıyor:

- **Paylaşılan mutable state.** Dashboard chart state'i (`_catChart`, `_firmChart`,
  `_weeklyChart`) hem chart render fonksiyonlarında hem app.js'te kalan
  `renderBars`/`loadWeeklyTrend`'de kullanılıyor. Global-script ile ayırmak state
  sahipliğini iki dosyaya böler → kırılgan.
- **Büyüyen eslint globals.** Her taşımada çağrılan/çağıran her isim
  `.eslintrc.json` globals'a ekleniyor (şu an ~25 isim). Bağımlılıklar örtük;
  linter gerçek grafiği görmüyor. (Örn. `typeof`-guard'lı çağrı bile no-undef'e
  takıldı → filterFullByFirm/updateTeamOptions da eklendi.)
- **Örtük yükleme sırası.** `chart→utils→app→audit→managed-firms` sırası elle
  korunuyor; kırılırsa sessiz runtime hatası.

ESM bunları **açık `import`/`export`** ile çözer: gerçek bağımlılık grafiği,
otomatik sıralama, statik analiz, ağaç-sağlıklı ayrıştırma.

## 2. Ana Kısıtlar (ölçülmüş — v5.41)

| Kısıt | Değer | Etki |
|---|---|---|
| Inline handler (`onclick=` vb.) | **183** (app.html 149 + JS template 34) | Modül fonksiyonu global değil → `window` köprüsü şart |
| Reassign edilen top-level state | **~14** (`tasks`, `USERS`, `currentUser`, `selectedUserId`, `firmUsers`, `currentFilter`, `dashPage`, `currentCategoryFilter`, `INVITATIONS`, `notifications`, `schedView`, `calYear`, `calMonth`, `boardCards`, `boardUsers`) | ESM live-binding reassign edilemez → **tek state nesnesi** gerek |
| Build step | **Yok** | Native ESM (build-free) mümkün; bundler opsiyonel |
| CSP | `script-src 'self' 'unsafe-inline'` | `type=module` + inline onclick **serbest** — blocker değil |
| JS testi | **Yok** | Faz başına tarayıcı smoke doğrulaması |
| Cache-busting | `?v={{version}}` query + sw.js `CACHE` bump | ESM import path'lerinde `?v=` awkward → çözüm gerek (bkz. §5) |

## 3. Anahtar Teknikler (big-bang'i önleyen)

1. **`window` köprüsü.** `unsafe-inline` sayesinde inline `onclick="foo()"` çalışır
   — **yeter ki `foo` global olsun.** ESM modülü, inline handler'ların çağırdığı
   fonksiyonları `expose('foo', foo)` ile `window`'a bağlar. Böylece 183 handler'ı
   **bir kerede yeniden yazmadan** ESM'e geçebiliriz. (Handler'ları event
   delegation'a çevirmek Faz 5'e — opsiyonel — bırakılır.)
2. **Tek state nesnesi.** `state.js` bir `state` nesnesi export eder
   (`state.tasks`, `state.currentUser`, …). **Property assignment** (`state.tasks = …`)
   hem klasik (`window.state.tasks`) hem ESM (`import { state }`) tarafında aynı
   nesneyi yazar — "binding reassign edilemez" sorununu tamamen atlar. Geçiş
   sırasında klasik app.js `window.state`, modüller `import` kullanır.

## 4. Kademeli Yol (her faz ayrı ayrı shippable + doğrulanabilir)

**Faz 1 — Entry + köprü altyapısı.**
`main.js` (`<script type="module">`) tek ESM giriş noktası olur. `bridge.js`:
`export function expose(name, fn){ window[name] = fn; }`. Mevcut klasik script'ler
korunur; main.js başlangıçta boş/bootstrap. (ESM kanalını klasiğin yanında açar.)
Risk: çok düşük. Çıktı gözlemlenebilir değil (altyapı) → sadece "sayfa hâlâ açılıyor".

**Faz 2 — State modülü.**
`state.js` + `state` nesnesi. app.js'in ~14 top-level `let`'i `state.*`'a taşınır
(mekanik, yüksek dokunuş ama davranış aynı). app.js klasik kaldığından
`state.js` ayrıca `window.state = state` yapar. Doğrulama: tüm sayfalar + filtreler
çalışıyor. **En kritik/riskli faz** — küçük parçalara bölünebilir (önce `tasks`,
sonra dashboard state, vb.).

**Faz 3 — Leaf modülleri ESM'e çevir.**
utils.js / audit.js / managed-firms.js gerçek `export`'a geçer; `state`, `escapeHtml`
vb. `import` eder; inline handler çağıranları `expose()` eder. Klasik `<script>`
etiketleri kaldırılır, `main.js` bunları `import` eder. eslint globals küçülmeye
başlar. Doğrulama: her sayfa + audit/managed-firms.

**Faz 4 — app.js'i alan modüllerine böl.**
`dashboard.js` (chart'lar dahil — state artık `state.js`'te, sahiplik sorunu yok),
`tasks.js`, `admin.js`, `notifications.js`, `settings.js`, `board.js`, `portal`…
Her biri `state` + ortak util import eder, handler'ları `expose()` eder. app.js
bir "orchestrator"a küçülür veya tamamen erir. En büyük değer burada.

**Faz 5 — (Opsiyonel, sonra) inline handler'ları event delegation'a çevir.**
`onclick=` → `addEventListener`/delegation; `window` köprüsü kaldırılır. 183
handler → büyük iş, ayrı değerlendirilir. ESM geçişi için **şart değil**.

## 5. Cache-busting / sw.js

ESM `import` path'leri statiktir; `?v=` query eklemek zahmetli. Seçenekler:
- **(a) Versiyonlu klasör:** `/static/js/` yerine deploy'da `/static/js/` içeriği
  versiyon damgalı (veya `main.js?v=` yalnız entry'de, alt import'lar relative +
  sw.js cache bump'a güvenir). En basit; mevcut sw.js `CACHE` bump zaten her
  sürümde eskiyi siliyor.
- **(b) Bundler (esbuild/rollup):** tek hash'li `bundle.[hash].js`. Temiz
  cache-busting + tek istek, ama CI/deploy'a **build step** ekler. Şu an build yok.

**Öneri:** Faz 1–4 boyunca **(a) native ESM + sw.js cache**; yük performansı sorun
olursa (çok sayıda küçük istek) Faz 4 sonrası **(b) esbuild** değerlendirilir.

## 6. Build: native ESM vs bundler (karar noktası)

- **Native ESM (build-free):** mevcut "Flask düz dosya sunar" akışı korunur, deploy
  değişmez. Dezavantaj: modül sayısı arttıkça çok HTTP isteği (iç ağ uygulaması
  için kabul edilebilir), cache-busting §5(a).
- **esbuild bundle:** tek dosya, ağaç-sağlıklı, hash'li. Dezavantaj: CI'ye build
  job, deploy'a artefakt kopyalama, `requirements`/Docker'a node.

**Öneri:** native ESM ile başla (sıfır altyapı değişikliği), bundler'ı sonraya sakla.

## 7. Test / Doğrulama

- Backend: mevcut pytest (409) değişmez.
- Frontend: JS testi yok → **faz başına tarayıcı smoke**: login → her sayfa render
  + konsol temiz + kritik etkileşim (filtre, period switcher, CSV). (Mevcut yerel
  önizleme akışı `run_preview.sh` + tarayıcı MCP ile.)
- İsteğe bağlı iyileştirme: minimal Playwright smoke (login + 5 sayfa + 0 console
  error) — regresyon ağı olarak Faz 1'de eklenebilir.

## 8. Risk & Geri Alma

- Her faz **bağımsız shippable**; `window` köprüsü tüm geçiş boyunca inline
  handler'ları çalışır tutar → kısmi geçişte kırılma yok.
- Geri alma = fazın PR'ını revert.
- **En riskli faz: 2 (state)** — küçük alt-adımlara bölünür, her biri ayrı sürüm.

## 9. Kaba Efor / Sürüm Haritası (öneri)

| Faz | İş | Tahmini sürüm |
|---|---|---|
| 1 | Entry + bridge + (ops.) Playwright smoke | 1 sürüm |
| 2 | State modülü (alt-adımlara bölünebilir) | 2–3 sürüm |
| 3 | Leaf modülleri ESM | 1–2 sürüm |
| 4 | app.js → alan modülleri (dashboard dahil) | 3–5 sürüm |
| 5 | inline → event delegation; `window` köprüsü kaldırılır (KAPSAMDA) | 2–3 sürüm |

Cadence korunur (her 2 develop'ta 1 prod release, merge-commit).

## 10. Kararlar (2026-08-18 — onaylandı)

1. **Native ESM (build-free)** ile başlanır (deploy değişmez, bundler sonraya saklı). ✅
2. **Playwright şimdilik atlanır.** Faz-başı tarayıcı smoke (yerel önizleme + MCP)
   + tüm fazlar bitince **uzun manuel test dönemi** (V6 öncesi) doğrulama ağı olur.
   İleride istenirse eklenebilir. ✅
3. **Faz 5 KAPSAMA DAHİL** — inline handler'lar event delegation'a çevrilir, `window`
   köprüsü en sonda kaldırılır. ✅
4. **Şimdi başlanır** (v5.42, Faz 1). ✅

**Hedef:** Tüm fazlar (1–5) tamamlanır → uzun manuel test dönemi → **V6** sürümü.
Cadence korunur (her 2 develop'ta 1 prod release).
