// ══════════════════════════════════════════════════════════
//  archive.js — Case Arşivi (v5.66, ESM Faz 4f-6)
//
//  Ay-bağımsız destek talebi arama (q/firma/durum filtresi + sayfalama).
//  Bağımlılıklar: escapeHtml (utils), firmChip (tasks). FIRMS/formatDateTR bare.
//  Inline: openEditTask, archGoPage (sayfalama — _archPage modül-local kaldığı için
//  pager onclick doğrudan değişken mutasyonundan archGoPage(n)'e çevrildi).
// ══════════════════════════════════════════════════════════
import { escapeHtml } from './utils.js';
import { firmChip } from './tasks.js';

let _archPage = 1, _archT = null;

export function loadArchivePage() {
  // Firma dropdown'unu doldur (bir kez)
  const fs = document.getElementById('arch-firm');
  if (fs && fs.options.length <= 1) {
    Object.entries(FIRMS).forEach(([slug, f]) => {
      const o = document.createElement('option'); o.value = slug; o.textContent = f.label || slug;
      fs.appendChild(o);
    });
  }
  _archPage = 1;
  archSearch();
}

export function archSearchDebounced() { clearTimeout(_archT); _archT = setTimeout(() => { _archPage = 1; archSearch(); }, 300); }

export async function archSearch() {
  const box = document.getElementById('arch-list');
  const pager = document.getElementById('arch-pager');
  if (!box) return;
  const params = new URLSearchParams({ page: String(_archPage) });
  const q = document.getElementById('arch-q').value.trim();
  const firm = document.getElementById('arch-firm').value;
  const status = document.getElementById('arch-status').value;
  if (q) params.set('q', q);
  if (firm) params.set('firm', firm);
  if (status && status !== 'all') params.set('status', status);
  try {
    const r = await fetch('/api/archive?' + params.toString());
    if (!r.ok) throw new Error();
    const d = await r.json();
    if (!d.items.length) {
      box.innerHTML = '<div style="padding:26px;text-align:center;color:var(--text-muted);font-size:12.5px">Eşleşen talep yok.</div>';
      pager.innerHTML = '';
      return;
    }
    box.innerHTML = d.items.map(i => {
      const st = i.status === 'resolved'
        ? '<span class="prio-badge low" style="background:rgba(40,180,135,.14);color:var(--green);border-color:rgba(40,180,135,.4)">✓ Çözüldü</span>'
        : '<span class="prio-badge med">Açık</span>';
      const owner = i.owner ? escapeHtml(i.owner) : '<span style="color:var(--text-muted)">🫧 havuz</span>';
      const dt = i.created_at ? formatDateTR(i.created_at.slice(0, 10)) : '';
      const code = i.case_code ? `<span class="prio-badge low" style="background:rgba(0,229,192,.12);color:var(--accent);border-color:rgba(0,229,192,.3)">🌐 ${escapeHtml(i.case_code)}</span>` : '';
      return `<div class="task-item" style="align-items:center;cursor:pointer" onclick="openEditTask(${i.id})">
        <div style="font-size:15px">🗄️</div>
        <div>
          <div class="task-title">${escapeHtml(i.title)}</div>
          <div class="task-meta">${code} ${st} ${firmChip(i.firm)}
            <span style="color:var(--text-muted);font-size:10px">· ${escapeHtml(i.reporter_name || '')} ${i.reporter_email ? '&lt;' + escapeHtml(i.reporter_email) + '&gt;' : ''} · ${dt} · Atanan: ${owner}</span></div>
        </div>
        <div></div><div></div>
      </div>`;
    }).join('');
    pager.innerHTML = d.pages > 1 ? `
      <button class="btn btn-outline btn-sm" ${d.page <= 1 ? 'disabled' : ''} onclick="archGoPage(${d.page-1})">‹ Önceki</button>
      <span>${d.page} / ${d.pages} · ${d.total} kayıt</span>
      <button class="btn btn-outline btn-sm" ${d.page >= d.pages ? 'disabled' : ''} onclick="archGoPage(${d.page+1})">Sonraki ›</button>` : `<span>${d.total} kayıt</span>`;
  } catch (e) {
    box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--danger);font-size:12px">Arşiv yüklenemedi.</div>';
  }
}

// Sayfalama — _archPage modül-local; inline pager onclick buradan çağırır.
export function archGoPage(n) { _archPage = Math.max(1, n); archSearch(); }
