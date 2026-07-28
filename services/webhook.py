"""Webhook bildirimleri v1 (v5.32) — Microsoft Teams Incoming Webhook.

Teams kanalına MessageCard gönderir (yeni destek talebi vb.). Webhook URL'i
SystemSetting (teams_webhook_url) ya da TEAMS_WEBHOOK_URL env'inden okunur.

GÜVENLİK: MAIL_SUPPRESS=1 ise (test/staging) GERÇEK POST yapılmaz — yalnız loglar.
URL yoksa sessizce atlanır (özellik kapalı). Böylece testler ve staging gerçek
Teams kanalına mesaj atmaz (mail bounce olayının webhook muadili önlenir).
"""

import json
import os
import urllib.request


def _teams_url():
    """Webhook URL — önce DB ayarı (SystemSetting), sonra env fallback."""
    try:
        from models.database import get_setting

        val = (get_setting("teams_webhook_url", "") or "").strip()
        if val:
            return val
    except Exception:
        pass
    return (os.environ.get("TEAMS_WEBHOOK_URL") or "").strip()


def teams_enabled():
    """Teams bildirimi yapılandırılmış mı? (URL var + suppress değil)."""
    if os.environ.get("MAIL_SUPPRESS", "0") == "1":
        return False
    return bool(_teams_url())


def notify_teams(title, text="", facts=None, color="0076D7"):
    """Teams'e MessageCard gönderir. Suppress/URL-yok durumunda güvenle atlar.

    facts: [(ad, deger), ...] — kartta anahtar-değer satırları.
    """
    if os.environ.get("MAIL_SUPPRESS", "0") == "1":
        print(f"[teams:SUPPRESSED] {title}")
        return {"ok": True, "suppressed": True}
    url = _teams_url()
    if not url:
        return {"ok": False, "error": "TEAMS_WEBHOOK_URL / teams_webhook_url ayarlı değil"}
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "sections": [
            {
                "activityTitle": title,
                "text": text or "",
                "facts": [{"name": str(k), "value": str(v)} for k, v in (facts or [])],
                "markdown": True,
            }
        ],
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(card).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
        return {"ok": ok, "status": resp.status}
    except Exception as e:
        print(f"[teams] gönderim hatası: {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)}
