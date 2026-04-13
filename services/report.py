"""PDF Rapor Üretici — ReportLab + Windows Türkçe font desteği"""
import os, tempfile
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

MONTH_TR = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",
            7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}
CAT_LABELS = {"routine":"Rutin","project":"Proje","task":"Anlık Görev",
               "support":"Destek","infra":"Altyapı","backup":"Config Backup","other":"Diğer"}

DARK  = colors.HexColor("#1a1a2e")
ACCENT= colors.HexColor("#00d4aa")
GREEN = colors.HexColor("#3fb950")
RED   = colors.HexColor("#f85149")
GRAY1 = colors.HexColor("#f5f5f5")
GRAY2 = colors.HexColor("#e5e7eb")
MUTED = colors.HexColor("#888888")

# Windows font yolları (Türkçe Unicode desteği için)
FONT_PATHS = [
    (r"C:\Windows\Fonts\arial.ttf",        r"C:\Windows\Fonts\arialbd.ttf"),
    (r"C:\Windows\Fonts\calibri.ttf",      r"C:\Windows\Fonts\calibrib.ttf"),
    (r"C:\Windows\Fonts\segoeui.ttf",      r"C:\Windows\Fonts\segoeuib.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

def _register_font():
    """Windows'ta mevcut Unicode fontu bul ve kaydet."""
    for reg, bold in FONT_PATHS:
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont("UniFont",     reg))
                pdfmetrics.registerFont(TTFont("UniFont-Bold",bold if os.path.exists(bold) else reg))
                return "UniFont", "UniFont-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"

FONT_NORMAL, FONT_BOLD = _register_font()

def generate_monthly_pdf(user, tasks, month, year):
    display_name = (user.full_name or "").strip() or user.username
    path = os.path.join(tempfile.gettempdir(),
                        f"IT_Rapor_{display_name}_{year}_{month:02d}.pdf")
    _build(user, tasks, month, year, path)
    return path

def _build(user, tasks, month, year, path):
    display_name = (user.full_name or "").strip() or user.username
    doc = SimpleDocTemplate(path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"IT Görev Raporu — {display_name} — {MONTH_TR[month]} {year}",
        author=display_name)

    def style(name, font=None, **kw):
        base = getSampleStyleSheet()["Normal"]
        return ParagraphStyle(name, parent=base, fontName=font or FONT_NORMAL, **kw)

    title_s  = style("TT", font=FONT_BOLD, fontSize=20, leading=26, textColor=ACCENT, spaceAfter=4, alignment=TA_CENTER)
    meta_s   = style("MM", fontSize=10, leading=16, textColor=MUTED, spaceAfter=16, alignment=TA_CENTER)
    h2_s     = style("HH", font=FONT_BOLD, fontSize=12, textColor=DARK, spaceBefore=14, spaceAfter=6)
    footer_s = style("FF", fontSize=9,  textColor=MUTED,  alignment=TA_CENTER, spaceBefore=6)
    cell_s   = style("CC", fontSize=8)

    # Rutin görevler tamamlandığında is_done=False sıfırlanır,
    # bu yüzden last_completed bu ay içindeyse de "tamamlandı" say
    from datetime import datetime
    def _is_done(t):
        if t.is_done:
            return True
        if t.category == "routine" and t.last_completed:
            lc = t.last_completed if hasattr(t.last_completed,"month") else datetime.fromisoformat(str(t.last_completed))
            return lc.year == year and lc.month == month
        return False

    done    = [t for t in tasks if _is_done(t)]
    pending = [t for t in tasks if not _is_done(t)]
    rate    = round(len(done)/len(tasks)*100) if tasks else 0

    elems = []
    elems.append(Paragraph(f"IT Görev Raporu — {MONTH_TR[month]} {year}", title_s))
    elems.append(Paragraph(f"{display_name}  |  {user.email}  |  {user.role}", meta_s))
    elems.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=12))

    # KPI
    def kpi(val, lbl, col):
        return Paragraph(
            f'<para align="center"><font size="22" color="{col}"><b>{val}</b></font>'
            f'<br/><font size="8" color="#888888">{lbl}</font></para>', cell_s)

    kpi_data = [[kpi(len(tasks),"Toplam","#1a1a2e"),
                 kpi(len(done), "Tamamlanan","#3fb950"),
                 kpi(len(pending),"Bekleyen","#f85149"),
                 kpi(f"%{rate}","Tamamlanma","#00d4aa")]]
    kt = Table(kpi_data, colWidths=[None]*4)
    kt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),GRAY1), ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),  ("BOX",(0,0),(-1,-1),0.5,GRAY2),
        ("INNERGRID",(0,0),(-1,-1),0.5,GRAY2),
        ("TOPPADDING",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),10),
    ]))
    elems += [kt, Spacer(1,16)]

    def task_table(lst, label, elems=elems):
        if not lst: return
        elems.append(Paragraph(label, h2_s))
        rows = [["#","Görev","Kategori","Firma","Ekip","Tarih","Durum"]]
        for i,t in enumerate(lst,1):
            rows.append([
                str(i),
                Paragraph(t.title[:52]+("…" if len(t.title)>52 else ""), cell_s),
                CAT_LABELS.get(t.category, t.category),
                getattr(t,"firm",""),
                Paragraph((t.team or "")[:20], cell_s),
                str(t.deadline) if t.deadline else "—",
                ("Bu ay yapıldı" if t.category=="routine" and not t.is_done else "Tamam") if _is_done(t) else "Bekliyor"
            ])
        row_bgs = [("BACKGROUND",(0,ri),(-1,ri), GRAY1 if ri%2==0 else colors.white)
                   for ri in range(1, len(rows))]
        clrs = [("TEXTCOLOR",(6,ri),(6,ri), GREEN if lst[ri-1].is_done else RED)
                for ri in range(1, len(rows))]
        tbl = Table(rows, colWidths=[.7*cm,6*cm,2.2*cm,1.8*cm,2.1*cm,2*cm,1.8*cm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),DARK), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),FONT_BOLD), ("FONTNAME",(0,1),(-1,-1),FONT_NORMAL),
            ("FONTSIZE",(0,0),(-1,-1),8), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),5), ("GRID",(0,0),(-1,-1),0.3,GRAY2),
        ] + row_bgs + clrs))
        elems += [tbl, Spacer(1,8)]

    task_table(done,    f"Tamamlanan Görevler ({len(done)})")
    task_table(pending, f"Bekleyen Görevler ({len(pending)})")

    backups = [t for t in tasks if t.category=="backup"]
    if backups:
        elems.append(Paragraph(f"Config Backup ({len(backups)})", h2_s))
        brows = [["Görev","Firma","Ekip","Durum"]]
        for t in backups:
            brows.append([Paragraph(t.title[:55], cell_s), getattr(t,"firm",""),
                          (t.team or "")[:20], "Tamam" if t.is_done else "Bekliyor"])
        bt = Table(brows, colWidths=[8*cm,2.5*cm,3*cm,2*cm], repeatRows=1)
        bt.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),DARK), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),FONT_BOLD), ("FONTNAME",(0,1),(-1,-1),FONT_NORMAL),
            ("FONTSIZE",(0,0),(-1,-1),8), ("GRID",(0,0),(-1,-1),0.3,GRAY2),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ]))
        elems += [bt, Spacer(1,8)]

    elems.append(Spacer(1,20))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=GRAY2))
    elems.append(Paragraph(
        f"IT Görev Takip Sistemi  |  Oluşturulma: {date.today().strftime('%d.%m.%Y')}",
        footer_s))
    doc.build(elems)
