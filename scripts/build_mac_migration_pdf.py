#!/usr/bin/env python3
"""IT Tracker — Mac geçiş rehberi PDF üreteci (ReportLab tabanlı).

ReportLab saf Python — Windows'ta GTK/Cairo gerektirmez.

Çalıştırma:
    source venv/Scripts/activate    # Windows
    python scripts/build_mac_migration_pdf.py

Çıktı: docs/mac-migration-guide.pdf
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Preformatted, Table, TableStyle, KeepTogether,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_PDF = ROOT / "docs" / "mac-migration-guide.pdf"

# ── Renkler (IT Tracker tema'sından) ──
ACCENT  = HexColor("#00b899")
DARK    = HexColor("#0f1419")
TEXT    = HexColor("#1f2937")
MUTED   = HexColor("#6b7e93")
BG_CODE = HexColor("#f3f4f6")
BORDER  = HexColor("#d1d5db")
TIP_BG  = HexColor("#eef9f6")
HEAD_BG = HexColor("#00b899")
ALT_BG  = HexColor("#f9fafb")

# ── Stiller ──
ST_TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22, leading=26,
                          textColor=DARK, spaceAfter=4)
ST_LEAD  = ParagraphStyle("lead", fontName="Helvetica", fontSize=11, leading=15,
                          textColor=TEXT, spaceAfter=4)
ST_META  = ParagraphStyle("meta", fontName="Courier", fontSize=8, leading=11,
                          textColor=MUTED, spaceAfter=14)
ST_LOGO  = ParagraphStyle("logo", fontName="Courier-Bold", fontSize=14, leading=16,
                          textColor=ACCENT, spaceAfter=2)

ST_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14, leading=18,
                       textColor=DARK, spaceBefore=14, spaceAfter=6,
                       borderPadding=0)
ST_H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=14,
                       textColor=TEXT, spaceBefore=8, spaceAfter=3)

ST_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14,
                         textColor=TEXT, alignment=TA_LEFT, spaceAfter=4)
ST_BULLET = ParagraphStyle("bullet", parent=ST_BODY, leftIndent=14, bulletIndent=2,
                           bulletFontName="Helvetica-Bold", bulletFontSize=10)
ST_CHECK = ParagraphStyle("check", parent=ST_BODY, leftIndent=18, bulletIndent=2)
ST_TIP   = ParagraphStyle("tip", parent=ST_BODY, leftIndent=10, rightIndent=6,
                          backColor=TIP_BG, borderColor=ACCENT, borderWidth=0,
                          borderPadding=(6, 8, 6, 10), spaceBefore=4, spaceAfter=8,
                          textColor=DARK)
ST_CODE  = ParagraphStyle("code", fontName="Courier", fontSize=8.5, leading=11.5,
                          textColor=DARK, leftIndent=8, rightIndent=8,
                          backColor=BG_CODE, borderColor=BORDER, borderWidth=0.5,
                          borderPadding=(6, 8, 6, 10), spaceBefore=2, spaceAfter=8)

ST_FOOTER = ParagraphStyle("footer", fontName="Courier", fontSize=8, leading=11,
                           textColor=MUTED, alignment=1)


def _h2(text):
    """Section başlığı + altta accent çizgi."""
    return [Paragraph(text, ST_H2)]


def _h3(text):
    return [Paragraph(text, ST_H3)]


def _p(text):
    return [Paragraph(text, ST_BODY)]


def _tip(text):
    return [Paragraph(text, ST_TIP)]


def _code(text):
    """Code block — Preformatted satırları korur."""
    return [Preformatted(text, ST_CODE)]


def _bullets(items):
    return [Paragraph(f"• {it}", ST_BULLET) for it in items]


def _checks(items):
    return [Paragraph(f"☐ {it}", ST_CHECK) for it in items]


def _table(header, rows, col_widths):
    data = [header] + rows
    cell_paragraphs = []
    for r_idx, row in enumerate(data):
        cell_row = []
        for c in row:
            if r_idx == 0:
                style = ParagraphStyle("th", fontName="Courier-Bold", fontSize=8.5,
                                       leading=11, textColor=HexColor("#ffffff"))
            else:
                style = ParagraphStyle("td", fontName="Helvetica", fontSize=8.8,
                                       leading=11.5, textColor=TEXT)
            cell_row.append(Paragraph(c, style))
        cell_paragraphs.append(cell_row)
    t = Table(cell_paragraphs, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])
    # Alt satır zebra
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), ALT_BG)
    t.setStyle(style)
    return [t, Spacer(1, 6)]


def _on_page(canvas, doc):
    """Her sayfa altına footer + sayfa numarası."""
    canvas.saveState()
    canvas.setFont("Courier", 7.5)
    canvas.setFillColor(MUTED)
    # Sol alt
    canvas.drawString(18 * mm, 12 * mm, "IT Tracker — Mac Geçiş Rehberi")
    # Sağ alt sayfa
    page_text = f"{doc.page} / {{pages}}"  # placeholder, simple count
    canvas.drawRightString(192 * mm, 12 * mm, str(doc.page))
    canvas.restoreState()


def build():
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title="IT Tracker — Mac Geçiş Rehberi",
        author="Claude Code",
    )

    story = []

    # ── Header ──
    story.append(Paragraph("⬡ IT//TRACKER", ST_LOGO))
    story.append(Paragraph("Mac Geçiş Rehberi", ST_TITLE))
    story.append(Paragraph(
        "Windows PC'den macOS'e taşıma — sıfırdan kurulum + dosya transferi + doğrulama",
        ST_LEAD))
    story.append(Paragraph(
        "Hazırlayan: Claude Code &nbsp;·&nbsp; Tarih: 2026-05-05 &nbsp;·&nbsp; Sürüm: v5.0 (Plan C sonrası)",
        ST_META))

    # ── 0. Önce Windows ──
    story += _h2("0. Önce Windows'ta Hazırlık")
    story += _p("Mac'e geçmeden önce Windows'tan transfer edilecek dosyaları topla.")

    story += _h3("Transfer edilecek dosyalar")
    story += _table(
        ["Dosya", "Windows yolu", "Neden"],
        [
            [".env",
             "C:\\Users\\levent.can\\Projects\\ittracker\\.env",
             "Secret keys, SMTP, O365 config"],
            ["ms_cer_secret.txt",
             "%USERPROFILE%\\Documents\\ms_cer_secret.txt",
             "O365 OAuth secret"],
            ["it_tracker.db",
             "...\\ittracker\\instance\\it_tracker.db",
             "Lokal dev DB (opsiyonel)"],
            ["MEMORY.md",
             "%USERPROFILE%\\.claude\\projects\\C--Users-levent-can-Projects-ittracker\\memory\\MEMORY.md",
             "Claude Code proje hafızası — Mac'te yeni session tüm v4.x→v5.0 sürüm geçmişini görür"],
        ],
        col_widths=[35 * mm, 75 * mm, 64 * mm],
    )

    story += _h3("Toplama komutu (Windows CMD)")
    story += _code(
        "mkdir C:\\Users\\levent.can\\Documents\\to-mac\n"
        "copy C:\\Users\\levent.can\\Projects\\ittracker\\.env C:\\Users\\levent.can\\Documents\\to-mac\\\n"
        "copy C:\\Users\\levent.can\\Projects\\ittracker\\instance\\it_tracker.db C:\\Users\\levent.can\\Documents\\to-mac\\\n"
        "copy C:\\Users\\levent.can\\Documents\\ms_cer_secret.txt C:\\Users\\levent.can\\Documents\\to-mac\\\n"
        "copy C:\\Users\\levent.can\\.claude\\projects\\C--Users-levent-can-Projects-ittracker\\memory\\MEMORY.md "
        "C:\\Users\\levent.can\\Documents\\to-mac\\"
    )
    story += _tip("<b>Aktarım yöntemi:</b> AirDrop, iCloud Drive, USB veya OneDrive. "
                  "<font face='Courier'>to-mac</font> klasörünü Mac'e taşı.")

    story.append(PageBreak())

    # ── 1. Mac Önkoşulları ──
    story += _h2("1. Mac Önkoşulları")
    story += _p("Mac terminal'de (Terminal.app veya iTerm2) sırayla çalıştır.")

    story += _h3("1.1 Homebrew (paket yöneticisi)")
    story += _code('/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
    story += _tip("Kurulum sonunda terminal'in <font face='Courier'>brew</font>'u tanıması için "
                  "söylediği <font face='Courier'>eval ...</font> satırını çalıştırmayı unutma.")

    story += _h3("1.2 Python 3.12 + Node + Native lib'ler")
    story += _code("brew install git python@3.12 node pango libffi cairo gdk-pixbuf")
    story += _p("Pango/Cairo WeasyPrint için zorunlu (PDF rapor üretimi).")

    story += _h3("1.3 Git kullanıcı bilgisi (yoksa)")
    story += _code(
        'git config --global user.name "Levent Mahir Can"\n'
        'git config --global user.email "leventmahircan@gmail.com"'
    )

    # ── 2. Repo + Dependencies ──
    story += _h2("2. Repo Clone + Dependencies")

    story += _h3("2.1 Clone")
    story += _code(
        "mkdir -p ~/Projects\n"
        "cd ~/Projects\n"
        "git clone https://github.com/Elanorth/ittracker.git\n"
        "cd ittracker"
    )

    story += _h3("2.2 Virtual environment + paketler")
    story += _code(
        "python3.12 -m venv venv\n"
        "source venv/bin/activate\n"
        "pip install --upgrade pip\n"
        "pip install -r requirements.txt\n"
        "pip install -r requirements-dev.txt"
    )
    story += _tip("<b>Bash uyarısı:</b> Mac'te venv aktivasyonu Windows'tan farklı: "
                  "<font face='Courier'>source venv/bin/activate</font> "
                  "(Windows: <font face='Courier'>source venv/Scripts/activate</font>).")

    # ── 3. Dosya Transferi ──
    story += _h2("3. Dosya Transferi")
    story += _p("Windows'tan getirdiğin <font face='Courier'>to-mac</font> klasörünü Mac'te "
                "<font face='Courier'>~/Downloads/to-mac</font>'e koyduğunu varsayıyorum.")

    story += _h3("3.1 .env, DB ve secret")
    story += _code(
        "cp ~/Downloads/to-mac/.env ~/Projects/ittracker/.env\n"
        "mkdir -p ~/Projects/ittracker/instance\n"
        "cp ~/Downloads/to-mac/it_tracker.db ~/Projects/ittracker/instance/\n"
        "cp ~/Downloads/to-mac/ms_cer_secret.txt ~/Documents/"
    )

    story += _h3("3.2 .env'deki Windows path'leri Mac'e uyarla")
    story += _code("nano ~/Projects/ittracker/.env")
    story += _p("Kontrol edilecekler:")
    story += _bullets([
        "<b>BACKUP_DIR</b> — Windows path varsa Mac path'iyle değiştir, klasörü oluştur: "
        "<font face='Courier'>mkdir -p ~/it-tracker-backups</font>",
        "<b>DATABASE_URL=sqlite:///it_tracker.db</b> — değişmez (relative path)",
        "<b>SMTP, O365</b> değerleri — aynı kalır",
    ])

    story.append(PageBreak())

    # ── 4. Test + Dev Sunucu ──
    story += _h2("4. Test + Dev Sunucu")

    story += _h3("4.1 Pytest")
    story += _code(
        "cd ~/Projects/ittracker\n"
        "source venv/bin/activate\n"
        "pytest -q"
    )
    story += _p("Beklenen: <b>191 passed, 0 failed</b> (Plan C + bug fix sonrası).")

    story += _h3("4.2 Dev sunucu")
    story += _code("python app.py")
    story += _p("Tarayıcıdan <font face='Courier'>http://localhost:5000</font> açılmalı.")

    story += _h3("4.3 Smoke test checklist")
    story += _checks([
        "Dashboard açılıyor",
        "&quot;Yönettiğim Firmalar&quot; sayfası görünür ve veri yüklüyor",
        "Rutin görev tamamla → işaretli kalıyor (v5.0 hotfix kontrolü)",
        "Türkçe karakterler tüm sayfalarda doğru",
        "Mobile viewport (DevTools): hamburger ☰ çalışıyor",
    ])

    # ── 5. Claude Code Kurulumu ──
    story += _h2("5. Claude Code Kurulumu")
    story += _p("Anthropic'in resmi kurulum talimatına bak: "
                "<font face='Courier'>https://claude.com/claude-code</font>")

    story += _h3("5.1 MEMORY.md transferi (önemli)")
    story += _p("Bu dosya tüm v4.1→v5.0 sürüm notlarını + mimari kararlarını içerir. "
                "Mac'te yeni Claude session'ında otomatik görülür.")
    story += _code(
        "USERNAME=$(whoami)\n"
        "mkdir -p ~/.claude/projects/-Users-${USERNAME}-Projects-ittracker/memory\n"
        "cp ~/Downloads/to-mac/MEMORY.md ~/.claude/projects/-Users-${USERNAME}-Projects-ittracker/memory/MEMORY.md"
    )
    story += _tip("<b>Path Key:</b> Claude Code project path'ini &quot;/&quot; → &quot;-&quot; eşlemesiyle "
                  "key'e çevirir. Mac'te kullanıcı <font face='Courier'>levent</font> ise klasör adı "
                  "<font face='Courier'>-Users-levent-Projects-ittracker</font> olur.")

    story += _h3("5.2 Subagent'lar")
    story += _p("<font face='Courier'>.claude/agents/ui-advisor.md</font> ve "
                "<font face='Courier'>.claude/agents/qa-tester.md</font> repo'da, otomatik gelir.")
    story += _tip("<b>Restart:</b> Yeni custom agent eklediğinde Claude Code'u kapat-aç, yeni agent listesine düşsün.")

    story.append(PageBreak())

    # ── 6. SSH Key ──
    story += _h2("6. SSH Key — Prod Deploy İçin")
    story += _p("Prod sunucu <font face='Courier'>leventcan@10.34.0.62</font>. Mac'ten deploy istersen yeni SSH key gerek.")

    story += _h3("6.1 Yeni key oluştur")
    story += _code(
        'ssh-keygen -t ed25519 -C "levent-mac" -f ~/.ssh/id_ed25519_ittracker\n'
        '# Passphrase boş bırakabilirsin'
    )

    story += _h3("6.2 Prod'a ekle")
    story += _code("ssh-copy-id -i ~/.ssh/id_ed25519_ittracker.pub leventcan@10.34.0.62")

    story += _h3("6.3 SSH config alias (opsiyonel)")
    story += _code(
        "cat >> ~/.ssh/config << 'EOF'\n"
        "\n"
        "Host ittracker-prod\n"
        "  HostName 10.34.0.62\n"
        "  User leventcan\n"
        "  IdentityFile ~/.ssh/id_ed25519_ittracker\n"
        "EOF\n"
        "chmod 600 ~/.ssh/config"
    )
    story += _p("Artık <font face='Courier'>ssh ittracker-prod</font> ile direkt bağlanırsın.")

    story += _h3("6.4 deploy.sh (Mac eşdeğeri)")
    story += _p("<font face='Courier'>deploy.bat</font> Windows-spesifik. Mac'te aynı işi yapan "
                "<font face='Courier'>deploy.sh</font> yazılması gerekir. Şimdilik manuel:")
    story += _code(
        "git push github main\n"
        "ssh ittracker-prod 'cd ~/ittracker && ./pull-and-rebuild.sh'"
    )
    story += _tip("İstersen <font face='Courier'>deploy.sh</font> Mac portunu birlikte yazarız — "
                  "<font face='Courier'>deploy.bat</font>'ı satır satır bash eşdeğerine çeviririz.")

    # ── 7. Bilinen Farklar ──
    story += _h2("7. Bilinen Farklar (Windows ↔ macOS)")
    story += _table(
        ["Konu", "Windows", "macOS"],
        [
            ["venv aktivasyon", "source venv/Scripts/activate", "source venv/bin/activate"],
            ["Path ayraç", "\\", "/"],
            ["Home dir", "%USERPROFILE%", "~ veya $HOME"],
            ["Console encoding", "cp1254 (Türkçe)", "UTF-8 (default)"],
            ["Line endings", "CRLF", "LF"],
            ["Python launcher", "py veya python", "python3 veya python3.12"],
            ["Claude path key", "C--Users-levent-can-...", "-Users-USERNAME-..."],
        ],
        col_widths=[40 * mm, 60 * mm, 74 * mm],
    )

    story.append(PageBreak())

    # ── 8. Doğrulama ──
    story += _h2("8. Doğrulama Checklist")
    story += _checks([
        "Repo clone edildi: <font face='Courier'>~/Projects/ittracker</font>",
        "venv kuruldu, <font face='Courier'>pip install</font> hatasız bitti",
        "Native lib'ler kuruldu (pango, libffi, cairo)",
        ".env, ms_cer_secret.txt, instance/it_tracker.db kopyalandı",
        "<font face='Courier'>pytest -q</font> → 191 passed",
        "<font face='Courier'>python app.py</font> → localhost:5000 açılıyor",
        "Login → super_admin → Yönettiğim Firmalar sayfası çalışıyor",
        "Rutin görev toggle: işaretle → işaretli kalıyor (v5.0 fix)",
        "Claude Code kuruldu, MEMORY.md yerinde",
        "SSH key prod'a eklendi (deploy ihtiyacı varsa)",
    ])

    # ── 9. Sorun Çıkarsa ──
    story += _h2("9. Sorun Çıkarsa")
    story += _table(
        ["Belirti", "Çözüm"],
        [
            ["cairo / WeasyPrint hatası",
             "brew install cairo pango gdk-pixbuf libffi · brew link --force libffi"],
            ["ModuleNotFoundError: No module named 'X'",
             "venv aktif değil. source venv/bin/activate sonra pip install -r requirements.txt"],
            ["SQLite DB locked",
             "Başka python app.py instance'ı çalışıyor. ps aux | grep python · kill"],
            ["localhost:5000 açılmıyor",
             "5000 portu macOS AirPlay ile çakışır. app.py'da port=5001 dene veya AirPlay Receiver'ı kapat (System Settings → General → AirDrop &amp; Handoff)"],
            ["Türkçe karakter bozuk (terminal)",
             "export LANG=tr_TR.UTF-8 (zsh için ~/.zshrc'ye ekle)"],
            ["git push reject",
             "git pull github main · sonra tekrar git push"],
        ],
        col_widths=[55 * mm, 119 * mm],
    )

    # ── Footer ──
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "IT Tracker · v5.0 · 2026-05-05<br/>"
        "<font size='7'>Repo: github.com/Elanorth/ittracker · Prod: ittracker.inventist.com.tr</font>",
        ST_FOOTER))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    size_kb = OUT_PDF.stat().st_size / 1024
    print(f"OK: {OUT_PDF} ({size_kb:.1f} KB, {doc.page} sayfa)")


if __name__ == "__main__":
    build()
