// ══════════════════════════════════════════════════════════
//  audit.js — Denetim Kayıtları (Audit Log) sayfası (v5.40)
//
//  app.js modülerleştirmesi 3. adım: bütün bir FEATURE alanı ayrı dosyaya.
//  app.js'ten SONRA yüklenir. Dış bağımlılıklar: escapeHtml (utils.js),
//  showToast + firmUsers (app.js). Inline onclick (setAuditRange/resetAuditFilters/
//  exportAuditCsv) ve app.js çağrıları (initAuditPage/loadAuditLog) için tanımlar
//  global kalır. Davranış birebir aynı.
// ══════════════════════════════════════════════════════════

const AUDIT_ACTION_LABELS = {
  'task.create':'Görev Oluşturma', 'task.assign':'Görev Atama',
  'task.update':'Görev Güncelleme','task.complete':'Görev Tamamlama',
  'task.reopen':'Görev Yeniden Açma','task.manager_note':'IT Müdürü Notu',
  'task.delete':'Görev Silme',
  'user.invite':'Kullanıcı Daveti','user.update':'Kullanıcı Güncelleme','user.delete':'Kullanıcı Silme',
};
// v5.0 BUG-1 fix: sabit hex değerleri — tema-bağımsız (Inventist temasında
// var(--accent) #ffffff olduğu için beyaz on beyaz badge görünmez oluyordu).
// Tüm badge'ler beyaz text üstüne kontrastlı renk göstermeli, tema değiştiğinde
// audit log'un okunabilirliği bozulmamalı.
const AUDIT_ACTION_COLORS = {
  'task.create':'#34d058',           // yeşil — oluşturma
  'task.assign':'#f4b942',           // gold — atama
  'task.update':'#7f6cf7',           // mor — güncelleme
  'task.complete':'#34d058',         // yeşil — tamamlanma
  'task.reopen':'#ff5f3d',           // turuncu — yeniden açma
  'task.manager_note':'#ef4444',     // kırmızı — vurgu
  'task.delete':'#f85149',           // kırmızı — silme
  'user.invite':'#34d058',           // yeşil — davet
  'user.update':'#7f6cf7',           // mor — kullanıcı güncelleme
  'user.delete':'#f85149',           // kırmızı — silme
};

function initAuditPage() {
  // Hedef kullanıcı dropdown'u firmUsers'tan doldur
  const sel = document.getElementById('audit-target-user');
  if (sel && firmUsers.length) {
    sel.innerHTML = '<option value="">Tümü</option>' +
      firmUsers.map(u => `<option value="${u.id}">${escapeHtml(u.full_name)}</option>`).join('');
  }
  // Varsayılan: son 30 gün
  const start = document.getElementById('audit-start');
  const end   = document.getElementById('audit-end');
  if (start && !start.value && end && !end.value) setAuditRange('30d');
  // Otomatik yükle
  loadAuditLog();
}

function setAuditRange(kind) {
  const now = new Date();
  const end = now.toISOString().slice(0,10);
  let start = end;
  if (kind === '7d')  { const d = new Date(now); d.setDate(d.getDate()-6);  start = d.toISOString().slice(0,10); }
  if (kind === '30d') { const d = new Date(now); d.setDate(d.getDate()-29); start = d.toISOString().slice(0,10); }
  if (kind === 'month') { start = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0,10); }
  if (kind === 'today') { start = end; }
  document.getElementById('audit-start').value = start;
  document.getElementById('audit-end').value   = end;
}

function resetAuditFilters() {
  document.getElementById('audit-start').value = '';
  document.getElementById('audit-end').value   = '';
  document.getElementById('audit-action').value = '';
  document.getElementById('audit-target-user').value = '';
  loadAuditLog();
}

// v5.14 — Denetim kayıtlarını ekrandaki filtrelerle CSV (Excel) olarak indir.
function _auditFilterParams() {
  const params = new URLSearchParams();
  const s = document.getElementById('audit-start')?.value;
  const e = document.getElementById('audit-end')?.value;
  const a = document.getElementById('audit-action')?.value;
  const t = document.getElementById('audit-target-user')?.value;
  if (s) params.set('start', s);
  if (e) params.set('end', e);
  if (a) params.set('action', a);
  if (t) params.set('target_user_id', t);
  return params;
}
function exportAuditCsv() {
  window.location.href = '/api/audit/export?' + _auditFilterParams().toString();
  showToast('ok', 'CSV indiriliyor…');
}

async function loadAuditLog() {
  const tbody = document.getElementById('audit-tbody');
  const count = document.getElementById('audit-count');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-muted);font-size:12px">Yükleniyor…</td></tr>';
  const params = _auditFilterParams();
  try {
    const res = await fetch('/api/audit?' + params.toString());
    if (!res.ok) throw new Error((await res.json()).error || 'API hatası');
    const data = await res.json();
    if (count) count.textContent = `${data.rows.length} / ${data.total} kayıt`;
    if (!data.rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-muted);font-size:12px">Bu filtrelerle kayıt bulunamadı.</td></tr>';
      return;
    }
    tbody.innerHTML = data.rows.map(r => {
      const label = AUDIT_ACTION_LABELS[r.action] || r.action;
      const color = AUDIT_ACTION_COLORS[r.action] || 'var(--text-muted)';
      const dt = r.created_at ? new Date(r.created_at) : null;
      const dtStr = dt ? dt.toLocaleString('tr-TR', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
      return `<tr>
        <td style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--text-muted)">${dtStr}</td>
        <td><span style="font-size:10px;padding:2px 8px;border-radius:4px;background:${color};color:#fff;font-weight:600;white-space:nowrap">${escapeHtml(label)}</span></td>
        <td style="font-size:12px">${escapeHtml(r.actor_name || '—')}</td>
        <td style="font-size:12px;color:var(--text-muted)">${escapeHtml(r.target_name || '—')}</td>
        <td style="font-size:12px">${escapeHtml(r.summary || '')}</td>
      </tr>`;
    }).join('');
  } catch(err) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--danger);font-size:12px">Hata: ${escapeHtml(err.message)}</td></tr>`;
  }
}
