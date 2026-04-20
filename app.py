"""
IT Görev Takip Sistemi — Flask Backend v2
Yenilikler: O365 OAuth2, çok kullanıcı, davet sistemi, Config Backup, Admin Panel
"""
import os
from dotenv import load_dotenv
load_dotenv()
import secrets
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from functools import wraps
from datetime import datetime, date, timedelta
import json as _json
from models.database import db, User, Task, TaskCompletion, Firm, Team, Invitation, ConfigBackup, BoardCard, BoardComment, AuditLog, init_db, _next_due_date, SLA_HOURS, _sla_target_hours
from services.report import generate_monthly_pdf
from services.mailer import send_report_email, send_invite_email
from services.storage import save_backup_file
from services.notifier import run_digest_job, collect_user_alerts

try:
    import msal
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# Nginx reverse proxy arkasında HTTPS ve gerçek IP'yi doğru al
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///it_tracker.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

O365_CLIENT_ID    = os.environ.get("O365_CLIENT_ID", "")
O365_CLIENT_SECRET = os.environ.get("O365_CLIENT_SECRET", "")
O365_TENANT_ID    = os.environ.get("O365_TENANT_ID", "common")
O365_REDIRECT_URI = os.environ.get("O365_REDIRECT_URI", "http://localhost:5000/auth/callback")
O365_SCOPES       = ["User.Read", "Mail.Send"]

db.init_app(app)

ALLOWED_PRIORITIES = {"düşük", "orta", "yüksek"}
def _normalize_priority(val):
    v = (val or "").strip().lower()
    return v if v in ALLOWED_PRIORITIES else "orta"

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login")) if not request.is_json else (jsonify({"error": "Unauthorized"}), 401)
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

def log_audit(actor, action, *, entity_type="", entity_id=None,
              target_user=None, firm="", summary="", details=None):
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
    - requested_uid yoksa: kendi id'si
    - requested_uid == kendi id'si: kendi id'si
    - super_admin: herkesin id'sini kullanabilir
    - it_director: yalnızca kendi firmasındaki aktif kullanıcıların id'si
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
    if me.permission_level == "it_director" and target.firm == me.firm:
        return target.id, None
    return None, (jsonify({"error": "Bu kullanıcının verilerine erişim yetkiniz yok"}), 403)

@app.route("/")
@login_required
def dashboard():
    return render_template("app.html")

@app.route("/sw.js")
def service_worker():
    resp = send_file(
        os.path.join(app.root_path, "static", "sw.js"),
        mimetype="application/javascript"
    )
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        username = (data.get("username") or "").strip().lower()
        password = data.get("password") or ""
        # Sadece admin kullanıcı local girişe izin verilir
        admin_username = os.environ.get("ADMIN_USERNAME", "levent.can")
        if username != admin_username:
            if request.is_json:
                return jsonify({"ok": False, "error": "Lütfen Microsoft 365 ile giriş yapın"}), 403
            return render_template("login.html", admin_mode=True,
                                   error="Bu kullanıcı için Microsoft 365 ile giriş gereklidir")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            if request.is_json:
                return jsonify({"ok": True, "user": user.to_dict()})
            return redirect(url_for("dashboard"))
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
    if not MSAL_AVAILABLE: return jsonify({"error":"pip install msal"}), 503
    # Davet token'ını session'a kaydet (register sayfasından geliyorsa)
    invite_token = request.args.get("invite")
    if invite_token:
        session["invite_token"] = invite_token
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    msal_app = msal.ConfidentialClientApplication(
        O365_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{O365_TENANT_ID}",
        client_credential=O365_CLIENT_SECRET)
    return redirect(msal_app.get_authorization_request_url(O365_SCOPES, state=state, redirect_uri=O365_REDIRECT_URI))

@app.route("/auth/callback")
def auth_callback():
    if not MSAL_AVAILABLE: return "MSAL yok", 503
    code = request.args.get("code")
    if request.args.get("state") != session.pop("oauth_state", None): return "Geçersiz state", 400
    msal_app = msal.ConfidentialClientApplication(
        O365_CLIENT_ID, authority=f"https://login.microsoftonline.com/{O365_TENANT_ID}",
        client_credential=O365_CLIENT_SECRET)
    result = msal_app.acquire_token_by_authorization_code(code, scopes=O365_SCOPES, redirect_uri=O365_REDIRECT_URI)
    if "error" in result: return f"Hata: {result.get('error_description','')}", 400
    claims  = result.get("id_token_claims", {})
    o365_id = claims.get("oid")
    email   = claims.get("preferred_username","").lower()
    name    = claims.get("name", email)

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
            return render_template("error.html",
                msg=f"'{email}' adresi için geçerli bir davet bulunamadı. "
                    "Lütfen sistem yöneticinizden davet isteyin.")

        role = inv.role if inv else "IT Sorumlusu"
        firm = inv.firm if inv else ""
        # Permission level: role_label'dan türet
        perm_map = {"Super Admin": "super_admin", "IT Müdürü": "it_director", "IT Yöneticisi": "it_manager", "IT Specialist": "it_specialist", "Junior": "junior"}
        perm = perm_map.get(role, "junior")
        user = User(
            username=email.split("@")[0].lower(),
            full_name=name, email=email,
            o365_id=o365_id, role=role, firm=firm,
            permission_level=perm,
            is_admin=perm in ("super_admin", "it_director", "it_manager")
        )
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        if inv:
            inv.used = True
        db.session.commit()
    else:
        # Mevcut kullanıcı — o365_id ve ad güncelle
        user.o365_id  = o365_id
        user.full_name = name
        db.session.commit()

    session["user_id"]    = user.id
    session["o365_token"] = result.get("access_token")
    session.pop("invite_token", None)
    return redirect(url_for("dashboard"))

# ── FIRM USERS (v4.2 — director+) ──
@app.route("/api/firm/users")
@login_required
def firm_users():
    """Director+ için firma bazlı kullanıcı listesi (dashboard dropdown)."""
    me = _current_user()
    if not me:
        return jsonify({"error": "Unauthorized"}), 401
    # Sadece director+ bu listeyi çeker; diğerleri sadece kendilerini görür
    if me.is_super_admin:
        q = User.query.filter_by(active=True).order_by(User.full_name)
    elif me.permission_level == "it_director":
        q = User.query.filter_by(active=True, firm=me.firm).order_by(User.full_name)
    else:
        return jsonify([{"id": me.id, "full_name": me.full_name, "firm": me.firm}])
    return jsonify([{"id": u.id, "full_name": u.full_name, "firm": u.firm,
                     "role": u.role, "permission_level": u.permission_level}
                    for u in q.all()])

# ── TASKS ──
@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err: return err
    month = request.args.get("month", date.today().month, type=int)
    year  = request.args.get("year",  date.today().year,  type=int)
    firm_filter     = request.args.get("firm")
    category_filter = request.args.get("category")

    result = []

    # 1) Rutin görevler: her ayın görünümünde listelenir, tamamlanma o aya özel
    if not category_filter or category_filter == "routine":
        rq = Task.query.filter_by(user_id=uid, category="routine")
        if firm_filter: rq = rq.filter_by(firm=firm_filter)
        result += rq.order_by(Task.created_at.desc()).all()

    # 2) Proje görevleri: tamamlanmamışlar her ayda görünür;
    #    tamamlanmışlar yalnızca tamamlandıkları ayda görünür
    if not category_filter or category_filter == "project":
        pq = Task.query.filter_by(user_id=uid, category="project")
        if firm_filter: pq = pq.filter_by(firm=firm_filter)
        for t in pq.order_by(Task.created_at.desc()).all():
            if not t.is_done:
                result.append(t)
            elif t.completed_at:
                if t.completed_at.month == month and t.completed_at.year == year:
                    result.append(t)

    # 3) Diğer görevler (support, infra, backup, other): o aya ait olanlar
    #    + tamamlanmamış olup önceki aylarda oluşturulmuş görevler (carry-over)
    if not category_filter or category_filter not in ("routine", "project"):
        created_match  = db.and_(db.extract("month", Task.created_at)==month,
                                  db.extract("year",  Task.created_at)==year)
        deadline_match = db.and_(Task.deadline!=None,
                                  db.extract("month", Task.deadline)==month,
                                  db.extract("year",  Task.deadline)==year)
        # Tamamlanmamış ve önceki aylarda oluşturulmuş görevler bir sonraki aya taşınır
        carry_over = db.and_(
            Task.is_done == False,
            db.or_(
                db.extract("year",  Task.created_at) < year,
                db.and_(
                    db.extract("year",  Task.created_at) == year,
                    db.extract("month", Task.created_at) <  month
                )
            )
        )
        oq = Task.query.filter(
            Task.user_id==uid,
            Task.category.notin_(["routine", "project"]),
            db.or_(created_match, deadline_match, carry_over)
        )
        if firm_filter:     oq = oq.filter_by(firm=firm_filter)
        if category_filter: oq = oq.filter_by(category=category_filter)
        result += oq.order_by(Task.created_at.desc()).all()

    return jsonify([t.to_dict(month=month, year=year) for t in result])

@app.route("/api/tasks", methods=["POST"])
@login_required
def create_task():
    # Junior sadece anlık görev oluşturabilir
    me = _current_user()
    if me and me.permission_level == "junior":
        cat = (request.form if request.content_type and "multipart" in request.content_type else request.get_json() or {}).get("category", "other")
        if cat in ("routine", "project", "backup"):
            return jsonify({"error": "Bu görev türünü oluşturma yetkiniz yok"}), 403
    if request.content_type and "multipart" in request.content_type:
        data = request.form; backup_file = request.files.get("backup_file")
    else:
        data = request.get_json(); backup_file = None
    # v4.3 — atama: director+ başka kullanıcıya görev oluşturabilir
    target_uid, err = _resolve_scope_uid(me, data.get("user_id"))
    if err: return err
    assigned_by = me.id if target_uid != me.id else None
    # manager_note yalnızca director+ tarafından atanabilir
    manager_note = (data.get("manager_note", "") or "").strip() if me.is_director_or_above else ""
    category = data.get("category","other")
    priority = _normalize_priority(data.get("priority"))
    period   = data.get("period","Tek Seferlik")
    deadline_raw = data.get("deadline")
    deadline = datetime.fromisoformat(deadline_raw).date() if deadline_raw else None
    next_due = None
    if category == "routine" and period != "Tek Seferlik":
        from models.database import _next_due_date
        next_due = _next_due_date(period)
        if not deadline:
            deadline = next_due
    cl_raw = data.get("checklist", "[]")
    if isinstance(cl_raw, list): cl_raw = _json.dumps(cl_raw)
    cl_items = _json.loads(cl_raw) if isinstance(cl_raw, str) else []
    task = Task(user_id=target_uid, title=data["title"], category=category,
                priority=priority,
                period=period, firm=data.get("firm",""), team=data.get("team",""),
                notes=data.get("notes",""), deadline=deadline, next_due=next_due,
                checklist=_json.dumps(cl_items),
                checklist_done=_json.dumps([False]*len(cl_items)),
                manager_note=manager_note,
                assigned_by=assigned_by)
    db.session.add(task); db.session.flush()
    if backup_file and backup_file.filename:
        fp = save_backup_file(backup_file, task.id, target_uid)
        db.session.add(ConfigBackup(task_id=task.id, user_id=target_uid,
            filename=backup_file.filename, file_path=fp, device=data.get("backup_device",""),
            file_size=os.path.getsize(fp)))
    # v4.4 — audit log
    target = db.session.get(User, target_uid)
    if assigned_by:
        log_audit(me, "task.assign", entity_type="task", entity_id=task.id,
                  target_user=target, firm=task.firm,
                  summary=f"'{task.title}' görevi {target.full_name if target else '?'} kişisine atandı",
                  details={"title": task.title, "category": task.category, "manager_note": bool(manager_note)})
    else:
        log_audit(me, "task.create", entity_type="task", entity_id=task.id,
                  firm=task.firm,
                  summary=f"'{task.title}' görevi oluşturuldu ({task.category})")
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
        if not (me.is_super_admin or (me.permission_level == "it_director" and owner and owner.firm == me.firm)):
            return jsonify({"error": "Bu görevi düzenleme yetkiniz yok"}), 403
    data = request.get_json()
    if "is_done" in data:
        if task.category == "routine" and task.period != "Tek Seferlik":
            # Rutin görevler: TaskCompletion kaydı oluştur/sil
            month = data.get("month", date.today().month)
            year  = data.get("year",  date.today().year)
            comp  = TaskCompletion.query.filter_by(task_id=task.id, year=year, month=month).first()
            if data["is_done"] and not comp:
                db.session.add(TaskCompletion(
                    task_id=task.id, year=year, month=month,
                    completed_by=session["user_id"]
                ))
                task.last_completed = datetime.utcnow()
            elif not data["is_done"] and comp:
                db.session.delete(comp)
        else:
            task.is_done     = data["is_done"]
            task.completed_at = datetime.utcnow() if data["is_done"] else None
    if "title"    in data: task.title    = data["title"]
    if "category" in data: task.category = data["category"]
    if "priority" in data: task.priority = _normalize_priority(data["priority"])
    if "period"   in data: task.period   = data["period"]
    if "firm"     in data: task.firm     = data["firm"]
    if "team"     in data: task.team     = data["team"]
    if "notes"    in data: task.notes    = data["notes"]
    if "deadline" in data: task.deadline = datetime.fromisoformat(data["deadline"]).date() if data["deadline"] else None
    if "checklist" in data:
        cl = data["checklist"] if isinstance(data["checklist"], list) else _json.loads(data["checklist"])
        task.checklist = _json.dumps(cl)
        cld = task.get_checklist_done()
        while len(cld) < len(cl): cld.append(False)
        task.checklist_done = _json.dumps(cld[:len(cl)])
    if "checklist_done" in data:
        cld = data["checklist_done"] if isinstance(data["checklist_done"], list) else _json.loads(data["checklist_done"])
        task.checklist_done = _json.dumps(cld)
    if "project_status" in data: task.project_status = data["project_status"]
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
        log_audit(me, "task.manager_note", entity_type="task", entity_id=task.id,
                  target_user=owner, firm=task.firm,
                  summary=f"'{task.title}' görevine IT Müdürü notu {'eklendi/güncellendi' if task.manager_note else 'silindi'}",
                  details={"before": old_manager_note, "after": task.manager_note})
    if "is_done" in data:
        log_audit(me, "task.complete" if data["is_done"] else "task.reopen",
                  entity_type="task", entity_id=task.id, target_user=owner, firm=task.firm,
                  summary=f"'{task.title}' görevi {'tamamlandı' if data['is_done'] else 'yeniden açıldı'}")
    elif me.id != task.user_id:  # başka biri düzenliyorsa (director+)
        log_audit(me, "task.update", entity_type="task", entity_id=task.id,
                  target_user=owner, firm=task.firm,
                  summary=f"'{task.title}' görevi güncellendi")
    db.session.commit()
    month_val = data.get("month", date.today().month)
    year_val  = data.get("year",  date.today().year)
    return jsonify(task.to_dict(month=month_val, year=year_val))

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    me = _current_user()
    task = Task.query.get_or_404(task_id)
    owner = db.session.get(User, task.user_id)
    if task.user_id != me.id:
        if not (me.is_super_admin or (me.permission_level == "it_director" and owner and owner.firm == me.firm)):
            return jsonify({"error": "Bu görevi silme yetkiniz yok"}), 403
    log_audit(me, "task.delete", entity_type="task", entity_id=task.id,
              target_user=owner, firm=task.firm,
              summary=f"'{task.title}' görevi silindi")
    db.session.delete(task); db.session.commit(); return jsonify({"ok":True})

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
    fp = save_backup_file(backup_file, task.id, session["user_id"])
    b = ConfigBackup(filename=backup_file.filename, file_path=fp,
                     device=request.form.get("backup_device", ""),
                     task_id=task.id, user_id=session["user_id"],
                     file_size=os.path.getsize(fp))
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201

# ── STATS ──
@app.route("/api/stats")
@login_required
def stats():
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err: return err
    month = request.args.get("month", date.today().month, type=int)
    year  = request.args.get("year",  date.today().year,  type=int)

    # Aynı mantık: rutin + proje (aktif) + ay bazlı diğer
    created_match  = db.and_(db.extract("month", Task.created_at)==month,
                              db.extract("year",  Task.created_at)==year)
    deadline_match = db.and_(Task.deadline!=None,
                              db.extract("month", Task.deadline)==month,
                              db.extract("year",  Task.deadline)==year)
    routines = Task.query.filter_by(user_id=uid, category="routine").all()
    projects = Task.query.filter_by(user_id=uid, category="project").filter(
        db.or_(Task.is_done==False,
               db.and_(Task.completed_at!=None,
                       db.extract("month", Task.completed_at)==month,
                       db.extract("year",  Task.completed_at)==year))
    ).all()
    others   = Task.query.filter(Task.user_id==uid,
                                  Task.category.notin_(["routine","project"]),
                                  db.or_(created_match, deadline_match)).all()

    tasks = routines + projects + others

    # Rutin is_done: TaskCompletion'dan
    completed_ids = {c.task_id for c in TaskCompletion.query.filter_by(year=year, month=month).all()}
    def _is_done(t):
        if t.category == "routine" and t.period != "Tek Seferlik":
            return t.id in completed_ids
        return t.is_done

    total = len(tasks)
    done  = sum(1 for t in tasks if _is_done(t))
    by_cat={};by_team={};by_firm={}
    for t in tasks:
        by_cat[t.category]  = by_cat.get(t.category,  0) + 1
        by_team[t.team]     = by_team.get(t.team,     0) + 1
        by_firm[t.firm]     = by_firm.get(t.firm,     0) + 1
    overdue = sum(1 for t in tasks if not _is_done(t) and t.deadline and t.deadline < date.today())
    return jsonify({"total":total,"done":done,"pending":total-done,"overdue":overdue,
                    "by_category":by_cat,"by_team":by_team,"by_firm":by_firm,
                    "completion_rate":round(done/total*100,1) if total else 0})

# ── v4.5 SLA STATS ──
@app.route("/api/sla/stats")
@login_required
def sla_stats():
    """v4.5 — Destek talepleri için SLA metrikleri.
    Query: month, year, user_id (director+ için firma bazlı)"""
    me = _current_user()
    uid, err = _resolve_scope_uid(me, request.args.get("user_id", type=int))
    if err: return err
    month = request.args.get("month", date.today().month, type=int)
    year  = request.args.get("year",  date.today().year,  type=int)

    # Destek görevleri — o ay içinde oluşturulanlar
    q = Task.query.filter(
        Task.user_id == uid,
        Task.category == "support",
        db.extract("month", Task.created_at) == month,
        db.extract("year",  Task.created_at) == year,
    )
    tasks = q.all()
    now = datetime.utcnow()

    totals = {"total": 0, "open": 0, "resolved": 0, "breached": 0,
              "resolved_on_time": 0, "avg_resolution_hours": 0.0}
    by_priority = {}  # key: priority → dict
    sum_resolution = 0.0
    resolved_count = 0

    for t in tasks:
        prio = (t.priority or "orta").strip().lower()
        target_h = _sla_target_hours(prio)
        deadline_dt = t.created_at + timedelta(hours=target_h) if t.created_at else None
        bucket = by_priority.setdefault(prio, {
            "total": 0, "open": 0, "resolved": 0, "breached": 0,
            "resolved_on_time": 0, "target_hours": target_h,
            "avg_resolution_hours": 0.0, "_sum_resolution": 0.0, "_resolved_cnt": 0,
        })
        totals["total"] += 1
        bucket["total"] += 1

        if t.is_done and t.completed_at:
            totals["resolved"] += 1
            bucket["resolved"] += 1
            res_h = (t.completed_at - t.created_at).total_seconds() / 3600.0
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
        b.pop("_sum_resolution", None); b.pop("_resolved_cnt", None)
        out_priority[p] = b

    return jsonify({
        **totals,
        "by_priority": out_priority,
        "sla_targets": SLA_HOURS,
        "month": month, "year": year,
    })

# ── FIRMS & TEAMS ──
@app.route("/api/firms")
@login_required
def get_firms(): return jsonify([f.to_dict() for f in Firm.query.order_by(Firm.name).all()])

@app.route("/api/firms", methods=["POST"])
@manager_required
def create_firm():
    data=request.get_json(); firm=Firm(name=data["name"],slug=data["name"].lower().replace(" ","_")); db.session.add(firm); db.session.commit(); return jsonify(firm.to_dict()),201

@app.route("/api/firms/<int:fid>/teams")
@login_required
def get_teams(fid): return jsonify([t.to_dict() for t in Team.query.filter_by(firm_id=fid).order_by(Team.name).all()])

@app.route("/api/firms/<int:fid>/teams", methods=["POST"])
@manager_required
def create_team(fid):
    data=request.get_json(); t=Team(firm_id=fid,name=data["name"]); db.session.add(t); db.session.commit(); return jsonify(t.to_dict()),201

@app.route("/api/teams/<int:tid>", methods=["DELETE"])
@manager_required
def delete_team(tid):
    t=Team.query.get_or_404(tid); db.session.delete(t); db.session.commit(); return jsonify({"ok":True})

# ── ADMIN ──
@app.route("/api/admin/users")
@manager_required
def admin_users(): return jsonify([u.to_dict() for u in User.query.order_by(User.created_at.desc()).all()])

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
        if f in data: setattr(target, f, data[f])
    # v4.4 — audit
    log_audit(me, "user.update", entity_type="user", entity_id=target.id,
              target_user=target, firm=target.firm,
              summary=f"{target.full_name} kullanıcı bilgileri güncellendi",
              details={k: data.get(k) for k in ("permission_level","role","firm","active","can_access_board") if k in data})
    db.session.commit(); return jsonify(target.to_dict())

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@manager_required
def admin_delete_user(uid):
    me = _current_user()
    target = User.query.get_or_404(uid)
    # IT Yöneticisi super_admin veya IT Müdürü silemez
    if not me.is_super_admin and target.permission_level in ("super_admin", "it_director"):
        return jsonify({"error": "Bu kullanıcıyı silme yetkiniz yok"}), 403
    log_audit(me, "user.delete", entity_type="user", entity_id=target.id,
              target_user=target, firm=target.firm,
              summary=f"{target.full_name} kullanıcı silindi")
    db.session.delete(target); db.session.commit(); return jsonify({"ok":True})

# ── INVITE ──
@app.route("/api/admin/invite", methods=["POST"])
@manager_required
def invite_user():
    me = _current_user()
    data=request.get_json(); email=data.get("email","").strip().lower()
    if not email: return jsonify({"error":"Mail boş"}),400
    if User.query.filter_by(email=email).first(): return jsonify({"error":"Kayıtlı"}),409
    perm = data.get("permission_level", "junior")
    # IT Yöneticisi super_admin veya it_director davet edemez
    if not me.is_super_admin and perm in ("super_admin", "it_director"):
        return jsonify({"error": "Bu rolü davet etme yetkiniz yok"}), 403
    Invitation.query.filter_by(email=email,used=False).delete()
    token=secrets.token_urlsafe(32)
    role_label = {"super_admin": "Super Admin", "it_director": "IT Müdürü", "it_manager": "IT Yöneticisi", "it_specialist": "IT Specialist", "junior": "Junior"}.get(perm, "Junior")
    inv=Invitation(email=email,full_name=data.get("full_name",""),role=role_label,
                   firm=data.get("firm",""),token=token,expires_at=datetime.utcnow()+timedelta(days=7),invited_by=session["user_id"])
    db.session.add(inv); db.session.flush()
    log_audit(me, "user.invite", entity_type="invitation", entity_id=inv.id,
              firm=inv.firm,
              summary=f"{email} adresine {role_label} rolü için davet gönderildi",
              details={"email": email, "role": role_label, "firm": inv.firm})
    db.session.commit()
    url=f"{request.host_url}register?token={token}"
    result=send_invite_email(email,data.get("full_name",""),url,role_label)
    return jsonify({"ok":result.get("ok"),"invite_url":url,"permission_level":perm})

@app.route("/api/admin/invitations")
@manager_required
def list_invitations():
    invs = Invitation.query.filter_by(used=False).order_by(Invitation.created_at.desc()).all()
    return jsonify([i.to_dict() for i in invs])

@app.route("/api/admin/invitations/<int:inv_id>", methods=["DELETE"])
@manager_required
def cancel_invitation(inv_id):
    inv = Invitation.query.get_or_404(inv_id)
    if inv.used: return jsonify({"error":"Zaten kullanılmış"}),400
    db.session.delete(inv); db.session.commit()
    return jsonify({"ok":True})

@app.route("/api/admin/invitations/<int:inv_id>/resend", methods=["POST"])
@manager_required
def resend_invitation(inv_id):
    inv = Invitation.query.get_or_404(inv_id)
    if inv.used: return jsonify({"error":"Zaten kullanılmış"}),400
    inv.token = secrets.token_urlsafe(32)
    inv.expires_at = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    url = f"{request.host_url}register?token={inv.token}"
    result = send_invite_email(inv.email, inv.full_name, url, inv.role)
    return jsonify({"ok":result.get("ok"),"invite_url":url})

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
    if err: return err
    user = db.session.get(User, uid)
    month=request.args.get("month",date.today().month,type=int); year=request.args.get("year",date.today().year,type=int)
    tasks=Task.query.filter(Task.user_id==user.id,db.extract("month",Task.created_at)==month,db.extract("year",Task.created_at)==year).all()
    pdf=generate_monthly_pdf(user,tasks,month,year)
    resp = send_file(pdf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"IT_Rapor_{user.username}_{year}_{month:02d}.pdf")
    resp.headers["Content-Disposition"] = f"inline; filename=IT_Rapor_{user.username}_{year}_{month:02d}.pdf"
    return resp

@app.route("/api/report/send", methods=["POST"])
@manager_required
def send_report():
    me = _current_user()
    data=request.get_json() or {}
    uid, err = _resolve_scope_uid(me, data.get("user_id"))
    if err: return err
    user = db.session.get(User, uid)
    month=data.get("month",date.today().month); year=data.get("year",date.today().year)
    tasks=Task.query.filter(Task.user_id==user.id,db.extract("month",Task.created_at)==month,db.extract("year",Task.created_at)==year).all()
    pdf=generate_monthly_pdf(user,tasks,month,year)
    return jsonify(send_report_email(user,pdf,month,year,cc=data.get("cc"),o365_token=session.get("o365_token")))

@app.route("/api/me")
@login_required
def me(): return jsonify(db.session.get(User, session["user_id"]).to_dict())

# ── v4.4 AUDIT LOG ──
@app.route("/api/audit")
@director_required
def list_audit():
    """Denetim kayıtları — director+ için.
    Query: start, end (YYYY-MM-DD); action; actor_id; target_user_id; firm; limit (max 500), offset"""
    me = _current_user()
    q = AuditLog.query
    # Firma kapsamı: super_admin tümünü görür, director sadece kendi firmasını
    if not me.is_super_admin:
        q = q.filter(AuditLog.firm == (me.firm or ""))
    # Tarih aralığı
    start = request.args.get("start")
    end   = request.args.get("end")
    try:
        if start:
            q = q.filter(AuditLog.created_at >= datetime.fromisoformat(start))
        if end:
            end_dt = datetime.fromisoformat(end) + timedelta(days=1)  # inclusive gün sonu
            q = q.filter(AuditLog.created_at < end_dt)
    except ValueError:
        return jsonify({"error": "Geçersiz tarih formatı (YYYY-MM-DD bekleniyor)"}), 400
    # Filtreler
    action = request.args.get("action")
    if action: q = q.filter(AuditLog.action == action)
    actor_id = request.args.get("actor_id", type=int)
    if actor_id: q = q.filter(AuditLog.actor_id == actor_id)
    target_uid = request.args.get("target_user_id", type=int)
    if target_uid: q = q.filter(AuditLog.target_user_id == target_uid)
    firm = request.args.get("firm")
    if firm and me.is_super_admin: q = q.filter(AuditLog.firm == firm)

    limit  = min(request.args.get("limit", 200, type=int), 500)
    offset = request.args.get("offset", 0, type=int)
    total  = q.count()
    rows   = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify({"total": total, "rows": [r.to_dict() for r in rows]})

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
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if request.method == "GET":
        return jsonify({
            "smtp_host":  os.environ.get("SMTP_HOST", "smtp.office365.com"),
            "smtp_port":  os.environ.get("SMTP_PORT", "587"),
            "smtp_user":  os.environ.get("SMTP_USER", ""),
            "smtp_pass":  "••••••" if os.environ.get("SMTP_PASS") else "",
        })
    data = request.get_json() or {}
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []
        updates = {}
        if data.get("smtp_host"): updates["SMTP_HOST"] = data["smtp_host"]
        if data.get("smtp_port"): updates["SMTP_PORT"] = str(data["smtp_port"])
        if data.get("smtp_user"): updates["SMTP_USER"] = data["smtp_user"]
        if data.get("smtp_pass") and data["smtp_pass"] != "••••••":
            updates["SMTP_PASS"] = data["smtp_pass"]
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
        for key, val in updates.items():
            os.environ[key] = val
        return jsonify({"ok": True, "updated": list(updates.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/settings/smtp/test", methods=["POST"])
@super_admin_required
def test_smtp():
    import smtplib, ssl
    host = os.environ.get("SMTP_HOST", "smtp.office365.com")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER", "")
    pw   = os.environ.get("SMTP_PASS", "")
    if not user or not pw:
        return jsonify({"ok": False, "error": "Mail adresi veya şifre girilmemiş"}), 400
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo(); s.starttls(context=ctx); s.login(user, pw)
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
        if not (me.is_super_admin or (me.permission_level == "it_director" and owner and owner.firm == me.firm)):
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
    return jsonify({
        "notify_overdue":      bool(me.notify_overdue) if me.notify_overdue is not None else True,
        "notify_sla_warning":  bool(me.notify_sla_warning) if me.notify_sla_warning is not None else True,
        "notify_daily_digest": bool(me.notify_daily_digest) if me.notify_daily_digest is not None else True,
        "overdue_days":        3,
        "sla_warning_ratio":   0.25,
        "schedule":            "Her gün 09:00 (UTC)",
    })


@app.route("/api/notifications/settings", methods=["PATCH"])
@login_required
def update_notification_settings():
    me = _current_user()
    data = request.get_json() or {}
    for field in ("notify_overdue", "notify_sla_warning", "notify_daily_digest"):
        if field in data:
            setattr(me, field, bool(data[field]))
    db.session.commit()
    return jsonify({
        "ok": True,
        "notify_overdue": bool(me.notify_overdue),
        "notify_sla_warning": bool(me.notify_sla_warning),
        "notify_daily_digest": bool(me.notify_daily_digest),
    })


@app.route("/api/notifications/preview")
@login_required
def notifications_preview():
    """Kendi uyarı listesini dry-run olarak döner (mail atmaz)."""
    me = _current_user()
    groups = collect_user_alerts(me)
    return jsonify({
        "overdue":      groups["overdue"],
        "sla_warning":  groups["sla_warning"],
        "sla_breached": groups["sla_breached"],
        "total": sum(len(v) for v in groups.values()),
    })


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
#  ORTAK ALAN (BOARD) API
# ══════════════════════════════════════════════════════════
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

    hour = int(os.environ.get("NOTIFY_HOUR", "9"))
    minute = int(os.environ.get("NOTIFY_MINUTE", "0"))

    def _job_wrapper():
        with app.app_context():
            try:
                rep = run_digest_job()
                print(f"[scheduler] digest job tamamlandı: {rep.get('users_processed',0)} kullanıcı")
            except Exception as e:
                print(f"[scheduler] digest job HATA: {e}")

    sch = BackgroundScheduler(daemon=True, timezone=os.environ.get("SCHEDULER_TZ", "UTC"))
    sch.add_job(_job_wrapper, "cron", hour=hour, minute=minute, id="daily_digest",
                replace_existing=True, misfire_grace_time=3600)
    sch.start()
    _scheduler = sch
    print(f"[scheduler] günlük digest planlandı: {hour:02d}:{minute:02d} ({sch.timezone})")


if __name__ == "__main__":
    # Debug modunda reloader iki process çalıştırır — sadece ikinci (main) process
    # init_db + scheduler çalıştırmalı. WERKZEUG_RUN_MAIN sadece reloader child'ında set olur.
    is_reloader_parent = os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
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
