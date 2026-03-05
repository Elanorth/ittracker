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
