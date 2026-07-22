"""
test_mail_suppress.py — v5.25 — MAIL_SUPPRESS ile gerçek gönderimin kapatılması.

Staging/test ortamında MAIL_SUPPRESS=1 iken hiçbir gönderim fonksiyonu SMTP'ye
bağlanmaz; {"ok": True, "suppressed": True} döner (bounce üretmez).
"""

from services import mailer


def test_suppress_case_ack(monkeypatch):
    monkeypatch.setenv("MAIL_SUPPRESS", "1")
    # SMTP creds olmasa bile suppress creds kontrolünden ÖNCE devreye girer
    r = mailer.send_case_ack("ahmet@inventist.com.tr", "Ahmet", "INV-TEST01", "Konu", "inventist")
    assert r == {"ok": True, "suppressed": True}


def test_suppress_send_plain(monkeypatch):
    monkeypatch.setenv("MAIL_SUPPRESS", "1")
    r = mailer.send_case_closed("ahmet@inventist.com.tr", "INV-TEST02", "Konu")
    assert r.get("suppressed") is True


def test_not_suppressed_default(monkeypatch):
    # MAIL_SUPPRESS yok/0 → suppress helper None döner (akış normale devam eder).
    monkeypatch.delenv("MAIL_SUPPRESS", raising=False)
    assert mailer._mail_suppressed("x@y.com", "test") is None
    monkeypatch.setenv("MAIL_SUPPRESS", "0")
    assert mailer._mail_suppressed("x@y.com", "test") is None


def test_suppressed_no_smtp_needed(monkeypatch):
    # Suppress açıkken SMTP env'i tamamen boş olsa da hata olmadan döner.
    monkeypatch.setenv("MAIL_SUPPRESS", "1")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    r = mailer.send_case_reply_notice("ahmet@inventist.com.tr", "INV-TEST03", "Konu")
    assert r.get("suppressed") is True
