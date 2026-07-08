"""
IT Görev Takip Sistemi — Flask Backend v2
Yenilikler: O365 OAuth2, çok kullanıcı, davet sistemi, Config Backup, Admin Panel
"""

import os

from dotenv import load_dotenv

load_dotenv()
import csv as _csv
import io as _io
import json as _json
import re as _re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

from models.database import (
    SLA_HOURS,
    AuditLog,
    BoardCard,
    BoardComment,
    CaseMessage,
    ConfigBackup,
    Firm,
    Invitation,
    Task,
    TaskOccurrence,
    Team,
    User,
    _sla_target_hours,
    business_hours_between,
    db,
    init_db,
    sla_deadline,
)
from services.mailer import send_invite_email, send_report_email
from services.notifier import collect_user_alerts, run_breach_check, run_digest_job
from services.report import generate_monthly_pdf
from services.storage import save_backup_file

try:
    import msal

    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False


# === Uygulama versiyonu — TEK KAYNAK: VERSION dosyası ===
# Versiyon string'i artık templates/app.html ve static/sw.js içinde hardcoded
# DEĞİL — VERSION dosyasından okunur ve Flask tarafından inject edilir. Böylece
# her sürümde tek dosya değişir; develop→main merge'lerinde tekrarlayan versiyon
# satırı çakışması (sw.js + app.html) ortadan kalkar.
def _read_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as _vf:
            return _vf.read().strip() or "0.0"
    except OSError:
        return os.environ.get("APP_VERSION", "0.0")


APP_VERSION = _read_version()

# === Sentry / Glitchtip error tracking ===
# GLITCHTIP_DSN env var varsa etkinleşir; yoksa sessizce atlanır.
_SENTRY_DSN = os.environ.get("GLITCHTIP_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,  # %10 performans izleme
            environment=os.environ.get("APP_ENV", "production"),
            release=f"v{APP_VERSION}",
        )
    except Exception:
        pass  # sentry_sdk yoksa veya init başarısız olursa uygulamayı durdurma

app = Flask(__name__)
# SECRET_KEY zorunlu — sabit fallback ile oturum çerezleri sahtelenebilirdi.
# Yalnızca FLASK_DEBUG=1 (yerel geliştirme) iken sabit dev anahtarına düşer;
# prod/staging'de eksikse uygulama ADMIN_PASSWORD gibi açık hatayla durur.
_secret_key = os.environ.get("SECRET_KEY", "")
if not _secret_key:
    if os.environ.get("FLASK_DEBUG", "0") == "1":
        _secret_key = "dev-secret-change-in-prod"  # pragma: allowlist secret
    else:
        raise RuntimeError("SECRET_KEY ortam değişkeni ayarlanmamış! .env dosyasını kontrol edin.")
app.secret_key = _secret_key

# Nginx reverse proxy arkasında HTTPS ve gerçek IP'yi doğru al
from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///it_tracker.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# === Oturum çerezi sertleştirme ===
# HttpOnly: JS çerezi okuyamaz (XSS ile oturum çalınmasını zorlaştırır).
# SameSite=Lax: çerez cross-site POST/fetch ile gönderilmez → CSRF'i büyük ölçüde
#   azaltır (state değiştiren tüm endpoint'ler POST/PATCH/DELETE). JSON API zaten
#   cross-origin basit form ile taklit edilemez (Content-Type: application/json).
# Secure: çerez yalnızca HTTPS üzerinde gönderilir. Prod/staging nginx TLS arkasında;
#   varsayılan açık. HTTP test/dev için SESSION_COOKIE_SECURE=0 ile kapatılabilir.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"

O365_CLIENT_ID = os.environ.get("O365_CLIENT_ID", "")
O365_CLIENT_SECRET = os.environ.get("O365_CLIENT_SECRET", "")
O365_TENANT_ID = os.environ.get("O365_TENANT_ID", "common")
O365_REDIRECT_URI = os.environ.get("O365_REDIRECT_URI", "http://localhost:5000/auth/callback")
O365_SCOPES = ["User.Read", "Mail.Send"]

db.init_app(app)

# Alembic / Flask-Migrate — `flask db <komut>` CLI'sini etkinleştirir.
# Schema değişiklikleri artık migrations/versions/ altında revision olarak yönetilir.
# init_db() mevcut idempotent ALTER mantığı korunur (CI test ve fresh install için).
# Bkz: docs/alembic-migrations.md
from flask_migrate import Migrate

migrate = Migrate(app, db, directory="migrations", render_as_batch=True)

ALLOWED_PRIORITIES = {"düşük", "orta", "yüksek"}


def _normalize_priority(val):
    v = (val or "").strip().lower()
    return v if v in ALLOWED_PRIORITIES else "orta"


# Türkçe-uyumlu küçük harf/slug haritası: Python `.lower()` 'İ' → 'i̇' (i + combining dot)
# döndürür ve slug'larda hayalet karakter bırakır. Aşağıdaki tablo Türkçe karakterleri
# slug-safe ASCII'ye eşler.
_TR_SLUG_MAP = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ş": "s",
        "ş": "s",
        "Ğ": "g",
        "ğ": "g",
        "Ü": "u",
        "ü": "u",
        "Ö": "o",
        "ö": "o",
        "Ç": "c",
        "ç": "c",
    }
)


def _slugify_tr(s):
    """Türkçe-aware slug üretimi.

    Örnek: 'İnventist' → 'inventist', 'Şirket Çağ' → 'sirket_cag'
    Saf `.lower().replace(" ","_")` 'İnventist' için 'i̇nventist' üretir
    (combining dot above) — slug bozulur. Bu helper Türkçe harfleri ASCII
    karşılıklarına eşler ve sonra slug'lar.
    """
    if not s:
        return ""
    return s.translate(_TR_SLUG_MAP).lower().strip().replace(" ", "_")


def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if "user_id" not in session:
            # API path veya JSON Accept/Content-Type → JSON 401 dön (302 redirect değil).
            # Frontend fetch() çağrılarının redirect'ten dolayı opaque/HTML cevap almaması için.
            wants_json = (
                request.is_json
                or request.path.startswith("/api/")
                or "application/json" in request.headers.get("Accept", "")
            )
            if wants_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return dec


def admin_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or not user.is_admin:
            return jsonify({"error": "Yetkisiz"}), 403
        return f(*args, **kwargs)

    return login_required(dec)


def manager_required(f):
    """IT Yöneticisi veya Super Admin gerektirir"""

    @wraps(f)
    def dec(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or not user.is_manager_or_above:
            return jsonify({"error": "Yetkisiz"}), 403
        return f(*args, **kwargs)

    return login_required(dec)


def director_required(f):
    """IT Müdürü veya Super Admin gerektirir (firma bazlı geniş erişim)"""

    @wraps(f)
    def dec(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or not user.is_director_or_above:
            return jsonify({"error": "Yetkisiz"}), 403
        return f(*args, **kwargs)

    return login_required(dec)


def super_admin_required(f):
    """Sadece Super Admin gerektirir"""

    @wraps(f)
    def dec(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or not user.is_super_admin:
            return jsonify({"error": "Yetkisiz"}), 403
        return f(*args, **kwargs)

    return login_required(dec)


def board_access_required(f):
    """Ortak Alan erişimi: can_access_board veya super_admin"""

    @wraps(f)
    def dec(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or (not user.can_access_board and not user.is_super_admin):
            return jsonify({"error": "Ortak Alan erisiminiz yok"}), 403
        return f(*args, **kwargs)

    return login_required(dec)


def _current_user():
    """Yardımcı: mevcut kullanıcıyı döndürür"""
    return db.session.get(User, session.get("user_id"))


def _csv_response(filename, header, rows):
    """v5.14 — UTF-8 BOM + ';' ayraçlı CSV yanıtı (TR Excel uyumlu).

    Excel Türkçe locale'de virgülü ondalık ayırıcı sayar; sütunların düzgün
    ayrılması için ';' kullanılır. BOM olmadan Türkçe karakterler Excel'de bozuk
    görünür (mojibake) → başa '﻿' eklenir.
    """
    buf = _io.StringIO()
    buf.write("﻿")
    writer = _csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for r in rows:
        writer.writerow(["" if c is None else c for c in r])
    resp = app.response_class(buf.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


def log_audit(actor, action, *, entity_type="", entity_id=None, target_user=None, firm="", summary="", details=None):
    """v4.4 — denetim kaydı oluşturur. Hata fırlatmaz; log sessizce atılır.
    commit yapılmaz — çağıran yerin db.session.commit() ile birlikte kaydeder."""
    try:
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            actor_name=(actor.full_name if actor else "") or (actor.username if actor else ""),
            action=action,
            entity_type=entity_type or "",
            entity_id=entity_id,
            target_user_id=target_user.id if target_user else None,
            target_name=(target_user.full_name if target_user else "") or (target_user.username if target_user else ""),
            firm=firm or (actor.firm if actor else ""),
            summary=(summary or "")[:500],
            details=_json.dumps(details) if details else "",
        )
        db.session.add(entry)
    except Exception as e:
        print(f"[audit] log hatası: {e}")


def _resolve_scope_uid(me, requested_uid):
    """
    v4.2 — firma bazlı kapsam çözümleyici.
    v4.9 — it_director için managed_firms (çoklu firma yönetimi) desteği eklendi.
    - requested_uid yoksa: kendi id'si
    - requested_uid == kendi id'si: kendi id'si
    - super_admin: herkesin id'sini kullanabilir
    - it_director: yönettiği herhangi bir firmadaki (managed_firms slug'larında
      VEYA kendi firm'inde — geriye dönük) aktif kullanıcıların id'si
    - diğerleri: başka kullanıcı görüntüleyemez (kendi id'si)
    Dönüş: (uid, error_tuple_or_None)
    """
    if not requested_uid or int(requested_uid) == me.id:
        return me.id, None
    target = db.session.get(User, int(requested_uid))
    if not target or not target.active:
        return None, (jsonify({"error": "Kullanıcı bulunamadı"}), 404)
    if me.is_super_admin:
        return target.id, None
    if me.permission_level == "it_director" and me.has_firm_scope(target.firm):
        return target.id, None
    return None, (jsonify({"error": "Bu kullanıcının verilerine erişim yetkiniz yok"}), 403)


def _can_modify_owned_task(me, owner):
    """Görev sahibi olmayan biri o görevi düzenleyebilir/silebilir mi?

    F2.3 fix: super_admin her görevi; it_director ise YÖNETTİĞİ herhangi bir
    firmadaki (has_firm_scope — managed_firms + kendi firma'sı) görevi. Eski kod
    `owner.firm == me.firm` ile yalnızca kendi firma'sını kapsıyordu → çoklu firma
    yöneten director ikinci firmayı görür ama düzenleyemezdi. update_task,
    delete_task ve update_task_alarm aynı kuralı kullanır (tek kaynak).
    """
    return me.is_super_admin or (me.permission_level == "it_director" and owner and me.has_firm_scope(owner.firm))


@app.route("/")
@login_required
def dashboard():
    # version → app.html içinde {{ version }} (title + app.js cache-busting)
    return render_template("app.html", version=APP_VERSION)


@app.route("/sw.js")
def service_worker():
    # sw.js içindeki __VERSION__ placeholder'ı APP_VERSION ile değiştir.
    # Böylece cache anahtarı her sürümde otomatik değişir (eski cache temizlenir).
    sw_path = os.path.join(app.root_path, "static", "sw.js")
    with open(sw_path, encoding="utf-8") as f:
        content = f.read().replace("__VERSION__", APP_VERSION)
    resp = app.response_class(content, mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ── /login brute-force koruması ──
# Basit bellek-içi kayan pencere: (ip, username) başına 15 dakikada 5 başarısız
# deneme → 429. gunicorn tek worker (bkz. Dockerfile) olduğu için process-yerel
# sözlük yeterli; worker sayısı artarsa paylaşımlı store (redis vb.) gerekir.
_LOGIN_FAILS: dict = {}
_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW_SEC = 900


def _login_rate_limited(ip, username):
    import time as _time

    key = (ip, username)
    stamps = _LOGIN_FAILS.get(key)
    if not stamps:
        return False
    now = _time.time()
    stamps[:] = [t for t in stamps if now - t < _LOGIN_WINDOW_SEC]
    if not stamps:
        _LOGIN_FAILS.pop(key, None)
        return False
    return len(stamps) >= _LOGIN_MAX_FAILS


def _register_login_fail(ip, username):
    import time as _time

    # Sınırsız büyümeyi engelle: kaba tavan — eski kayıtları topluca at
    if len(_LOGIN_FAILS) > 1000:
        _LOGIN_FAILS.clear()
    _LOGIN_FAILS.setdefault((ip, username), []).append(_time.time())


@app.after_request
def _security_headers(resp):
    """Temel güvenlik başlıkları. CSP bilinçli olarak YOK — arayüz inline
    onclick/style kullanıyor; CSP ancak app.js event-listener refactor'ından
    sonra eklenebilir."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        username = (data.get("username") or "").strip().lower()
        password = data.get("password") or ""
        client_ip = request.remote_addr or "?"
        if _login_rate_limited(client_ip, username):
            msg = "Çok fazla başarısız deneme — 15 dakika sonra tekrar deneyin"
            if request.is_json:
                return jsonify({"ok": False, "error": msg}), 429
            return render_template("login.html", admin_mode=True, error=msg), 429
        # Sadece admin kullanıcı local girişe izin verilir.
        # ALLOW_DEMO_LOGIN=1 ortam değişkeni varsa `demo_` prefix'li kullanıcılar da
        # password ile girebilir — sadece staging için (prod .env'de açılmamalı).
        # Önceden bu, her deploy sonrası container'a manuel hot-patch ile yapılıyordu.
        admin_username = os.environ.get("ADMIN_USERNAME", "levent.can")
        allow_demo = os.environ.get("ALLOW_DEMO_LOGIN", "").lower() in ("1", "true", "yes")
        is_demo_user = allow_demo and username.startswith("demo_")
        if username != admin_username and not is_demo_user:
            _register_login_fail(client_ip, username)
            if request.is_json:
                return jsonify({"ok": False, "error": "Lütfen Microsoft 365 ile giriş yapın"}), 403
            return render_template(
                "login.html", admin_mode=True, error="Bu kullanıcı için Microsoft 365 ile giriş gereklidir"
            )
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            _LOGIN_FAILS.pop((client_ip, username), None)  # başarılı giriş sayacı sıfırlar
            session["user_id"] = user.id
            if request.is_json:
                return jsonify({"ok": True, "user": user.to_dict()})
            return redirect(url_for("dashboard"))
        _register_login_fail(client_ip, username)
        if request.is_json:
            return jsonify({"ok": False, "error": "Hatalı kullanıcı adı veya şifre"}), 401
        return render_template("login.html", admin_mode=True, error="Hatalı kullanıcı adı veya şifre")
    admin_mode = request.args.get("admin") == "1"
    return render_template("login.html", admin_mode=admin_mode)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── O365 OAUTH ──
@app.route("/auth/o365")
def auth_o365():
    if not MSAL_AVAILABLE:
        return jsonify({"error": "pip install msal"}), 503
    # Davet token'ını session'a kaydet (register sayfasından geliyorsa)
    invite_token = request.args.get("invite")
    if invite_token:
        session["invite_token"] = invite_token
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    msal_app = msal.ConfidentialClientApplication(
        O365_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{O365_TENANT_ID}",
        client_credential=O365_CLIENT_SECRET,
    )
    return redirect(msal_app.get_authorization_request_url(O365_SCOPES, state=state, redirect_uri=O365_REDIRECT_URI))


@app.route("/auth/callback")
def auth_callback():
    if not MSAL_AVAILABLE:
        return "MSAL yok", 503
    code = request.args.get("code")
    if request.args.get("state") != session.pop("oauth_state", None):
        return "Geçersiz state", 400
    msal_app = msal.ConfidentialClientApplication(
        O365_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{O365_TENANT_ID}",
        client_credential=O365_CLIENT_SECRET,
    )
    result = msal_app.acquire_token_by_authorization_code(code, scopes=O365_SCOPES, redirect_uri=O365_REDIRECT_URI)
    if "error" in result:
        return f"Hata: {result.get('error_description', '')}", 400
    claims = result.get("id_token_claims", {})
    o365_id = claims.get("oid")
    email = claims.get("preferred_username", "").lower()
    name = claims.get("name", email)

    admin_email = os.environ.get("ADMIN_EMAIL", "").lower()

    # Mevcut kullanıcı kontrolü (o365_id veya email ile)
    user = User.query.filter_by(o365_id=o365_id).first() or User.query.filter_by(email=email).first()

    if not user:
        # Yeni kullanıcı — davet zorunlu (admin hariç)
        invite_token = session.pop("invite_token", None)
        inv = None
        if invite_token:
            inv = Invitation.query.filter_by(token=invite_token, used=False).first()
        if not inv:
            inv = Invitation.query.filter_by(email=email, used=False).first()

        if not inv and email != admin_email:
            return render_template(
                "error.html",
                msg=f"'{email}' adresi için geçerli bir davet bulunamadı. Lütfen sistem yöneticinizden davet isteyin.",
            )

        role = inv.role if inv else "IT Sorumlusu"
        firm = inv.firm if inv else ""
        # Permission level: role_label'dan türet
        perm_map = {
            "Super Admin": "super_admin",
            "IT Müdürü": "it_director",
            "IT Yöneticisi": "it_manager",
            "IT Specialist": "it_specialist",
            "Junior": "junior",
        }
        perm = perm_map.get(role, "junior")
        user = User(
            username=email.split("@")[0].lower(),
            full_name=name,
            email=email,
            o365_id=o365_id,
            role=role,
            firm=firm,
            permission_level=perm,
            is_admin=perm in ("super_admin", "it_director", "it_manager"),
        )
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        if inv:
            inv.used = True
        db.session.commit()
    else:
        # Mevcut kullanıcı — o365_id ve ad güncelle
        user.o365_id = o365_id
        user.full_name = name
        db.session.commit()

    session["user_id"] = user.id
    session["o365_token"] = result.get("access_token")
    session.pop("invite_token", None)
    return redirect(url_for("dashboard"))


# ── FIRM USERS (v4.2 — director+) ──
@app.route("/api/firm/users")
@login_required
def firm_users():
    """Director+ için firma bazlı kullanıcı listesi (dashboard dropdown).

    v4.9 — it_director için yönettiği TÜM firmaların kullanıcıları döner
    (managed_firms slug listesi + geriye dönük olarak kendi firm'i).
    """
    me = _current_user()
    if not me:
        return jsonify({"error": "Unauthorized"}), 401
    # Sadece director+ bu listeyi çeker; diğerleri sadece kendilerini görür
    if me.is_super_admin:
        q = User.query.filter_by(active=True).order_by(User.full_name)
    elif me.permission_level == "it_director":
        # v4.9 — managed_firms kapsamı (kendi firm'i her zaman dahil)
        scope_slugs = set(me.managed_firm_slugs)
        if me.firm:
            scope_slugs.add(me.firm)
        q = User.query.filter(User.active == True, User.firm.in_(list(scope_slugs))).order_by(User.full_name)
    else:
        return jsonify([{"id": me.id, "full_name": me.full_name, "firm": me.firm}])
    return jsonify(
        [
            {
                "id": u.id,
                "full_name": u.full_name,
                "firm": u.firm,
                "role": u.role,
                "permission_level": u.permission_level,
            }
            for u in q.all()
        ]
    )


# ── Firma dashboard'ları için N+1 önleyici yardımcılar ──
# dashboard_firm_summary / managed_firms_detail eskiden her görev için
# is_done_now/is_overdue_now çağırıp TaskOccurrence sorguluyordu (firma×görev,
# trend'de ayrıca ×6 = ağır N+1). Aşağıdaki ön-yükleme firma başına TEK sorgu yapar.
def _preload_routine_occurrences(tasks):
    """Verilen görevlerin rutin occurrence period_key'lerini tek sorguda yükler → {task_id: set(period_key)}."""
    routine_ids = [t.id for t in tasks if t.category == "routine" and t.period != "Tek Seferlik"]
    occ_map = {}
    if routine_ids:
        for occ in TaskOccurrence.query.filter(TaskOccurrence.task_id.in_(routine_ids)).all():
            occ_map.setdefault(occ.task_id, set()).add(occ.period_key)
    return occ_map


def _task_done_at(t, day, occ_map):
    """Task.is_done_now'ın ön-yüklenmiş occ_map ile çağrısı (ek sorgu yok).

    Kanonik tanım artık TEK yerde: models.database.Task.is_done_now. Bu sarmalayıcı
    yalnızca occ_map[task_id] → occ_set adaptasyonunu yapar (N+1 önler).
    """
    return t.is_done_now(today=day, occ_set=occ_map.get(t.id, set()))


def _task_overdue_at(t, day, occ_map):
    """Task.is_overdue_now'ın ön-yüklenmiş occ_map ile çağrısı (ek sorgu yok)."""
    return t.is_overdue_now(today=day, occ_set=occ_map.get(t.id, set()))


# v4.9 — Dashboard firma şeridi için aggregated özet endpoint'i.
# IT Müdürü yönettiği her firma için tek satırlık özet (total/done/overdue/rate/sla_breach) alır.
@app.route("/api/dashboard/firm-summary")
@director_required
def dashboard_firm_summary():
    """v4.9 — IT Müdürü dashboard şeridi için her yönetilen firma özeti.

    Response: [{firm, slug, name, total, done, overdue, rate, sla_breach}, ...]
    Sıralama: tamamlanma oranı azalan (en sorunlu firma altta görünür).
    Pratik karar: rutin görevlerde Task.is_done flag kullanılır (TaskCompletion
    sorgusu N+1 maliyeti yaratır; şerit canlı snapshot, raporlama için /api/stats var).
    SLA breach yalnızca açık (is_done=False) destek talepleri için sayılır.
    """
    me = _current_user()
    if me.is_super_admin:
        firms = Firm.query.order_by(Firm.name).all()
    else:
        # it_director: yönettiği firmalar + kendi firma'sı (geriye dönük)
        scope_slugs = set(me.managed_firm_slugs)
        if me.firm:
            scope_slugs.add(me.firm)
        if not scope_slugs:
            return jsonify([])
        firms = Firm.query.filter(Firm.slug.in_(list(scope_slugs))).order_by(Firm.name).all()

    today = date.today()
    now = datetime.utcnow()
    summary = []
    for f in firms:
        tasks = Task.query.filter(Task.firm == f.slug).all()
        total = len(tasks)
        # v5.0 — rutin görevler için period_key bazlı anlık tamamlanma/gecikme (N+1 önlemeli)
        occ_map = _preload_routine_occurrences(tasks)
        done = sum(1 for t in tasks if _task_done_at(t, today, occ_map))
        overdue = sum(1 for t in tasks if _task_overdue_at(t, today, occ_map))
        rate = round((done / total) * 100) if total else 0
        # SLA ihlali — açık destek talepleri için (resolved değil, iş-saati deadline geçmiş)
        sla_breach = 0
        for t in tasks:
            if t.category != "support" or t.is_done or not t.created_at:
                continue
            deadline_dt = sla_deadline(t.created_at, t.priority)
            if deadline_dt and now > deadline_dt:
                sla_breach += 1
        summary.append(
            {
                "firm": f.slug,
                "slug": f.slug,
                "name": f.name,
                "total": total,
                "done": done,
                "overdue": overdue,
                "rate": rate,
                "sla_breach": sla_breach,
            }
        )
    # En düşük tamamlanma oranı altta (dikkat çekecek olan üstte)
    summary.sort(key=lambda s: s["rate"])
    return jsonify(summary)


# v5.0 — "Yönettiğim Firmalar" sayfası için detaylı endpoint.
# Her yönetilen firma için: KPI + 6 aylık trend + kategori dağılımı + geciken
# top-3 + kullanıcı dağılımı + SLA breach. Sıralama: geciken sayısı azalan
# (en kritik firma üstte).
_TR_MONTHS_SHORT = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
_CAT_LABELS = {
    "routine": "Rutin",
    "support": "Destek",
    "infra": "Altyapı",
    "backup": "Backup",
    "project": "Proje",
    "task": "Anlık",
    "other": "Diğer",
}


@app.route("/api/managed-firms/detail")
@director_required
def managed_firms_detail():
    """v5.0 — Yönettiğim Firmalar sayfası ana endpoint'i.

    Query: period=1m|3m|1y (default 1m) — kategori dağılımı + trend için.
    KPI/SLA breach periyot bağımsız (anlık durum).

    super_admin: tüm firmalar.
    it_director: managed_firms + kendi firma'sı (geriye dönük).
    """
    me = _current_user()
    period = request.args.get("period", "1m")
    months_back_for_cat = {"1m": 1, "3m": 3, "1y": 12}.get(period, 1)

    if me.is_super_admin:
        firms = Firm.query.order_by(Firm.name).all()
    else:
        scope_slugs = set(me.managed_firm_slugs)
        if me.firm:
            scope_slugs.add(me.firm)
        if not scope_slugs:
            return jsonify([])
        firms = Firm.query.filter(Firm.slug.in_(list(scope_slugs))).order_by(Firm.name).all()

    today = date.today()
    now = datetime.utcnow()
    period_start = today - timedelta(days=30 * months_back_for_cat)

    result = []
    for f in firms:
        all_tasks = Task.query.filter(Task.firm == f.slug).all()
        occ_map = _preload_routine_occurrences(all_tasks)

        # KPI — anlık durum, periyot bağımsız (v5.0: rutin için period_key bazlı, N+1 önlemeli)
        total = len(all_tasks)
        done = sum(1 for t in all_tasks if _task_done_at(t, today, occ_map))
        overdue = sum(1 for t in all_tasks if _task_overdue_at(t, today, occ_map))
        rate = round((done / total) * 100) if total else 0

        # SLA ihlali — açık destek talepleri (iş-saati bazlı)
        sla_breach = 0
        for t in all_tasks:
            if t.category != "support" or t.is_done or not t.created_at:
                continue
            deadline_dt = sla_deadline(t.created_at, t.priority)
            if deadline_dt and now > deadline_dt:
                sla_breach += 1

        # Trend — son 6 ay (en yaşlı önce, en yeni sonda)
        trend = []
        for i in range(5, -1, -1):
            tm = today.month - i
            ty = today.year
            while tm <= 0:
                tm += 12
                ty -= 1
            month_tasks = [
                t for t in all_tasks if t.created_at and t.created_at.year == ty and t.created_at.month == tm
            ]
            # v5.0 — o ayın 15'i ile is_done_now (rutin period_key bazlı)
            ref_dt = date(ty, tm, 15)
            trend.append(
                {
                    "month": _TR_MONTHS_SHORT[tm - 1],
                    "year": ty,
                    "total": len(month_tasks),
                    "done": sum(1 for t in month_tasks if _task_done_at(t, ref_dt, occ_map)),
                }
            )

        # Kategori dağılımı — periyot içindeki görevler için count
        cat_count = {}
        for t in all_tasks:
            if not t.created_at:
                continue
            if t.created_at.date() < period_start:
                continue
            c = t.category or "other"
            cat_count[c] = cat_count.get(c, 0) + 1
        category_breakdown = [
            {"cat": c, "label": _CAT_LABELS.get(c, c), "count": n}
            for c, n in sorted(cat_count.items(), key=lambda x: -x[1])
        ]

        # Overdue top-3 — KANONİK is_overdue (rutinlerde donmuş deadline değil).
        # Eski kod `not t.is_done and t.deadline < today` idi → rutinler is_done hiç
        # set edilmediği için geçmiş deadline'lı TÜM rutinler yanlışlıkla listeleniyordu.
        overdue_tasks = [t for t in all_tasks if _task_overdue_at(t, today, occ_map)]
        # Deadline'ı olanlar tarihe göre (en kötü önce); rutinler (deadline None) sona.
        overdue_tasks.sort(key=lambda t: t.deadline or date.max)
        overdue_top3 = []
        for t in overdue_tasks[:3]:
            owner = db.session.get(User, t.user_id) if t.user_id else None
            is_routine = t.category == "routine" and t.period != "Tek Seferlik"
            overdue_top3.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    # Rutin: kaç periyot atlandı; diğer: kaç gün gecikti
                    "days_overdue": (today - t.deadline).days if (t.deadline and not is_routine) else None,
                    "overdue_periods": t.overdue_period_count(today=today) if is_routine else None,
                    "period": t.period if is_routine else None,
                    "assigned_to": owner.full_name if owner else "—",
                }
            )

        # Kullanıcı dağılımı — max 8, açık görev sayısına göre azalan.
        # KANONİK tamamlanma (rutinler is_done flag'i kullanmaz → occ_map ile).
        user_stats = {}
        for t in all_tasks:
            if not t.user_id:
                continue
            stats = user_stats.setdefault(t.user_id, {"open": 0, "done": 0})
            if _task_done_at(t, today, occ_map):
                stats["done"] += 1
            else:
                stats["open"] += 1
        users = []
        for uid, stats in user_stats.items():
            u = db.session.get(User, uid)
            if not u:
                continue
            users.append(
                {
                    "id": uid,
                    "full_name": u.full_name,
                    "open_tasks": stats["open"],
                    "done_tasks": stats["done"],
                }
            )
        users.sort(key=lambda u: -u["open_tasks"])
        users = users[:8]

        theme_class = "fc-inv" if f.slug == "inventist" else "fc-assos" if f.slug == "assos" else ""

        result.append(
            {
                "slug": f.slug,
                "name": f.name,
                "theme_class": theme_class,
                "kpi": {"total": total, "done": done, "overdue": overdue, "rate": rate},
                "trend": trend,
                "category_breakdown": category_breakdown,
                "overdue_top3": overdue_top3,
                "users": users,
                "sla_breach_count": sla_breach,
                "last_updated": now.isoformat(),
            }
        )

    # Levent karari (Soru 2 = B): geciken sayisi azalan — kritik ustte
    result.sort(key=lambda r: -r["kpi"]["overdue"])
    return jsonify(result)


# ── TASKS ──
def _collect_tasks_for_month(uid, month, year, firm_filter=None, category_filter=None):
    """Bir kullanıcının verilen ay için GÖRÜNEN görev listesini döndürür (Task objeleri).

    TEK KAYNAK: /api/tasks (get_tasks), /api/report/pdf ve mail raporu artık aynı
    görev kümesini kullanır. Önceki sürümde rapor endpoint'leri görevleri yalnızca
    `created_at` o ay olanlarla filtreliyordu → her ay tekrar eden ve çoğu önceki
    aylarda açılmış RUTİN görevler rapora HİÇ girmiyordu (F2.1 bug'ı). Ekrandaki
    liste ile PDF aynı görevleri göstermeli.

    Kurallar:
      1) routine: hepsi (tamamlanma o aya özel; to_dict period_key ile hesaplar)
      2) project: tamamlanmamışlar her ayda; tamamlanmışlar yalnızca tamamlandıkları ayda
      3) diğer (support/infra/backup/other): o ay created/deadline + carry-over
         (açık & önceki aylarda oluşturulmuş)
    """
    result = []

    # 1) Rutin görevler: her ayın görünümünde listelenir, tamamlanma o aya özel
    if not category_filter or category_filter == "routine":
        rq = Task.query.filter_by(user_id=uid, category="routine")
        if firm_filter:
            rq = rq.filter_by(firm=firm_filter)
        result += rq.order_by(Task.created_at.desc()).all()

    # 2) Proje görevleri: tamamlanmamışlar her ayda görünür;
    #    tamamlanmışlar yalnızca tamamlandıkları ayda görünür
    if not category_filter or category_filter == "project":
        pq = Task.query.filter_by(user_id=uid, category="project")
        if firm_filter:
            pq = pq.filter_by(firm=firm_filter)
        for t in pq.order_by(Task.created_at.desc()).all():
            if not t.is_done:
                result.append(t)
            elif t.completed_at:
                if t.completed_at.month == month and t.completed_at.year == year:
                    result.append(t)

    # 3) Diğer görevler (support, infra, backup, other): o aya ait olanlar
    #    + tamamlanmamış olup önceki aylarda oluşturulmuş görevler (carry-over)
    if not category_filter or category_filter not in ("routine", "project"):
        created_match = db.and_(
            db.extract("month", Task.created_at) == month, db.extract("year", Task.created_at) == year
        )
        deadline_match = db.and_(
            Task.deadline != None,
            db.extract("month", Task.deadline) == month,
            db.extract("year", Task.deadline) == year,
        )
        # Tamamlanmamış ve önceki aylarda oluşturulmuş görevler bir sonraki aya taşınır
        carry_over = db.and_(
            Task.is_done == False,
            db.or_(
                db.extract("year", Task.created_at) < year,
                db.and_(db.extract("year", Task.created_at) == year, db.extract("month", Task.created_at) < month),
            ),
        )
        oq = Task.query.filter(
            Task.user_id == uid,
            Task.category.notin_(["routine", "project"]),
            db.or_(created_match, deadline_match, carry_over),
        )
        if firm_filter:
            oq = oq.filter_by(firm=firm_filter)
        if category_filter:
            oq = oq.filter_by(category=category_filter)
        result += oq.order_by(Task.created_at.desc()).all()

    return result


@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err:
        return err
    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)
    firm_filter = request.args.get("firm")
    category_filter = request.args.get("category")
    result = _collect_tasks_for_month(uid, month, year, firm_filter, category_filter)
    return jsonify([t.to_dict(month=month, year=year) for t in result])


@app.route("/api/tasks/export")
@login_required
def export_tasks_csv():
    """v5.14 — Görev listesini CSV olarak dışa aktarır (ekrandaki ay/filtre ile aynı küme)."""
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err:
        return err
    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)
    firm_filter = request.args.get("firm")
    category_filter = request.args.get("category")
    tasks = _collect_tasks_for_month(uid, month, year, firm_filter, category_filter)
    header = [
        "ID",
        "Başlık",
        "Kategori",
        "Öncelik",
        "Periyot",
        "Firma",
        "Ekip",
        "Durum",
        "Deadline",
        "Oluşturulma",
        "SLA Durumu",
        "SLA Kalan (iş saati)",
    ]
    rows = []
    for t in tasks:
        d = t.to_dict(month=month, year=year)
        sla = d.get("sla")
        sla_status, sla_rem = "", ""
        if sla:
            sla_status = "İhlal" if sla.get("breached") else ("Çözüldü" if d["is_done"] else "Açık")
            if not d["is_done"] and isinstance(sla.get("remaining_hours"), int | float):
                sla_rem = f"{sla['remaining_hours']:.1f}"
        rows.append(
            [
                t.id,
                t.title,
                _CAT_LABELS.get(t.category, t.category),
                t.priority or "",
                t.period or "",
                t.firm or "",
                t.team or "",
                "Tamam" if d["is_done"] else "Bekliyor",
                t.deadline.isoformat() if t.deadline else "",
                t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
                sla_status,
                sla_rem,
            ]
        )
    return _csv_response(f"gorevler_{year}_{month:02d}.csv", header, rows)


@app.route("/api/tasks", methods=["POST"])
@login_required
def create_task():
    # Junior sadece anlık görev oluşturabilir
    me = _current_user()
    if me and me.permission_level == "junior":
        cat = (
            request.form if request.content_type and "multipart" in request.content_type else request.get_json() or {}
        ).get("category", "other")
        if cat in ("routine", "project", "backup"):
            return jsonify({"error": "Bu görev türünü oluşturma yetkiniz yok"}), 403
    if request.content_type and "multipart" in request.content_type:
        data = request.form
        backup_file = request.files.get("backup_file")
    else:
        data = request.get_json()
        backup_file = None
    # v4.3 — atama: director+ başka kullanıcıya görev oluşturabilir
    target_uid, err = _resolve_scope_uid(me, data.get("user_id"))
    if err:
        return err
    assigned_by = me.id if target_uid != me.id else None
    # manager_note yalnızca director+ tarafından atanabilir
    manager_note = (data.get("manager_note", "") or "").strip() if me.is_director_or_above else ""
    category = data.get("category", "other")
    priority = _normalize_priority(data.get("priority"))
    period = data.get("period", "Tek Seferlik")
    deadline_raw = data.get("deadline")
    deadline = datetime.fromisoformat(deadline_raw).date() if deadline_raw else None
    next_due = None
    if category == "routine" and period != "Tek Seferlik":
        from models.database import _next_due_date

        next_due = _next_due_date(period)
        if not deadline:
            deadline = next_due
    cl_raw = data.get("checklist", "[]")
    if isinstance(cl_raw, list):
        cl_raw = _json.dumps(cl_raw)
    cl_items = _json.loads(cl_raw) if isinstance(cl_raw, str) else []
    task = Task(
        user_id=target_uid,
        title=data["title"],
        category=category,
        priority=priority,
        period=period,
        firm=data.get("firm", ""),
        team=data.get("team", ""),
        notes=data.get("notes", ""),
        deadline=deadline,
        next_due=next_due,
        checklist=_json.dumps(cl_items),
        checklist_done=_json.dumps([False] * len(cl_items)),
        manager_note=manager_note,
        assigned_by=assigned_by,
    )
    db.session.add(task)
    db.session.flush()
    if backup_file and backup_file.filename:
        try:
            fp = save_backup_file(backup_file, task.id, target_uid)
        except ValueError as e:  # izin verilmeyen dosya uzantısı — görev de kaydedilmez
            db.session.rollback()
            return jsonify({"error": str(e)}), 400
        db.session.add(
            ConfigBackup(
                task_id=task.id,
                user_id=target_uid,
                filename=backup_file.filename,
                file_path=fp,
                device=data.get("backup_device", ""),
                file_size=os.path.getsize(fp),
            )
        )
    # v4.4 — audit log
    target = db.session.get(User, target_uid)
    if assigned_by:
        log_audit(
            me,
            "task.assign",
            entity_type="task",
            entity_id=task.id,
            target_user=target,
            firm=task.firm,
            summary=f"'{task.title}' görevi {target.full_name if target else '?'} kişisine atandı",
            details={"title": task.title, "category": task.category, "manager_note": bool(manager_note)},
        )
    else:
        log_audit(
            me,
            "task.create",
            entity_type="task",
            entity_id=task.id,
            firm=task.firm,
            summary=f"'{task.title}' görevi oluşturuldu ({task.category})",
        )
    db.session.commit()
    return jsonify(task.to_dict()), 201


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@login_required
def update_task(task_id):
    me = _current_user()
    task = Task.query.get_or_404(task_id)
    # Sahibi veya director+ (firma bazlı) düzenleyebilir
    if task.user_id != me.id:
        owner = db.session.get(User, task.user_id)
        if not _can_modify_owned_task(me, owner):
            return jsonify({"error": "Bu görevi düzenleme yetkiniz yok"}), 403
    data = request.get_json()
    if "is_done" in data:
        if task.category == "routine" and task.period != "Tek Seferlik":
            # v5.0 — Rutin görevler: TaskOccurrence (period_key) kaydı oluştur/sil
            # Karar 2 = B: server date.today() kullanır; eski month/year param'ları silent ignore.
            from models.database import TaskOccurrence, _period_key

            today = date.today()
            pk = _period_key(task.period, today)
            if not pk:
                # Geçersiz periyot — fallback: is_done flag güncelle
                task.is_done = data["is_done"]
                task.completed_at = datetime.utcnow() if data["is_done"] else None
            else:
                comp = TaskOccurrence.query.filter_by(task_id=task.id, period_key=pk).first()
                if data["is_done"] and not comp:
                    db.session.add(TaskOccurrence(task_id=task.id, period_key=pk, completed_by=session["user_id"]))
                    task.last_completed = datetime.utcnow()
                elif not data["is_done"] and comp:
                    db.session.delete(comp)
        else:
            task.is_done = data["is_done"]
            task.completed_at = datetime.utcnow() if data["is_done"] else None
    if "title" in data:
        task.title = data["title"]
    if "category" in data:
        task.category = data["category"]
    if "priority" in data:
        task.priority = _normalize_priority(data["priority"])
    if "period" in data:
        task.period = data["period"]
    if "firm" in data:
        task.firm = data["firm"]
    if "team" in data:
        task.team = data["team"]
    if "notes" in data:
        task.notes = data["notes"]
    if "deadline" in data:
        task.deadline = datetime.fromisoformat(data["deadline"]).date() if data["deadline"] else None
    if "checklist" in data:
        cl = data["checklist"] if isinstance(data["checklist"], list) else _json.loads(data["checklist"])
        task.checklist = _json.dumps(cl)
        cld = task.get_checklist_done()
        while len(cld) < len(cl):
            cld.append(False)
        task.checklist_done = _json.dumps(cld[: len(cl)])
    if "checklist_done" in data:
        cld = (
            data["checklist_done"] if isinstance(data["checklist_done"], list) else _json.loads(data["checklist_done"])
        )
        task.checklist_done = _json.dumps(cld)
    if "project_status" in data:
        task.project_status = data["project_status"]
    # v4.3 — manager_note sadece director+ tarafından düzenlenebilir
    mn_changed = False
    old_manager_note = task.manager_note or ""
    if "manager_note" in data and me.is_director_or_above:
        new_mn = data["manager_note"] or ""
        if new_mn != old_manager_note:
            task.manager_note = new_mn
            mn_changed = True
    # v4.4 — audit log (manager_note değişimi + tamamlama)
    owner = db.session.get(User, task.user_id)
    if mn_changed:
        log_audit(
            me,
            "task.manager_note",
            entity_type="task",
            entity_id=task.id,
            target_user=owner,
            firm=task.firm,
            summary=f"'{task.title}' görevine IT Müdürü notu {'eklendi/güncellendi' if task.manager_note else 'silindi'}",
            details={"before": old_manager_note, "after": task.manager_note},
        )
    if "is_done" in data:
        log_audit(
            me,
            "task.complete" if data["is_done"] else "task.reopen",
            entity_type="task",
            entity_id=task.id,
            target_user=owner,
            firm=task.firm,
            summary=f"'{task.title}' görevi {'tamamlandı' if data['is_done'] else 'yeniden açıldı'}",
        )
    elif me.id != task.user_id:  # başka biri düzenliyorsa (director+)
        log_audit(
            me,
            "task.update",
            entity_type="task",
            entity_id=task.id,
            target_user=owner,
            firm=task.firm,
            summary=f"'{task.title}' görevi güncellendi",
        )
    db.session.commit()
    month_val = data.get("month", date.today().month)
    year_val = data.get("year", date.today().year)
    return jsonify(task.to_dict(month=month_val, year=year_val))


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    me = _current_user()
    task = Task.query.get_or_404(task_id)
    owner = db.session.get(User, task.user_id)
    if task.user_id != me.id:
        if not _can_modify_owned_task(me, owner):
            return jsonify({"error": "Bu görevi silme yetkiniz yok"}), 403
    log_audit(
        me,
        "task.delete",
        entity_type="task",
        entity_id=task.id,
        target_user=owner,
        firm=task.firm,
        summary=f"'{task.title}' görevi silindi",
    )
    db.session.delete(task)
    db.session.commit()
    return jsonify({"ok": True})


# ── CONFIG BACKUP ──
@app.route("/api/backups")
@login_required
def list_backups():
    user = _current_user()
    if user and user.permission_level == "junior":
        return jsonify({"error": "Yetkisiz"}), 403
    bkps = ConfigBackup.query.filter_by(user_id=session["user_id"]).order_by(ConfigBackup.uploaded_at.desc()).all()
    return jsonify([b.to_dict() for b in bkps])


@app.route("/api/backups/<int:bid>/download")
@login_required
def download_backup(bid):
    b = ConfigBackup.query.filter_by(id=bid, user_id=session["user_id"]).first_or_404()
    if not os.path.exists(b.file_path):
        return jsonify({"error": "Dosya sunucuda bulunamadı"}), 404
    return send_file(b.file_path, as_attachment=True, download_name=b.filename)


@app.route("/api/backups/<int:bid>", methods=["DELETE"])
@login_required
def delete_backup(bid):
    b = ConfigBackup.query.filter_by(id=bid, user_id=session["user_id"]).first_or_404()
    try:
        if os.path.exists(b.file_path):
            os.remove(b.file_path)
    except OSError:
        pass
    db.session.delete(b)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>/backups")
@login_required
def task_backups(task_id):
    task = Task.query.filter_by(id=task_id, user_id=session["user_id"]).first_or_404()
    return jsonify([b.to_dict() for b in task.backups])


@app.route("/api/tasks/<int:task_id>/backups", methods=["POST"])
@login_required
def add_task_backup(task_id):
    task = Task.query.filter_by(id=task_id, user_id=session["user_id"]).first_or_404()
    backup_file = request.files.get("backup_file")
    if not backup_file or not backup_file.filename:
        return jsonify({"error": "Dosya seçilmedi"}), 400
    try:
        fp = save_backup_file(backup_file, task.id, session["user_id"])
    except ValueError as e:  # izin verilmeyen dosya uzantısı
        return jsonify({"error": str(e)}), 400
    b = ConfigBackup(
        filename=backup_file.filename,
        file_path=fp,
        device=request.form.get("backup_device", ""),
        task_id=task.id,
        user_id=session["user_id"],
        file_size=os.path.getsize(fp),
    )
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201


# ── STATS ──
@app.route("/api/stats")
@login_required
def stats():
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err:
        return err
    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)

    # Aynı mantık: rutin + proje (aktif) + ay bazlı diğer
    created_match = db.and_(db.extract("month", Task.created_at) == month, db.extract("year", Task.created_at) == year)
    deadline_match = db.and_(
        Task.deadline != None, db.extract("month", Task.deadline) == month, db.extract("year", Task.deadline) == year
    )
    routines = Task.query.filter_by(user_id=uid, category="routine").all()
    projects = (
        Task.query.filter_by(user_id=uid, category="project")
        .filter(
            db.or_(
                Task.is_done == False,
                db.and_(
                    Task.completed_at != None,
                    db.extract("month", Task.completed_at) == month,
                    db.extract("year", Task.completed_at) == year,
                ),
            )
        )
        .all()
    )
    others = Task.query.filter(
        Task.user_id == uid, Task.category.notin_(["routine", "project"]), db.or_(created_match, deadline_match)
    ).all()

    tasks = routines + projects + others

    # v5.x — Tamamlanma/gecikme KANONİK kaynaktan (Task.is_done_now/is_overdue_now),
    # occ_map ile N+1'siz. Referans gün: görüntülenen ay bugünün ayıysa bugün,
    # değilse ayın 15'i (to_dict ile aynı semantik → ekran/PDF/stats birebir tutar).
    ref_dt = date.today() if (date.today().year == year and date.today().month == month) else date(year, month, 15)
    occ_map = _preload_routine_occurrences(tasks)

    total = len(tasks)
    done = sum(1 for t in tasks if _task_done_at(t, ref_dt, occ_map))
    by_cat = {}
    by_team = {}
    by_firm = {}
    for t in tasks:
        by_cat[t.category] = by_cat.get(t.category, 0) + 1
        by_team[t.team] = by_team.get(t.team, 0) + 1
        by_firm[t.firm] = by_firm.get(t.firm, 0) + 1
    overdue = sum(1 for t in tasks if _task_overdue_at(t, ref_dt, occ_map))
    return jsonify(
        {
            "total": total,
            "done": done,
            "pending": total - done,
            "overdue": overdue,
            "by_category": by_cat,
            "by_team": by_team,
            "by_firm": by_firm,
            "completion_rate": round(done / total * 100, 1) if total else 0,
        }
    )


# ── v4.8 DASHBOARD TRENDS — bu ay vs geçen ay karşılaştırması ──
def _stats_for_month(uid, month, year):
    """Tek ay için total/done/overdue hesaplar — /api/stats ile aynı mantık."""
    created_match = db.and_(db.extract("month", Task.created_at) == month, db.extract("year", Task.created_at) == year)
    deadline_match = db.and_(
        Task.deadline != None, db.extract("month", Task.deadline) == month, db.extract("year", Task.deadline) == year
    )
    routines = Task.query.filter_by(user_id=uid, category="routine").all()
    projects = (
        Task.query.filter_by(user_id=uid, category="project")
        .filter(
            db.or_(
                Task.is_done == False,
                db.and_(
                    Task.completed_at != None,
                    db.extract("month", Task.completed_at) == month,
                    db.extract("year", Task.completed_at) == year,
                ),
            )
        )
        .all()
    )
    others = Task.query.filter(
        Task.user_id == uid, Task.category.notin_(["routine", "project"]), db.or_(created_match, deadline_match)
    ).all()
    tasks = routines + projects + others
    # v5.x — Kanonik tamamlanma/gecikme (Task.is_done_now/is_overdue_now), occ_map ile
    # N+1'siz. stats() ile birebir aynı referans-gün semantiği.
    ref_dt = date.today() if (date.today().year == year and date.today().month == month) else date(year, month, 15)
    occ_map = _preload_routine_occurrences(tasks)

    total = len(tasks)
    done = sum(1 for t in tasks if _task_done_at(t, ref_dt, occ_map))
    overdue = sum(1 for t in tasks if _task_overdue_at(t, ref_dt, occ_map))
    return {"total": total, "done": done, "overdue": overdue, "rate": round(done / total * 100, 1) if total else 0.0}


@app.route("/api/dashboard/trends")
@login_required
def dashboard_trends():
    """v4.8 — Bu ay vs geçen ay KPI karşılaştırması.
    Döner: { current:{total,done,overdue,rate}, previous:{...},
             delta:{total,done,overdue,rate} }  (delta'lar işaretli sayı)
    """
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err:
        return err
    today = date.today()
    cur_m, cur_y = today.month, today.year
    if cur_m == 1:
        prev_m, prev_y = 12, cur_y - 1
    else:
        prev_m, prev_y = cur_m - 1, cur_y

    cur = _stats_for_month(uid, cur_m, cur_y)
    prev = _stats_for_month(uid, prev_m, prev_y)

    def _delta(c, p):
        return round(c - p, 1)

    return jsonify(
        {
            "current": cur,
            "previous": prev,
            "delta": {
                "total": _delta(cur["total"], prev["total"]),
                "done": _delta(cur["done"], prev["done"]),
                "overdue": _delta(cur["overdue"], prev["overdue"]),
                "rate": _delta(cur["rate"], prev["rate"]),
            },
        }
    )


# ── v4.5 SLA STATS ──
@app.route("/api/sla/stats")
@login_required
def sla_stats():
    """v4.5 — Destek talepleri için SLA metrikleri.
    Query: month, year, user_id (director+ için firma bazlı)"""
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err:
        return err
    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)

    # Destek görevleri — o ay içinde oluşturulanlar
    q = Task.query.filter(
        Task.user_id == uid,
        Task.category == "support",
        db.extract("month", Task.created_at) == month,
        db.extract("year", Task.created_at) == year,
    )
    tasks = q.all()
    now = datetime.utcnow()

    totals = {"total": 0, "open": 0, "resolved": 0, "breached": 0, "resolved_on_time": 0, "avg_resolution_hours": 0.0}
    by_priority = {}  # key: priority → dict
    sum_resolution = 0.0
    resolved_count = 0

    for t in tasks:
        prio = (t.priority or "orta").strip().lower()
        target_h = _sla_target_hours(prio)
        deadline_dt = sla_deadline(t.created_at, prio) if t.created_at else None  # v5.13 iş-saati
        bucket = by_priority.setdefault(
            prio,
            {
                "total": 0,
                "open": 0,
                "resolved": 0,
                "breached": 0,
                "resolved_on_time": 0,
                "target_hours": target_h,
                "avg_resolution_hours": 0.0,
                "_sum_resolution": 0.0,
                "_resolved_cnt": 0,
            },
        )
        totals["total"] += 1
        bucket["total"] += 1

        if t.is_done and t.completed_at:
            totals["resolved"] += 1
            bucket["resolved"] += 1
            res_h = business_hours_between(t.created_at, t.completed_at)  # v5.13 iş-saati
            sum_resolution += res_h
            resolved_count += 1
            bucket["_sum_resolution"] += res_h
            bucket["_resolved_cnt"] += 1
            breached = bool(deadline_dt and t.completed_at > deadline_dt)
            if breached:
                totals["breached"] += 1
                bucket["breached"] += 1
            else:
                totals["resolved_on_time"] += 1
                bucket["resolved_on_time"] += 1
        else:
            totals["open"] += 1
            bucket["open"] += 1
            # Açık görev deadline geçtiyse breach sayılır
            if deadline_dt and now > deadline_dt:
                totals["breached"] += 1
                bucket["breached"] += 1

    # Ortalamaları hesapla
    totals["avg_resolution_hours"] = round(sum_resolution / resolved_count, 2) if resolved_count else 0.0
    # compliance_pct: resolved_on_time / total (açık breach'ler dahil değil, sadece kapanan işler üzerinden)
    compliance_base = totals["resolved"]
    totals["compliance_pct"] = round(totals["resolved_on_time"] / compliance_base * 100, 1) if compliance_base else 0.0

    out_priority = {}
    for p, b in by_priority.items():
        b["avg_resolution_hours"] = round(b["_sum_resolution"] / b["_resolved_cnt"], 2) if b["_resolved_cnt"] else 0.0
        base = b["resolved"]
        b["compliance_pct"] = round(b["resolved_on_time"] / base * 100, 1) if base else 0.0
        b.pop("_sum_resolution", None)
        b.pop("_resolved_cnt", None)
        out_priority[p] = b

    # v5.13 — iş-saati yapılandırması (UI'da "İş saati: 09:00-18:00, Pzt-Cum" göstermek için)
    from models.database import _business_config

    cfg = _business_config()
    _DAY_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    business = {
        "enabled": cfg["enabled"],
        "work_start": cfg["start"],
        "work_end": cfg["end"],
        "work_days": sorted(cfg["days"]),
        "work_days_label": ", ".join(_DAY_TR[d] for d in sorted(cfg["days"])),
        "holidays": sorted(h.isoformat() for h in cfg["holidays"]),
    }
    return jsonify(
        {
            **totals,
            "by_priority": out_priority,
            "sla_targets": SLA_HOURS,
            "business_hours": business,
            "month": month,
            "year": year,
        }
    )


# ── FIRMS & TEAMS ──
@app.route("/api/firms")
@login_required
def get_firms():
    return jsonify([f.to_dict() for f in Firm.query.order_by(Firm.name).all()])


@app.route("/api/firms", methods=["POST"])
@manager_required
def create_firm():
    data = request.get_json()
    firm = Firm(name=data["name"], slug=_slugify_tr(data["name"]))
    db.session.add(firm)
    db.session.commit()
    return jsonify(firm.to_dict()), 201


@app.route("/api/firms/<int:fid>/teams")
@login_required
def get_teams(fid):
    return jsonify([t.to_dict() for t in Team.query.filter_by(firm_id=fid).order_by(Team.name).all()])


@app.route("/api/firms/<int:fid>/teams", methods=["POST"])
@manager_required
def create_team(fid):
    data = request.get_json()
    t = Team(firm_id=fid, name=data["name"])
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@app.route("/api/teams/<int:tid>", methods=["DELETE"])
@manager_required
def delete_team(tid):
    t = Team.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True})


# ── ADMIN ──
@app.route("/api/admin/users")
@manager_required
def admin_users():
    return jsonify([u.to_dict() for u in User.query.order_by(User.created_at.desc()).all()])


@app.route("/api/admin/users/<int:uid>", methods=["PATCH"])
@manager_required
def admin_update_user(uid):
    me = _current_user()
    target = User.query.get_or_404(uid)
    data = request.get_json()
    # IT Yöneticisi super_admin veya IT Müdürü'nü düzenleyemez
    if not me.is_super_admin and target.permission_level in ("super_admin", "it_director"):
        return jsonify({"error": "Bu kullanıcıyı düzenleme yetkiniz yok"}), 403
    # permission_level güncellemesi
    if "permission_level" in data:
        new_level = data["permission_level"]
        # IT Yöneticisi super_admin veya it_director atayamaz
        if not me.is_super_admin and new_level in ("super_admin", "it_director"):
            return jsonify({"error": "Bu rolü atama yetkiniz yok"}), 403
        target.permission_level = new_level
        target.is_admin = new_level in ("super_admin", "it_director", "it_manager")
    # can_access_board — sadece super_admin ayarlayabilir
    if "can_access_board" in data and me.is_super_admin:
        target.can_access_board = bool(data["can_access_board"])
    for f in ("role", "firm", "active"):
        if f in data:
            setattr(target, f, data[f])
    # v4.4 — audit
    log_audit(
        me,
        "user.update",
        entity_type="user",
        entity_id=target.id,
        target_user=target,
        firm=target.firm,
        summary=f"{target.full_name} kullanıcı bilgileri güncellendi",
        details={
            k: data.get(k) for k in ("permission_level", "role", "firm", "active", "can_access_board") if k in data
        },
    )
    db.session.commit()
    return jsonify(target.to_dict())


@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@manager_required
def admin_delete_user(uid):
    me = _current_user()
    target = User.query.get_or_404(uid)
    # IT Yöneticisi super_admin veya IT Müdürü silemez
    if not me.is_super_admin and target.permission_level in ("super_admin", "it_director"):
        return jsonify({"error": "Bu kullanıcıyı silme yetkiniz yok"}), 403
    log_audit(
        me,
        "user.delete",
        entity_type="user",
        entity_id=target.id,
        target_user=target,
        firm=target.firm,
        summary=f"{target.full_name} kullanıcı silindi",
    )
    db.session.delete(target)
    db.session.commit()
    return jsonify({"ok": True})


# ── INVITE ──
@app.route("/api/admin/invite", methods=["POST"])
@manager_required
def invite_user():
    me = _current_user()
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Mail boş"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Kayıtlı"}), 409
    perm = data.get("permission_level", "junior")
    # IT Yöneticisi super_admin veya it_director davet edemez
    if not me.is_super_admin and perm in ("super_admin", "it_director"):
        return jsonify({"error": "Bu rolü davet etme yetkiniz yok"}), 403
    Invitation.query.filter_by(email=email, used=False).delete()
    token = secrets.token_urlsafe(32)
    role_label = {
        "super_admin": "Super Admin",
        "it_director": "IT Müdürü",
        "it_manager": "IT Yöneticisi",
        "it_specialist": "IT Specialist",
        "junior": "Junior",
    }.get(perm, "Junior")
    inv = Invitation(
        email=email,
        full_name=data.get("full_name", ""),
        role=role_label,
        firm=data.get("firm", ""),
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=7),
        invited_by=session["user_id"],
    )
    db.session.add(inv)
    db.session.flush()
    log_audit(
        me,
        "user.invite",
        entity_type="invitation",
        entity_id=inv.id,
        firm=inv.firm,
        summary=f"{email} adresine {role_label} rolü için davet gönderildi",
        details={"email": email, "role": role_label, "firm": inv.firm},
    )
    db.session.commit()
    url = f"{request.host_url}register?token={token}"
    result = send_invite_email(email, data.get("full_name", ""), url, role_label)
    return jsonify({"ok": result.get("ok"), "invite_url": url, "permission_level": perm})


@app.route("/api/admin/invitations")
@manager_required
def list_invitations():
    invs = Invitation.query.filter_by(used=False).order_by(Invitation.created_at.desc()).all()
    return jsonify([i.to_dict() for i in invs])


@app.route("/api/admin/invitations/<int:inv_id>", methods=["DELETE"])
@manager_required
def cancel_invitation(inv_id):
    inv = Invitation.query.get_or_404(inv_id)
    if inv.used:
        return jsonify({"error": "Zaten kullanılmış"}), 400
    db.session.delete(inv)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/invitations/<int:inv_id>/resend", methods=["POST"])
@manager_required
def resend_invitation(inv_id):
    inv = Invitation.query.get_or_404(inv_id)
    if inv.used:
        return jsonify({"error": "Zaten kullanılmış"}), 400
    inv.token = secrets.token_urlsafe(32)
    inv.expires_at = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    url = f"{request.host_url}register?token={inv.token}"
    result = send_invite_email(inv.email, inv.full_name, url, inv.role)
    return jsonify({"ok": result.get("ok"), "invite_url": url})


@app.route("/register")
def register():
    token = request.args.get("token")
    inv = Invitation.query.filter_by(token=token, used=False).first()
    if not inv or inv.expires_at < datetime.utcnow():
        return render_template("error.html", msg="Bu davet bağlantısı geçersiz veya süresi dolmuş."), 400
    return render_template("register.html", invitation=inv, token=token)


# ── REPORT ──
@app.route("/api/report/pdf")
@manager_required
def download_report():
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err:
        return err
    user = db.session.get(User, uid)
    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)
    # F2.1 fix: ekrandaki liste ile aynı görev kümesi (rutinler + carry-over dahil),
    # yalnızca created_at o ay olanlar DEĞİL.
    tasks = _collect_tasks_for_month(user.id, month, year)
    pdf = generate_monthly_pdf(user, tasks, month, year)
    resp = send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"IT_Rapor_{user.username}_{year}_{month:02d}.pdf",
    )
    resp.headers["Content-Disposition"] = f"inline; filename=IT_Rapor_{user.username}_{year}_{month:02d}.pdf"
    return resp


@app.route("/api/report/send", methods=["POST"])
@manager_required
def send_report():
    me = _current_user()
    data = request.get_json() or {}
    uid, err = _resolve_scope_uid(me, data.get("user_id"))
    if err:
        return err
    user = db.session.get(User, uid)
    month = data.get("month", date.today().month)
    year = data.get("year", date.today().year)
    # F2.1 fix: rapor PDF'i ekrandaki liste ile aynı görev kümesini kullanır.
    tasks = _collect_tasks_for_month(user.id, month, year)
    pdf = generate_monthly_pdf(user, tasks, month, year)
    return jsonify(send_report_email(user, pdf, month, year, cc=data.get("cc"), o365_token=session.get("o365_token")))


@app.route("/api/me")
@login_required
def me():
    return jsonify(db.session.get(User, session["user_id"]).to_dict())


# ── v4.4 AUDIT LOG ──
def _audit_scoped_query(me):
    """AuditLog sorgusu: firma kapsamı + request.args filtreleri (TEK KAYNAK).

    list_audit ve export_audit_csv aynı kapsam/filtre mantığını kullanır.
    Geçersiz tarih formatında ValueError fırlatır (çağıran 400 döner).
    """
    q = AuditLog.query
    # Firma kapsamı: super_admin tümünü; director YÖNETTİĞİ tüm firmaları (F2.3).
    if not me.is_super_admin:
        scope = set(me.managed_firm_slugs)
        scope.add(me.firm or "")
        q = q.filter(AuditLog.firm.in_(list(scope)))
    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        q = q.filter(AuditLog.created_at >= datetime.fromisoformat(start))
    if end:
        q = q.filter(AuditLog.created_at < datetime.fromisoformat(end) + timedelta(days=1))
    action = request.args.get("action")
    if action:
        q = q.filter(AuditLog.action == action)
    actor_id = request.args.get("actor_id", type=int)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    target_uid = request.args.get("target_user_id", type=int)
    if target_uid:
        q = q.filter(AuditLog.target_user_id == target_uid)
    firm = request.args.get("firm")
    if firm and me.is_super_admin:
        q = q.filter(AuditLog.firm == firm)
    return q


# CSV/UI'da okunabilir işlem etiketleri (app.js AUDIT_ACTION_LABELS ile paralel)
_AUDIT_ACTION_LABELS = {
    "task.create": "Görev Oluşturma",
    "task.assign": "Görev Atama",
    "task.update": "Görev Güncelleme",
    "task.complete": "Görev Tamamlama",
    "task.reopen": "Görev Yeniden Açma",
    "task.manager_note": "IT Müdürü Notu",
    "task.delete": "Görev Silme",
    "user.invite": "Kullanıcı Daveti",
    "user.update": "Kullanıcı Güncelleme",
    "user.delete": "Kullanıcı Silme",
    "settings.smtp": "SMTP Ayarı",
}


@app.route("/api/audit")
@director_required
def list_audit():
    """Denetim kayıtları — director+ için.
    Query: start, end (YYYY-MM-DD); action; actor_id; target_user_id; firm; limit (max 500), offset"""
    me = _current_user()
    try:
        q = _audit_scoped_query(me)
    except ValueError:
        return jsonify({"error": "Geçersiz tarih formatı (YYYY-MM-DD bekleniyor)"}), 400
    limit = min(request.args.get("limit", 200, type=int), 500)
    offset = request.args.get("offset", 0, type=int)
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify({"total": total, "rows": [r.to_dict() for r in rows]})


@app.route("/api/audit/export")
@director_required
def export_audit_csv():
    """v5.14 — Denetim kayıtlarını CSV olarak dışa aktarır (liste ile aynı filtreler, max 5000)."""
    me = _current_user()
    try:
        q = _audit_scoped_query(me)
    except ValueError:
        return jsonify({"error": "Geçersiz tarih formatı (YYYY-MM-DD bekleniyor)"}), 400
    rows_db = q.order_by(AuditLog.created_at.desc()).limit(5000).all()
    header = ["Tarih", "İşlem", "Aktör", "Hedef", "Firma", "Özet"]
    rows = []
    for r in rows_db:
        rows.append(
            [
                r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                _AUDIT_ACTION_LABELS.get(r.action, r.action),
                r.actor_name or "",
                r.target_name or "",
                r.firm or "",
                r.summary or "",
            ]
        )
    today = date.today().isoformat()
    return _csv_response(f"denetim_{today}.csv", header, rows)


@app.route("/api/me", methods=["PATCH"])
@login_required
def update_me():
    user = db.session.get(User, session["user_id"])
    data = request.get_json()
    if "username" in data:
        new_u = data["username"].strip().lower()
        if not new_u:
            return jsonify({"error": "Kullanıcı adı boş olamaz"}), 400
        conflict = User.query.filter_by(username=new_u).first()
        if conflict and conflict.id != user.id:
            return jsonify({"error": "Bu kullanıcı adı zaten alınmış"}), 409
        user.username = new_u
    for field in ("email", "full_name", "role"):
        if field in data and data[field]:
            setattr(user, field, data[field])
    if data.get("password"):
        if len(data["password"]) < 6:
            return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400
        user.set_password(data["password"])
    db.session.commit()
    return jsonify(user.to_dict())


@app.route("/api/settings/smtp", methods=["GET", "POST"])
@super_admin_required
def smtp_settings():
    # ENV_FILE_PATH ile override edilebilir (test izolasyonu); yoksa proje kökü .env.
    env_path = os.environ.get("ENV_FILE_PATH") or os.path.join(os.path.dirname(__file__), ".env")
    if request.method == "GET":
        return jsonify(
            {
                "smtp_host": os.environ.get("SMTP_HOST", "smtp.office365.com"),
                "smtp_port": os.environ.get("SMTP_PORT", "587"),
                "smtp_user": os.environ.get("SMTP_USER", ""),
                "smtp_pass": "••••••" if os.environ.get("SMTP_PASS") else "",
            }
        )
    data = request.get_json() or {}

    # GÜVENLİK — env injection savunması. Değerler .env'e ham yazıldığı için
    # newline/CR içeren bir değer YENİ satır enjekte edebilir, örn:
    #   smtp_pass = "x\nADMIN_PASSWORD=attacker"  → .env'e ekstra env değişkeni.
    # super_admin gate var ama oturum ele geçirme (XSS/CSRF) veya kötü niyetli
    # super_admin bununla SECRET_KEY/ADMIN_PASSWORD/DATABASE_URL yazıp sistemi
    # kalıcı ele geçirebilir. Kontrol karakteri içeren her değer reddedilir.
    def _clean_env_value(raw):
        if raw is None:
            return None
        s = str(raw)
        if any(c in s for c in ("\n", "\r", "\x00")):
            raise ValueError("Değerlerde satır sonu / kontrol karakteri kullanılamaz")
        return s.strip()

    try:
        updates = {}
        if data.get("smtp_host"):
            updates["SMTP_HOST"] = _clean_env_value(data["smtp_host"])
        if data.get("smtp_port"):
            port_str = _clean_env_value(data["smtp_port"])
            if not port_str.isdigit() or not (1 <= int(port_str) <= 65535):
                return jsonify({"error": "SMTP port 1-65535 aralığında bir sayı olmalı"}), 400
            updates["SMTP_PORT"] = port_str
        if data.get("smtp_user"):
            updates["SMTP_USER"] = _clean_env_value(data["smtp_user"])
        if data.get("smtp_pass") and data["smtp_pass"] != "••••••":
            updates["SMTP_PASS"] = _clean_env_value(data["smtp_pass"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []
        new_lines = []
        updated_keys = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        for key, val in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        # .env yalnızca sahibi okuyabilsin (gizli bilgi içerir) — best-effort.
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
        for key, val in updates.items():
            os.environ[key] = val
        # Denetim kaydı — kim değiştirdi (şifre DEĞERİ loglanmaz, yalnız anahtarlar).
        me = _current_user()
        log_audit(
            me,
            "settings.smtp",
            entity_type="settings",
            summary=f"SMTP ayarları güncellendi ({', '.join(sorted(updates.keys())) or 'değişiklik yok'})",
            details={"updated_keys": sorted(updates.keys())},
        )
        db.session.commit()
        return jsonify({"ok": True, "updated": list(updates.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/smtp/test", methods=["POST"])
@super_admin_required
def test_smtp():
    import smtplib
    import ssl

    host = os.environ.get("SMTP_HOST", "smtp.office365.com")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASS", "")
    if not user or not pw:
        return jsonify({"ok": False, "error": "Mail adresi veya şifre girilmemiş"}), 400
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(user, pw)
        return jsonify({"ok": True, "message": f"{host}:{port} bağlantısı başarılı"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ══════════════════════════════════════════════════════════
#  v4.6 — BİLDİRİMLER / ALARM
# ══════════════════════════════════════════════════════════
@app.route("/api/tasks/<int:task_id>/alarm", methods=["PATCH"])
@login_required
def update_task_alarm(task_id):
    """Tek görevin alarm_enabled durumunu günceller."""
    me = _current_user()
    task = Task.query.get_or_404(task_id)
    if task.user_id != me.id:
        owner = db.session.get(User, task.user_id)
        if not _can_modify_owned_task(me, owner):
            return jsonify({"error": "Bu görevin alarmını düzenleme yetkiniz yok"}), 403
    data = request.get_json() or {}
    if "alarm_enabled" in data:
        task.alarm_enabled = bool(data["alarm_enabled"])
        db.session.commit()
    return jsonify({"ok": True, "alarm_enabled": bool(task.alarm_enabled)})


@app.route("/api/notifications/settings", methods=["GET"])
@login_required
def get_notification_settings():
    me = _current_user()
    from services.notifier import effective_digest_hour, effective_overdue_days, effective_sla_ratio

    tz_name = os.environ.get("SCHEDULER_TZ", "UTC")
    digest_hour = effective_digest_hour(me)
    return jsonify(
        {
            "notify_overdue": bool(me.notify_overdue) if me.notify_overdue is not None else True,
            "notify_sla_warning": bool(me.notify_sla_warning) if me.notify_sla_warning is not None else True,
            "notify_daily_digest": bool(me.notify_daily_digest) if me.notify_daily_digest is not None else True,
            # v5.10 — ayrı breach kanalı + müdür digesti + ayarlanabilir eşikler
            "notify_sla_breach": bool(me.notify_sla_breach) if me.notify_sla_breach is not None else True,
            "notify_manager_digest": (bool(me.notify_manager_digest) if me.notify_manager_digest is not None else True),
            "overdue_days": effective_overdue_days(me),
            "sla_warning_ratio": effective_sla_ratio(me),
            "digest_hour": digest_hour,
            "timezone": tz_name,
            "is_director": me.is_director_or_above,
            "schedule": f"Her gün {digest_hour:02d}:00 ({tz_name})",
        }
    )


@app.route("/api/notifications/settings", methods=["PATCH"])
@login_required
def update_notification_settings():
    me = _current_user()
    data = request.get_json() or {}
    bool_fields = (
        "notify_overdue",
        "notify_sla_warning",
        "notify_daily_digest",
        "notify_sla_breach",
        "notify_manager_digest",
    )
    for field in bool_fields:
        if field in data:
            setattr(me, field, bool(data[field]))
    # v5.10 — ayarlanabilir eşikler; aralık dışı değer 400 döner (sessiz clamp yok)
    if "notify_overdue_days" in data:
        try:
            v = int(data["notify_overdue_days"])
        except (TypeError, ValueError):
            return jsonify({"error": "Gecikme eşiği sayı olmalı"}), 400
        if not 1 <= v <= 30:
            return jsonify({"error": "Gecikme eşiği 1-30 gün aralığında olmalı"}), 400
        me.notify_overdue_days = v
    if "notify_sla_ratio" in data:
        try:
            r = float(data["notify_sla_ratio"])
        except (TypeError, ValueError):
            return jsonify({"error": "SLA oranı sayı olmalı"}), 400
        if not 0.05 <= r <= 0.9:
            return jsonify({"error": "SLA uyarı oranı 0.05-0.90 aralığında olmalı"}), 400
        me.notify_sla_ratio = r
    if "notify_digest_hour" in data:
        try:
            h = int(data["notify_digest_hour"])
        except (TypeError, ValueError):
            return jsonify({"error": "Digest saati sayı olmalı"}), 400
        if not 0 <= h <= 23:
            return jsonify({"error": "Digest saati 0-23 aralığında olmalı"}), 400
        me.notify_digest_hour = h
    db.session.commit()
    from services.notifier import effective_digest_hour, effective_overdue_days, effective_sla_ratio

    return jsonify(
        {
            "ok": True,
            "notify_overdue": bool(me.notify_overdue),
            "notify_sla_warning": bool(me.notify_sla_warning),
            "notify_daily_digest": bool(me.notify_daily_digest),
            "notify_sla_breach": bool(me.notify_sla_breach),
            "notify_manager_digest": bool(me.notify_manager_digest),
            "overdue_days": effective_overdue_days(me),
            "sla_warning_ratio": effective_sla_ratio(me),
            "digest_hour": effective_digest_hour(me),
        }
    )


@app.route("/api/notifications/preview")
@login_required
def notifications_preview():
    """Kendi uyarı listesini dry-run olarak döner (mail atmaz)."""
    me = _current_user()
    groups = collect_user_alerts(me)
    return jsonify(
        {
            "overdue": groups["overdue"],
            "sla_warning": groups["sla_warning"],
            "sla_breached": groups["sla_breached"],
            "total": sum(len(v) for v in groups.values()),
        }
    )


@app.route("/api/notifications/test", methods=["POST"])
@login_required
def notifications_test():
    """Digest mail testini anında kendi kullanıcın için çalıştırır."""
    me = _current_user()
    data = request.get_json(silent=True) or {}
    dry = bool(data.get("dry_run", False))
    report = run_digest_job(dry_run=dry, only_user_id=me.id)
    return jsonify(report)


@app.route("/api/notifications/run-now", methods=["POST"])
@super_admin_required
def notifications_run_now():
    """Super admin — tüm kullanıcılar için digest job'u tetikler."""
    data = request.get_json(silent=True) or {}
    dry = bool(data.get("dry_run", False))
    report = run_digest_job(dry_run=dry)
    return jsonify(report)


# ══════════════════════════════════════════════════════════
#  v5.15 — İNTRANET PORTAL (self-service, LOGIN YOK)
# ══════════════════════════════════════════════════════════
# Son kullanıcı /portal üzerinden destek talebi açar; tahmin edilemez bir
# Case No (INV-7K3M9Q) üretilir ve ACK maili gönderilir. Takip sorgusu
# Case No + e-posta İKİSİ birlikte doğrulanarak yapılır (tek başına kod yetmez).
# Faz A: form + ACK + temel durum görüntüleme. Faz B: CaseMessage yanıt akışı.

# Karışabilen karakterler yok (0/O, 1/I/L) — telefonda okunabilir kod
_CASE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # pragma: allowlist secret  (case-kodu alfabesi, sır değil)
_CASE_PREFIX = {"inventist": "INV", "assos": "ASS"}
_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Public form/lookup için IP bazlı basit rate-limit (login limiter kalıbı)
_PORTAL_HITS: dict = {}
_PORTAL_MAX = 10  # 10 dakikada 10 istek / IP
_PORTAL_WINDOW = 600


def _portal_rate_limited(ip):
    import time as _t

    stamps = _PORTAL_HITS.get(ip)
    if not stamps:
        return False
    now = _t.time()
    stamps[:] = [t for t in stamps if now - t < _PORTAL_WINDOW]
    if not stamps:
        _PORTAL_HITS.pop(ip, None)
        return False
    return len(stamps) >= _PORTAL_MAX


def _portal_register_hit(ip):
    import time as _t

    if len(_PORTAL_HITS) > 2000:
        _PORTAL_HITS.clear()
    _PORTAL_HITS.setdefault(ip, []).append(_t.time())


def _gen_case_code(firm_slug):
    """Tahmin edilemez, marka önekli case kodu: INV-7K3M9Q (unique garantili)."""
    prefix = _CASE_PREFIX.get((firm_slug or "").lower(), "GEN")
    for _ in range(20):
        body = "".join(secrets.choice(_CASE_ALPHABET) for _ in range(6))
        code = f"{prefix}-{body}"
        if not Task.query.filter_by(case_code=code).first():
            return code
    # Aşırı düşük olasılık: 8 haneye çık
    body = "".join(secrets.choice(_CASE_ALPHABET) for _ in range(8))
    return f"{prefix}-{body}"


@app.route("/portal")
def portal_home():
    """Public intranet portal SPA — login gerektirmez."""
    return render_template("portal.html", version=APP_VERSION)


@app.route("/portal/api/cases", methods=["POST"])
def portal_create_case():
    """Portaldan yeni destek talebi — LOGIN YOK. Case No üretir + ACK mail."""
    ip = request.remote_addr or "?"
    if _portal_rate_limited(ip):
        return jsonify({"error": "Çok fazla istek — birkaç dakika sonra tekrar deneyin"}), 429
    _portal_register_hit(ip)
    data = request.get_json(silent=True) or {}
    firm = (data.get("firm") or "").strip().lower()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    subject = (data.get("subject") or "").strip()
    category = (data.get("category") or "other").strip()
    description = (data.get("description") or "").strip()
    # AnyDesk ID — opsiyonel; kontrol karakterleri temizlenir, 40 kr tavan
    anydesk = " ".join((data.get("anydesk") or "").split())[:40]
    # Doğrulama (form kuralları: ad+mail+konu zorunlu, açıklama ≥60)
    if firm not in _CASE_PREFIX:
        return jsonify({"error": "Geçersiz firma"}), 400
    if not name or not subject:
        return jsonify({"error": "Ad-soyad ve konu zorunludur"}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "Geçerli bir e-posta adresi girin"}), 400
    if len(description) < 60:
        return jsonify({"error": "Açıklama en az 60 karakter olmalı"}), 400
    # Firma varsayılan kuyruk sahibi: o firmadaki ilk aktif super_admin/it_* (yoksa herhangi admin)
    assignee = (
        User.query.filter(User.firm == firm, User.active == True, User.is_admin == True).order_by(User.id).first()
    )
    if not assignee:
        assignee = User.query.filter(User.is_admin == True, User.active == True).order_by(User.id).first()
    case_code = _gen_case_code(firm)
    task = Task(
        user_id=assignee.id if assignee else None,
        title=subject[:300],
        category="support",
        priority="orta",
        period="Tek Seferlik",
        firm=firm,
        notes=description,
        source="portal",
        case_code=case_code,
        reporter_email=email,
        reporter_name=name[:100],
        reporter_anydesk=anydesk or None,
    )
    db.session.add(task)
    db.session.flush()
    log_audit(
        assignee,
        "task.create",
        entity_type="task",
        entity_id=task.id,
        firm=firm,
        summary=f"Portal talebi {case_code} — {subject[:80]}",
        details={"source": "portal", "case_code": case_code, "reporter": email, "category": category},
    )
    db.session.commit()
    # ACK maili (best-effort — başarısızsa case yine açık)
    try:
        from services.mailer import send_case_ack

        send_case_ack(email, name, case_code, subject, firm)
    except Exception as e:
        print(f"[portal] ACK mail hatası: {e}")
    return jsonify({"ok": True, "case_code": case_code}), 201


def _case_public_dict(task):
    """Case takip sayfası için GÜVENLİ alanlar (iç notlar/atanan mail vb. YOK).

    v5.15 Faz B — durum artık daha anlamlı: IT en az bir KULLANICIYA yanıt (it)
    mesajı yazdıysa "in_progress"; yalnız kuyruğa atanmış ama yanıt yoksa "received".
    (Eski: user_id varsa hep in_progress → oto-atama yüzünden yeni case hep işlemde
    görünüyordu.) Mesaj akışı reporter+it (internal HARİÇ) döner.
    """
    has_it_reply = CaseMessage.query.filter_by(task_id=task.id, sender_type="it").first() is not None
    status = "resolved" if task.is_done else ("in_progress" if has_it_reply else "received")
    msgs = (
        CaseMessage.query.filter(CaseMessage.task_id == task.id, CaseMessage.sender_type.in_(["reporter", "it"]))
        .order_by(CaseMessage.created_at.asc())
        .all()
    )
    return {
        "case_code": task.case_code,
        "subject": task.title,
        "category": task.category,
        "firm": task.firm,
        "status": status,
        "is_done": bool(task.is_done),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "reporter_name": task.reporter_name,
        "reporter_anydesk": task.reporter_anydesk,
        "description": task.notes or "",
        "messages": [m.to_public_dict() for m in msgs],
    }


def _portal_verify_case(data):
    """Portal doğrulaması: Case No + e-posta → (task, error_response). Tek kaynak."""
    code = (data.get("case_code") or "").strip().upper()
    email = (data.get("email") or "").strip().lower()
    task = Task.query.filter_by(case_code=code, source="portal").first()
    if not task or (task.reporter_email or "").lower() != email:
        return None, (jsonify({"error": "Case No veya e-posta hatalı"}), 404)
    return task, None


@app.route("/portal/api/lookup", methods=["POST"])
def portal_lookup_case():
    """Case takip — Case No + e-posta İKİSİ birlikte doğrulanır (tek başına kod yetmez)."""
    ip = request.remote_addr or "?"
    if _portal_rate_limited(ip):
        return jsonify({"error": "Çok fazla deneme — birkaç dakika sonra tekrar deneyin"}), 429
    _portal_register_hit(ip)
    task, err = _portal_verify_case(request.get_json(silent=True) or {})
    if err:
        return err
    return jsonify(_case_public_dict(task))


@app.route("/portal/api/case/reply", methods=["POST"])
def portal_case_reply():
    """Kullanıcı case'ine yanıt yazar (login yok — her istekte Case No + e-posta doğrulanır)."""
    ip = request.remote_addr or "?"
    if _portal_rate_limited(ip):
        return jsonify({"error": "Çok fazla istek — birkaç dakika sonra tekrar deneyin"}), 429
    _portal_register_hit(ip)
    data = request.get_json(silent=True) or {}
    task, err = _portal_verify_case(data)
    if err:
        return err
    body = (data.get("body") or "").strip()
    if len(body) < 2:
        return jsonify({"error": "Mesaj boş olamaz"}), 400
    if len(body) > 5000:
        body = body[:5000]
    msg = CaseMessage(
        task_id=task.id,
        sender_type="reporter",
        author_id=None,
        author_name=task.reporter_name or "Talep Sahibi",
        body=body,
    )
    db.session.add(msg)
    db.session.commit()
    # Atanan IT'yi bilgilendir (best-effort; anlık — digest beklemez)
    try:
        owner = db.session.get(User, task.user_id) if task.user_id else None
        if owner and owner.email:
            from services.mailer import send_case_user_replied

            send_case_user_replied(owner.email, task.case_code, task.title, task.reporter_name or "")
    except Exception as e:
        print(f"[portal] IT bildirim hatası: {e}")
    return jsonify(_case_public_dict(task)), 201


# ── IT tarafı: case mesajları (auth) — İç Notlar | Kullanıcıya Yanıt ──
def _can_view_task(me, task):
    owner = db.session.get(User, task.user_id) if task.user_id else None
    return task.user_id == me.id or _can_modify_owned_task(me, owner)


@app.route("/api/tasks/<int:task_id>/messages", methods=["GET"])
@login_required
def list_case_messages(task_id):
    """IT: bir case'in TÜM mesajları (reporter + it + internal). Görünürlük IT'de."""
    me = _current_user()
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(me, task):
        return jsonify({"error": "Bu talebi görüntüleme yetkiniz yok"}), 403
    msgs = CaseMessage.query.filter_by(task_id=task_id).order_by(CaseMessage.created_at.asc()).all()
    return jsonify(
        {"case_code": task.case_code, "reporter_email": task.reporter_email, "messages": [m.to_dict() for m in msgs]}
    )


@app.route("/api/tasks/<int:task_id>/messages", methods=["POST"])
@login_required
def add_case_message(task_id):
    """IT mesaj ekler. sender_type: 'it' (kullanıcıya yanıt → mail) | 'internal' (iç not)."""
    me = _current_user()
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(me, task):
        return jsonify({"error": "Bu talebe yazma yetkiniz yok"}), 403
    data = request.get_json() or {}
    stype = data.get("sender_type")
    if stype not in ("it", "internal"):
        return jsonify({"error": "Geçersiz mesaj türü"}), 400
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Mesaj boş olamaz"}), 400
    msg = CaseMessage(
        task_id=task.id,
        sender_type=stype,
        author_id=me.id,
        author_name=me.full_name or me.username,
        body=body[:5000],
    )
    db.session.add(msg)
    db.session.commit()
    # "it" (kullanıcıya yanıt) → talep sahibine bildirim maili
    if stype == "it" and task.reporter_email:
        try:
            from services.mailer import send_case_reply_notice

            send_case_reply_notice(task.reporter_email, task.case_code, task.title)
        except Exception as e:
            print(f"[case] yanıt bildirimi hatası: {e}")
    return jsonify(msg.to_dict()), 201


@app.route("/api/board/cards", methods=["GET"])
@board_access_required
def board_list_cards():
    me = _current_user()
    q = BoardCard.query.order_by(BoardCard.column, BoardCard.position, BoardCard.created_at)
    # Super admin tum kartlari gorur, digerleri kendi firmasinin kartlarini
    if not me.is_super_admin:
        q = q.filter_by(firm=me.firm)
    return jsonify([c.to_dict() for c in q.all()])


@app.route("/api/board/cards", methods=["POST"])
@board_access_required
def board_create_card():
    me = _current_user()
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Baslik zorunludur"}), 400
    col = data.get("column", "todo")
    # Pozisyonu kolonun sonuna ekle
    max_pos = db.session.query(db.func.max(BoardCard.position)).filter_by(column=col).scalar() or 0
    card = BoardCard(
        title=title,
        description=data.get("description", ""),
        column=col,
        position=max_pos + 1,
        color=data.get("color", "yellow"),
        checklist=_json.dumps(data.get("checklist", [])),
        checklist_done=_json.dumps(data.get("checklist_done", [])),
        created_by=me.id,
        assigned_to=data.get("assigned_to"),
        firm=data.get("firm", me.firm),
    )
    db.session.add(card)
    db.session.commit()
    return jsonify(card.to_dict()), 201


@app.route("/api/board/cards/<int:card_id>", methods=["PATCH"])
@board_access_required
def board_update_card(card_id):
    card = BoardCard.query.get_or_404(card_id)
    data = request.get_json() or {}
    for field in ("title", "description", "column", "position", "color", "firm", "assigned_to"):
        if field in data:
            setattr(card, field, data[field])
    if "checklist" in data:
        card.checklist = _json.dumps(data["checklist"])
    if "checklist_done" in data:
        card.checklist_done = _json.dumps(data["checklist_done"])
    db.session.commit()
    return jsonify(card.to_dict())


@app.route("/api/board/cards/<int:card_id>", methods=["DELETE"])
@board_access_required
def board_delete_card(card_id):
    me = _current_user()
    card = BoardCard.query.get_or_404(card_id)
    if not me.is_super_admin and card.created_by != me.id:
        return jsonify({"error": "Bu karti silme yetkiniz yok"}), 403
    db.session.delete(card)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/board/cards/<int:card_id>/comments", methods=["GET"])
@board_access_required
def board_list_comments(card_id):
    BoardCard.query.get_or_404(card_id)
    comments = BoardComment.query.filter_by(card_id=card_id).order_by(BoardComment.created_at.asc()).all()
    return jsonify([c.to_dict() for c in comments])


@app.route("/api/board/cards/<int:card_id>/comments", methods=["POST"])
@board_access_required
def board_add_comment(card_id):
    BoardCard.query.get_or_404(card_id)
    me = _current_user()
    data = request.get_json() or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Yorum bos olamaz"}), 400
    comment = BoardComment(card_id=card_id, user_id=me.id, content=content)
    db.session.add(comment)
    db.session.commit()
    return jsonify(comment.to_dict()), 201


# Board kullanicilari listesi (atama dropdown icin)
@app.route("/api/board/users", methods=["GET"])
@board_access_required
def board_list_users():
    users = User.query.filter_by(active=True).all()
    return jsonify([{"id": u.id, "full_name": u.full_name, "firm": u.firm} for u in users])


# ══════════════════════════════════════════════════════════
#  v4.6 — Scheduler (APScheduler)
# ══════════════════════════════════════════════════════════
_scheduler = None


def start_scheduler():
    """Günlük digest job'unu APScheduler ile planlar.
    - ENABLE_SCHEDULER=0 ise başlatılmaz.
    - Flask debug reloader altında ikinci process'te başlatılmaz.
    - Tek seferlik (singleton) başlatma garantisi.
    """
    global _scheduler
    if _scheduler is not None:
        return
    if os.environ.get("ENABLE_SCHEDULER", "1") != "1":
        print("[scheduler] devre dışı (ENABLE_SCHEDULER=0)")
        return
    # Flask debug reloader — sadece ikinci (asıl) process başlatır
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("[scheduler] apscheduler kurulu değil — bildirimler pasif")
        return

    minute = int(os.environ.get("NOTIFY_MINUTE", "0"))

    sch = BackgroundScheduler(daemon=True, timezone=os.environ.get("SCHEDULER_TZ", "UTC"))
    tz_obj = sch.timezone  # scheduler'ın çözümlenmiş timezone objesi — job içinde saat bunun üzerinden

    # v5.10 — Saatlik tek job: her saat başı (NOTIFY_MINUTE dakikasında) çalışır.
    #   1) Digest saati o saate denk gelen kullanıcılara kişisel (+müdür) digest.
    #      Eski model tüm kullanıcılar için sabit NOTIFY_HOUR idi; artık kullanıcı
    #      bazlı notify_digest_hour (NULL → NOTIFY_HOUR varsayılanı, geriye dönük aynı).
    #   2) SLA breach kontrolü: yeni breach'ler digest saati beklemeden bildirilir
    #      (4 saatlik SLA'da günlük digest çok geç kalıyordu). Anti-spam last_notified.
    def _job_wrapper():
        with app.app_context():
            current_hour = datetime.now(tz_obj).hour
            try:
                rep = run_digest_job(digest_hour=current_hour)
                if rep.get("users_processed"):
                    print(f"[scheduler] digest ({current_hour:02d}:00): {rep['users_processed']} kullanıcı")
            except Exception as e:
                print(f"[scheduler] digest job HATA: {e}")
            try:
                brep = run_breach_check()
                if brep.get("results"):
                    print(f"[scheduler] breach check: {len(brep['results'])} kullanıcıya bildirim")
            except Exception as e:
                print(f"[scheduler] breach check HATA: {e}")

    sch.add_job(
        _job_wrapper,
        "cron",
        minute=minute,
        id="hourly_notify",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    sch.start()
    _scheduler = sch
    default_h = int(os.environ.get("NOTIFY_HOUR", "9"))
    print(
        f"[scheduler] saatlik bildirim job'u planlandı "
        f"(dk {minute:02d}, digest default {default_h:02d}:00, {sch.timezone})"
    )


if __name__ == "__main__":
    # Debug modunda reloader iki process çalıştırır — sadece ikinci (main) process
    # init_db + scheduler çalıştırmalı. WERKZEUG_RUN_MAIN sadece reloader child'ında set olur.
    is_reloader_parent = os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    # Varsayılan KAPALI (0). Debugger'ı yalnızca yerel geliştirmede FLASK_DEBUG=1
    # ile açın. Prod/staging gunicorn kullanır (Dockerfile) ve bu yola hiç girmez;
    # bu satır "biri prod'da elle python app.py çalıştırırsa" kalkanıdır.
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    if not (debug_mode and is_reloader_parent):
        with app.app_context():
            init_db()
        start_scheduler()
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
else:
    # WSGI (gunicorn vb.) import yolu: init_db + scheduler tek seferlik
    with app.app_context():
        init_db()
    start_scheduler()
