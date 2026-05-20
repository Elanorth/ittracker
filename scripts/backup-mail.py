#!/usr/bin/env python3
"""IT Tracker yedek hatasi bildirimi.

Kullanim: backup-mail.py "<konu>" "<govde>"

Prod .env'den SMTP_HOST/PORT/USER/PASS okur, admin@inventist.com.tr'ye yollar.
Sessiz hata (mail gonderemese bile script bozulmaz).
"""
import sys
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

ENV_FILE = Path("/home/leventcan/ittracker/.env")
TO_ADDR = "admin@inventist.com.tr"


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: backup-mail.py <subject> <body>", file=sys.stderr)
        return 2

    subject, body = sys.argv[1], sys.argv[2]
    env = load_env(ENV_FILE)

    host = env.get("SMTP_HOST") or os.environ.get("SMTP_HOST")
    port = int(env.get("SMTP_PORT") or os.environ.get("SMTP_PORT") or "587")
    user = env.get("SMTP_USER") or os.environ.get("SMTP_USER")
    pwd = env.get("SMTP_PASS") or os.environ.get("SMTP_PASS")

    if not all([host, user, pwd]):
        print("SMTP config eksik", file=sys.stderr)
        return 1

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = TO_ADDR
    msg.set_content(body + "\n\n--\nIT Tracker backup script (10.34.0.62)")

    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.send_message(msg)
        print(f"mail gonderildi: {TO_ADDR}")
        return 0
    except Exception as exc:
        print(f"mail HATA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
