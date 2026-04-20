"""Mail Servisi v2 — Rapor maili + kullanıcı davet maili"""
import os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

MONTH_TR = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",
            7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}

def _smtp():
    host = os.environ.get("SMTP_HOST","smtp.office365.com")
    port = int(os.environ.get("SMTP_PORT",587))
    user = os.environ.get("SMTP_USER")
    pw   = os.environ.get("SMTP_PASS")
    return host, port, user, pw

def send_report_email(user, pdf_path, month, year, cc=None, o365_token=None):
    host,port,smtp_user,smtp_pass = _smtp()
    if not smtp_user or not smtp_pass:
        return {"ok":False,"error":"SMTP ayarları eksik — Ayarlar > SMTP bölümünden kullanıcı adı ve şifre girin"}
    if not os.path.exists(pdf_path):
        return {"ok":False,"error":f"PDF dosyası oluşturulamadı: {pdf_path} — weasyprint veya reportlab kurulu mu?"}
    subject = f"IT Görev Raporu – {MONTH_TR[month]} {year} – {user.full_name}"
    body    = f"Merhaba {user.full_name},\n\n{MONTH_TR[month]} {year} raporunuz ekte.\n\nIT Görev Takip Sistemi"
    msg = MIMEMultipart(); msg["From"]=smtp_user; msg["To"]=user.email; msg["Subject"]=subject
    if cc: msg["Cc"]=cc
    msg.attach(MIMEText(body,"plain","utf-8"))
    try:
        with open(pdf_path,"rb") as f:
            part=MIMEBase("application","octet-stream"); part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",f'attachment; filename="{os.path.basename(pdf_path)}"')
        msg.attach(part)
    except Exception as e:
        return {"ok":False,"error":f"PDF eklenemedi: {str(e)}"}
    import ssl
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [user.email]+([cc] if cc else []), msg.as_string())
        return {"ok":True,"message":f"Rapor {user.email} adresine gönderildi"}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok":False,"error":f"Kimlik doğrulama hatası — SMTP şifresi yanlış veya hesap için App Password gerekiyor olabilir. ({str(e)})"}
    except smtplib.SMTPConnectError as e:
        return {"ok":False,"error":f"Sunucuya bağlanılamadı: {host}:{port} — host/port ayarlarını kontrol edin. ({str(e)})"}
    except smtplib.SMTPRecipientsRefused as e:
        return {"ok":False,"error":f"Alıcı adresi reddedildi: {str(e)}"}
    except smtplib.SMTPException as e:
        return {"ok":False,"error":f"SMTP hatası: {str(e)}"}
    except OSError as e:
        return {"ok":False,"error":f"Ağ hatası: {host}:{port} adresine ulaşılamıyor. ({str(e)})"}

def send_alarm_digest(user, groups):
    """v4.6 — Bildirim özeti maili.
    groups: dict — {"overdue": [task_dict,...], "sla_warning": [...], "sla_breached": [...]}
    task_dict minimum: {id, title, firm, team, days_late, priority, sla_remaining_hours}
    """
    host,port,smtp_user,smtp_pass = _smtp()
    if not smtp_user or not smtp_pass:
        return {"ok":False,"error":"SMTP ayarları eksik"}

    overdue     = groups.get("overdue") or []
    sla_warning = groups.get("sla_warning") or []
    sla_breach  = groups.get("sla_breached") or []

    total = len(overdue) + len(sla_warning) + len(sla_breach)
    if total == 0:
        return {"ok":True,"skipped":True,"message":"Bildirilecek görev yok"}

    subject = f"IT Tracker — {total} bildirim ({user.full_name})"

    parts = [f"Merhaba {user.full_name},", "",
             f"Bugünkü görev özetiniz aşağıdadır (toplam {total} uyarı).", ""]

    def _fmt_task(t, kind="overdue"):
        firm_team = " / ".join(x for x in [t.get("firm") or "", t.get("team") or ""] if x)
        prefix = f"[{t.get('priority','orta').upper()}]" if t.get("priority") else ""
        if kind == "overdue":
            return f"  - #{t['id']} {prefix} {t['title']} — {t.get('days_late','?')} gün gecikmeli" + (f" ({firm_team})" if firm_team else "")
        if kind == "sla_warning":
            rh = t.get("sla_remaining_hours")
            rem = f"{rh:.1f} saat kaldı" if isinstance(rh, (int,float)) else "süresi azaldı"
            return f"  - #{t['id']} {prefix} {t['title']} — SLA: {rem}" + (f" ({firm_team})" if firm_team else "")
        if kind == "sla_breached":
            return f"  - #{t['id']} {prefix} {t['title']} — SLA AŞILDI" + (f" ({firm_team})" if firm_team else "")
        return f"  - #{t['id']} {t['title']}"

    if overdue:
        parts.append(f"3+ gün geciken görevler ({len(overdue)}):")
        parts += [_fmt_task(t, "overdue") for t in overdue]
        parts.append("")
    if sla_breach:
        parts.append(f"SLA aşan destek talepleri ({len(sla_breach)}):")
        parts += [_fmt_task(t, "sla_breached") for t in sla_breach]
        parts.append("")
    if sla_warning:
        parts.append(f"SLA'sı yaklaşan destek talepleri ({len(sla_warning)}):")
        parts += [_fmt_task(t, "sla_warning") for t in sla_warning]
        parts.append("")

    parts += ["—", "IT Görev Takip Sistemi", "https://ittracker.inventist.com.tr"]
    body = "\n".join(parts)

    msg = MIMEMultipart(); msg["From"]=smtp_user; msg["To"]=user.email; msg["Subject"]=subject
    msg.attach(MIMEText(body,"plain","utf-8"))
    import ssl
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo(); s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [user.email], msg.as_string())
        return {"ok":True,"count":total,"message":f"Bildirim {user.email} adresine gönderildi"}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok":False,"error":f"Kimlik doğrulama hatası: {str(e)}"}
    except Exception as e:
        return {"ok":False,"error":f"{type(e).__name__}: {str(e)}"}


def send_invite_email(email, name, invite_url, role):
    host,port,smtp_user,smtp_pass = _smtp()
    if not smtp_user or not smtp_pass:
        return {"ok":False,"error":"SMTP ayarları eksik"}
    subject = "IT Görev Takip Sistemi — Davet"
    body = f"""Merhaba{' '+name if name else ''},

IT Görev Takip Sistemine "{role}" rolüyle davet edildiniz.

Hesabınızı oluşturmak için aşağıdaki bağlantıyı kullanın (7 gün geçerli):

{invite_url}

Aynı zamanda Microsoft 365 hesabınızla da giriş yapabilirsiniz.

IT Ekibi"""
    msg = MIMEMultipart(); msg["From"]=smtp_user; msg["To"]=email; msg["Subject"]=subject
    msg.attach(MIMEText(body,"plain","utf-8"))
    import ssl
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo(); s.login(smtp_user,smtp_pass)
            s.sendmail(smtp_user,[email],msg.as_string())
        return {"ok":True}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok":False,"error":f"Kimlik doğrulama hatası: {str(e)}"}
    except Exception as e:
        return {"ok":False,"error":f"{type(e).__name__}: {str(e)}"}
