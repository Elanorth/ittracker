// ══════════════════════════════════════════════════════════
//  utils.js — Saf/stateless yardımcı fonksiyonlar (v5.38)
//
//  app.js (~4400 satır) modülerleştirmesinin 1. adımı. Buradaki fonksiyonlar
//  yalnızca kendi argümanlarına + DOM/CSS değişkenlerine bağlıdır; app.js'in
//  değişken modül state'ine (tasks, currentUser, FIRMS, TODAY, ...) bağımlı
//  DEĞİLDİR. Klasik <script> olarak app.js'ten ÖNCE yüklenir → tanımlar global
//  kalır, inline onclick ve app.js çağrıları aynen çalışır. Davranış birebir aynı.
// ══════════════════════════════════════════════════════════

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// v5.0 — Rutin görev için periyot-aware tamamlanma etiketi.
// Backend Karar 2=B uyarınca server `date.today()` kullanır; frontend bu helper
// ile kullanıcıya hangi periyot için tamamlandığı/açık olduğu netleşir.
function _periodCompletionLabel(t) {
  if (!t || t.cat !== 'routine' || t.period === 'Tek Seferlik') return '';
  const Y = new Date().getFullYear();
  if (t.period === 'Günlük')   return t.done ? 'Bugün ✓'   : 'Bugün için tamamlanmamış';
  if (t.period === 'Haftalık') return t.done ? 'Bu hafta ✓' : 'Bu hafta için tamamlanmamış';
  if (t.period === 'Aylık')    return t.done ? 'Bu ay ✓'    : 'Bu ay için tamamlanmamış';
  if (t.period === 'Yıllık')   return t.done ? `${Y} ✓`     : `${Y} için tamamlanmamış`;
  return '';
}
// Kısa rozet (UI rozet olarak gösterim için, max 12 karakter)
function _periodCompletionBadge(t) {
  if (!t || t.cat !== 'routine' || t.period === 'Tek Seferlik') return '';
  if (t.period === 'Günlük')   return t.done ? '· Bugün ✓'   : '';
  if (t.period === 'Haftalık') return t.done ? '· Bu hafta ✓' : '';
  if (t.period === 'Aylık')    return t.done ? '· Bu ay ✓'    : '';
  if (t.period === 'Yıllık')   return t.done ? '· ' + new Date().getFullYear() + ' ✓' : '';
  return '';
}

function _cssVar(name) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || '#888';
}
function _chartTheme() {
  return { text: _cssVar('--text'), muted: _cssVar('--text-muted'), grid: _cssVar('--border2') || _cssVar('--border') };
}
// Doughnut ortasına % yazan hafif plugin (tema-duyarlı)
const _centerTextPlugin = {
  id: 'centerText',
  afterDraw(chart, args, opts) {
    if (!opts || opts.text == null) return;
    const { ctx, chartArea } = chart;
    const cx = (chartArea.left + chartArea.right) / 2;
    const cy = (chartArea.top + chartArea.bottom) / 2;
    ctx.save();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = _cssVar('--text');
    ctx.font = "700 22px 'IBM Plex Mono', monospace";
    ctx.fillText(opts.text, cx, cy - 6);
    ctx.fillStyle = _cssVar('--text-muted');
    ctx.font = "9px 'IBM Plex Mono', monospace";
    ctx.fillText(opts.sub || '', cx, cy + 12);
    ctx.restore();
  }
};

// v5.22 — IT ilgisi bekleyen portal case rozeti (yeni case / yeni yanıt)
function unreadBadge(t) {
  if (!t || !t.it_unread || t.source !== 'portal') return '';
  const assigned = t.user_id != null;  // atanmışsa muhtemelen kullanıcı yanıtı
  return ` <span class="unread-badge" title="IT ilgisi bekliyor">${assigned ? '💬 yeni yanıt' : '🆕 yeni'}</span>`;
}
function priorityBadge(t) {
  if (!t || t.cat !== 'support') return '';
  const p = (t.priority || 'orta').toLowerCase();
  const cls = p === 'yüksek' ? 'high' : (p === 'düşük' ? 'low' : 'med');
  const label = p === 'yüksek' ? 'Yüksek' : (p === 'düşük' ? 'Düşük' : 'Orta');
  const dot = p === 'yüksek' ? '⬤' : (p === 'düşük' ? '⬤' : '⬤');
  return ` <span class="prio-badge ${cls}" title="Öncelik">${dot} ${label}</span>`;
}
// v4.5 — SLA rozeti (destek talepleri için)
function slaBadge(t) {
  if (!t || t.cat !== 'support' || !t.sla) return '';
  const s = t.sla;
  const tgt = s.target_hours;
  // Çözüldü
  if (t.done && s.resolution_hours != null) {
    const h = s.resolution_hours;
    const label = h >= 24 ? `${Math.round(h/24*10)/10}g` : `${Math.round(h*10)/10}s`;
    if (s.breached) {
      return ` <span class="prio-badge high" title="SLA aşıldı (hedef ${tgt}s)">⚠ SLA ${label}</span>`;
    }
    return ` <span class="prio-badge low" title="SLA içinde çözüldü (hedef ${tgt}s)">✓ SLA ${label}</span>`;
  }
  // Açık görev
  const rem = s.remaining_hours;
  if (s.breached) {
    const over = Math.abs(rem);
    const label = over >= 24 ? `${Math.round(over/24*10)/10}g` : `${Math.round(over*10)/10}s`;
    return ` <span class="prio-badge high" title="SLA aşıldı (hedef ${tgt}s)">⚠ SLA +${label}</span>`;
  }
  const label = rem >= 24 ? `${Math.round(rem/24*10)/10}g` : `${Math.round(rem*10)/10}s`;
  const cls = rem < (tgt * 0.25) ? 'med' : 'low';
  return ` <span class="prio-badge ${cls}" title="SLA kalan süre (hedef ${tgt}s)">⏱ SLA ${label}</span>`;
}
// v5.15 — portal kaynaklı destek talebi rozeti (case kodu ile)
function portalBadge(t) {
  if (!t || t.source !== 'portal' || !t.case_code) return '';
  return ` <span class="prio-badge low" title="İntranet portalından açıldı" style="background:rgba(0,229,192,.12);color:var(--accent);border-color:rgba(0,229,192,.3)">🌐 ${escapeHtml(t.case_code)}</span>`;
}
// v5.0 — SLA kalan süreyi insan-okur formatta döndürür ("3s 12dk", "1g 4s", "GECİKTİ")
function _slaRemainingHuman(t) {
  if (t.cat !== 'support' || !t.sla) return null;
  const rem = t.sla.remaining_hours;
  if (typeof rem !== 'number') return null;
  if (t.sla.breached || rem < 0) {
    const over = Math.abs(rem);
    if (over >= 24) return { txt: `+${(over/24).toFixed(1)}g`, color: 'var(--danger)' };
    const h = Math.floor(over); const m = Math.round((over - h) * 60);
    return { txt: h ? `+${h}s ${m}dk` : `+${m}dk`, color: 'var(--danger)' };
  }
  if (rem >= 24)  return { txt: `${(rem/24).toFixed(1)}g`, color: 'var(--accent)' };
  const h = Math.floor(rem); const m = Math.round((rem - h) * 60);
  const color = rem < (t.sla.target_hours || 24) * 0.25 ? 'var(--gold)' : 'var(--accent)';
  return { txt: h ? `${h}s ${m}dk` : `${m}dk`, color };
}
