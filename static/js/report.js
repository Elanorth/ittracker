// ══════════════════════════════════════════════════════════
//  report.js — Rapor sayfası (v5.61, ESM Faz 4f-1)
//
//  Aylık görev raporu: ay seçici + kategori ilerleme istatistikleri + PDF önizleme
//  + CSV export + e-posta gönderimi. app.js'ten çıkarıldı.
//  main.js import edip public fonksiyonları exposeAll ile window'a bağlar.
//
//  Bağımlılıklar: CAT_LABELS (utils import), state (import). showToast app.js
//  klasik → bare global (app.js modül olunca import'a döner).
// ══════════════════════════════════════════════════════════
import { CAT_LABELS } from './utils.js';
import { state } from './state.js';

const MONTH_TR_JS = {1:'Ocak',2:'Şubat',3:'Mart',4:'Nisan',5:'Mayıs',6:'Haziran',
                     7:'Temmuz',8:'Ağustos',9:'Eylül',10:'Ekim',11:'Kasım',12:'Aralık'};

// Alıcı mail — oturumda sakla, sayfa yenilenmesinde sıfırlanmaz
let _reportToMail = '';

export function initReportPage() {
  // Ay seçiciyi doldur (son 12 ay)
  const sel = document.getElementById('report-month-sel');
  if (!sel) return;
  sel.innerHTML = '';
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const m = d.getMonth() + 1;
    const y = d.getFullYear();
    const opt = document.createElement('option');
    opt.value = `${y}-${m}`;
    opt.textContent = `${MONTH_TR_JS[m]} ${y}`;
    sel.appendChild(opt);
  }
  // Alıcı mail: daha önce girilmişse onu koru, yoksa /api/me'den çek
  const toEl = document.getElementById('report-to');
  if (_reportToMail) {
    if (toEl) toEl.value = _reportToMail;
  } else {
    fetch('/api/me').then(r => r.json()).then(u => {
      _reportToMail = u.email || '';
      if (toEl && !toEl.value) toEl.value = _reportToMail;
    }).catch(() => {});
  }
  onReportMonthChange();
}

// Alıcı mail her değiştiğinde sakla
document.addEventListener('input', e => {
  if (e.target && e.target.id === 'report-to') {
    _reportToMail = e.target.value;
  }
});

function _getSelectedMonthYear() {
  const sel = document.getElementById('report-month-sel');
  if (!sel || !sel.value) return null;
  const [y, m] = sel.value.split('-').map(Number);
  return { month: m, year: y };
}

export async function onReportMonthChange() {
  const my = _getSelectedMonthYear();
  if (!my) return;
  const sub = document.getElementById('report-sub');
  if (sub) sub.textContent = `${MONTH_TR_JS[my.month]} ${my.year} · Gerçek veriler yükleniyor...`;
  const body = document.getElementById('report-stats-body');
  if (body) body.innerHTML = '<div style="padding:24px;text-align:center;font-size:12px;color:var(--text-muted)">Yükleniyor...</div>';
  try {
    const userParam = state.selectedUserId ? `&user_id=${state.selectedUserId}` : '';
    const res = await fetch(`/api/tasks?month=${my.month}&year=${my.year}${userParam}`);
    const taskList = await res.json();
    renderReportStats(taskList, my.month, my.year);
  } catch(e) {
    if (body) body.innerHTML = `<div style="padding:24px;text-align:center;font-size:12px;color:var(--danger)">API hatası: ${e.message}</div>`;
  }
}

function renderReportStats(taskList, month, year) {
  const sub = document.getElementById('report-sub');
  if (sub) sub.textContent = `${MONTH_TR_JS[month]} ${year} · ${taskList.length} görev`;
  const body = document.getElementById('report-stats-body');
  if (!body) return;
  if (!taskList.length) {
    body.innerHTML = '<div style="padding:24px;text-align:center;font-size:12px;color:var(--text-muted)">Bu ay için kayıt bulunamadı.</div>';
    return;
  }
  const done = taskList.filter(t => t.is_done).length;
  const total = taskList.length;
  const rate = total ? Math.round(done/total*100) : 0;
  const cats = ['routine','support','infra','backup','other'];
  const catColors = {routine:'var(--accent)',support:'var(--accent3)',infra:'var(--accent2)',backup:'var(--gold)',other:'var(--text-muted)'};
  const catRows = cats.map(c => {
    const all  = taskList.filter(t => t.category === c);
    const comp = all.filter(t => t.is_done).length;
    if (!all.length) return '';
    const pct = Math.round(comp/all.length*100);
    return `<div class="progress-wrap">
      <div class="progress-label"><span>${CAT_LABELS[c]||c}</span><span style="color:${catColors[c]}">${comp}/${all.length}</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${catColors[c]}"></div></div>
    </div>`;
  }).join('');
  body.innerHTML = catRows + `
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
      <div class="progress-wrap">
        <div class="progress-label"><span style="font-weight:600">Genel İlerleme</span><span style="color:var(--green)">${rate}%</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${rate}%;background:var(--green)"></div></div>
      </div>
    </div>`;
}

export function previewReportPdf() {
  const my = _getSelectedMonthYear();
  if (!my) { showToast('err', 'Lütfen önce ay seçin'); return; }
  const userParam = state.selectedUserId ? `&user_id=${state.selectedUserId}` : '';
  window.open(`/api/report/pdf?month=${my.month}&year=${my.year}${userParam}`, '_blank');
}

// v5.14 — Seçili ayın görev listesini CSV (Excel) olarak indir. Ekrandaki
// ay/kullanıcı kapsamıyla aynı küme (backend _collect_tasks_for_month).
export function exportTasksCsv() {
  const my = _getSelectedMonthYear();
  if (!my) { showToast('err', 'Lütfen önce ay seçin'); return; }
  const userParam = state.selectedUserId ? `&user_id=${state.selectedUserId}` : '';
  window.location.href = `/api/tasks/export?month=${my.month}&year=${my.year}${userParam}`;
  showToast('ok', 'CSV indiriliyor…');
}

export async function sendReportMail() {
  const my = _getSelectedMonthYear();
  if (!my) { showToast('err', 'Lütfen önce ay seçin'); return; }
  const to = document.getElementById('report-to')?.value?.trim();
  const cc = document.getElementById('report-cc')?.value?.trim();
  if (!to) { showToast('err', 'Alıcı mail adresi boş olamaz'); return; }
  showToast('ok', 'Mail gönderiliyor, lütfen bekleyin...');
  try {
    const res  = await fetch('/api/report/send', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ month: my.month, year: my.year, cc: cc||null, user_id: state.selectedUserId || null })
    });
    const data = await res.json();
    if (data.ok) {
      showMailResultModal(true, data.message || 'Mail başarıyla gönderildi', null);
    } else {
      showMailResultModal(false, data.error || 'Bilinmeyen hata', my);
    }
  } catch(e) {
    showMailResultModal(false, `Bağlantı hatası: ${e.message}`, my);
  }
}

function showMailResultModal(success, message, my) {
  const modal = document.getElementById('mail-error-modal');
  const title = document.getElementById('mail-error-title');
  const msgEl = document.getElementById('mail-error-body');
  const hint  = document.getElementById('mail-error-hint');
  if (!modal) return;
  title.textContent = success ? '✅ Mail Gönderildi' : '❌ Mail Gönderilemedi';
  title.style.color = success ? 'var(--green)' : 'var(--danger)';
  msgEl.textContent = message;
  msgEl.style.color = success ? 'var(--text)' : 'var(--danger)';
  // Hata türüne göre ipucu göster
  if (!success) {
    hint.style.display = 'block';
    if (message.includes('kimlik') || message.includes('Authentication') || message.includes('App Password')) {
      hint.textContent = '💡 Office 365 kullanıyorsanız: Ayarlar > SMTP\'de şifre olarak normal şifre yerine uygulama şifresi (App Password) kullanmanız gerekebilir. Azure AD > Kullanıcı > Kimlik Doğrulama bölümünden App Password oluşturabilirsiniz.';
    } else if (message.includes('bağlanam') || message.includes('Connect') || message.includes('Ağ')) {
      hint.textContent = '💡 Sunucuya ulaşılamıyor. SMTP host ve port ayarlarını kontrol edin. Office 365 için: smtp.office365.com:587';
    } else if (message.includes('eksik') || message.includes('SMTP ayar')) {
      hint.textContent = '💡 Ayarlar > SMTP bölümünden SMTP Host, Port, Kullanıcı Adı ve Şifre bilgilerini doldurun.';
    } else {
      hint.textContent = '💡 Hatayı kopyalayarak SMTP sağlayıcınızın destek ekibiyle paylaşabilir veya sistem yöneticinize danışabilirsiniz.';
    }
  } else {
    hint.style.display = 'none';
  }
  modal.classList.remove('hidden');
}
