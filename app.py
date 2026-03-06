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
from models.database import db, User, Task, TaskCompletion, Firm, Team, Invitation, ConfigBackup, init_db, _next_due_date
from services.report import generate_monthly_pdf
from services.mailer import send_report_email, send_invite_email
from services.storage import save_backup_file

try:
    import msal
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///it_tracker.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

O365_CLIENT_ID    = os.environ.get("O365_CLIENT_ID", "")
O365_CLIENT_SECRET = os.environ.get("O365_CLIENT_SECRET", "")
O365_TENANT_ID    = os.environ.get("O365_TENANT_ID", "common")
O365_REDIRECT_URI = os.environ.get("O365_REDIRECT_URI", "http://localhost:5000/auth/callback")
O365_SCOPES       = ["User.Read", "Mail.Send"]

db.init_app(app)

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

@app.route("/")
@login_required
def dashboard():
    return render_template("app.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        username = (data.get("username") or "").strip().lower()
        password = data.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            if request.is_json:
                return jsonify({"ok": True, "user": user.to_dict()})
            return redirect(url_for("dashboard"))
        if request.is_json:
            return jsonify({"ok": False, "error": "Hatalı kullanıcı adı veya şifre"}), 401
        return render_template("login.html", error="Hatalı kullanıcı adı veya şifre")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── O365 OAUTH ──
@app.route("/auth/o365")
def auth_o365():
    if not MSAL_AVAILABLE: return jsonify({"error":"pip install msal"}), 503
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
    email   = claims.get("preferred_username","")
    name    = claims.get("name", email)
    user = User.query.filter_by(o365_id=o365_id).first() or User.query.filter_by(email=email).first()
    if not user:
        inv  = Invitation.query.filter_by(email=email, used=False).first()
        user = User(username=email.split("@")[0].lower(), full_name=name, email=email, o365_id=o365_id, role=inv.role if inv else "IT Yardımcısı")
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        if inv: inv.used = True
        db.session.commit()
    else:
        user.o365_id = o365_id; user.full_name = name; db.session.commit()
    session["user_id"] = user.id
    session["o365_token"] = result.get("access_token")
    return redirect(url_for("dashboard"))

# ── TASKS ──
@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():
    uid   = session["user_id"]
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
    if not category_filter or category_filter not in ("routine", "project"):
        created_match  = db.and_(db.extract("month", Task.created_at)==month,
                                  db.extract("year",  Task.created_at)==year)
        deadline_match = db.and_(Task.deadline!=None,
                                  db.extract("month", Task.deadline)==month,
                                  db.extract("year",  Task.deadline)==year)
        oq = Task.query.filter(
            Task.user_id==uid,
            Task.category.notin_(["routine", "project"]),
            db.or_(created_match, deadline_match)
        )
        if firm_filter:     oq = oq.filter_by(firm=firm_filter)
        if category_filter: oq = oq.filter_by(category=category_filter)
        result += oq.order_by(Task.created_at.desc()).all()

    return jsonify([t.to_dict(month=month, year=year) for t in result])

@app.route("/api/tasks", methods=["POST"])
@login_required
def create_task():
    if request.content_type and "multipart" in request.content_type:
        data = request.form; backup_file = request.files.get("backup_file")
    else:
        data = request.get_json(); backup_file = None
    category = data.get("category","other")
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
    task = Task(user_id=session["user_id"], title=data["title"], category=category,
                period=period, firm=data.get("firm",""), team=data.get("team",""),
                notes=data.get("notes",""), deadline=deadline, next_due=next_due,
                checklist=_json.dumps(cl_items),
                checklist_done=_json.dumps([False]*len(cl_items)))
    db.session.add(task); db.session.flush()
    if backup_file and backup_file.filename:
        fp = save_backup_file(backup_file, task.id, session["user_id"])
        db.session.add(ConfigBackup(task_id=task.id, user_id=session["user_id"],
            filename=backup_file.filename, file_path=fp, device=data.get("backup_device","")))
    db.session.commit()
    return jsonify(task.to_dict()), 201

@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@login_required
def update_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=session["user_id"]).first_or_404()
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
    db.session.commit()
    month_val = data.get("month", date.today().month)
    year_val  = data.get("year",  date.today().year)
    return jsonify(task.to_dict(month=month_val, year=year_val))

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=session["user_id"]).first_or_404()
    db.session.delete(task); db.session.commit(); return jsonify({"ok":True})

# ── CONFIG BACKUP ──
@app.route("/api/backups")
@login_required
def list_backups():
    bkps = ConfigBackup.query.filter_by(user_id=session["user_id"]).order_by(ConfigBackup.uploaded_at.desc()).all()
    return jsonify([b.to_dict() for b in bkps])

@app.route("/api/backups/<int:bid>/download")
@login_required
def download_backup(bid):
    b = ConfigBackup.query.filter_by(id=bid, user_id=session["user_id"]).first_or_404()
    return send_file(b.file_path, as_attachment=True, download_name=b.filename)

# ── STATS ──
@app.route("/api/stats")
@login_required
def stats():
    uid   = session["user_id"]
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

# ── FIRMS & TEAMS ──
@app.route("/api/firms")
@login_required
def get_firms(): return jsonify([f.to_dict() for f in Firm.query.order_by(Firm.name).all()])

@app.route("/api/firms", methods=["POST"])
@admin_required
def create_firm():
    data=request.get_json(); firm=Firm(name=data["name"],slug=data["name"].lower().replace(" ","_")); db.session.add(firm); db.session.commit(); return jsonify(firm.to_dict()),201

@app.route("/api/firms/<int:fid>/teams")
@login_required
def get_teams(fid): return jsonify([t.to_dict() for t in Team.query.filter_by(firm_id=fid).order_by(Team.name).all()])

@app.route("/api/firms/<int:fid>/teams", methods=["POST"])
@admin_required
def create_team(fid):
    data=request.get_json(); t=Team(firm_id=fid,name=data["name"]); db.session.add(t); db.session.commit(); return jsonify(t.to_dict()),201

@app.route("/api/teams/<int:tid>", methods=["DELETE"])
@admin_required
def delete_team(tid):
    t=Team.query.get_or_404(tid); db.session.delete(t); db.session.commit(); return jsonify({"ok":True})

# ── ADMIN ──
@app.route("/api/admin/users")
@admin_required
def admin_users(): return jsonify([u.to_dict() for u in User.query.order_by(User.created_at.desc()).all()])

@app.route("/api/admin/users/<int:uid>", methods=["PATCH"])
@admin_required
def admin_update_user(uid):
    user=User.query.get_or_404(uid); data=request.get_json()
    for f in ("role","is_admin","firm","active"):
        if f in data: setattr(user,f,data[f])
    db.session.commit(); return jsonify(user.to_dict())

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    u=User.query.get_or_404(uid); db.session.delete(u); db.session.commit(); return jsonify({"ok":True})

# ── INVITE ──
@app.route("/api/admin/invite", methods=["POST"])
@admin_required
def invite_user():
    data=request.get_json(); email=data.get("email","").strip().lower()
    if not email: return jsonify({"error":"Mail boş"}),400
    if User.query.filter_by(email=email).first(): return jsonify({"error":"Kayıtlı"}),409
    Invitation.query.filter_by(email=email,used=False).delete()
    token=secrets.token_urlsafe(32)
    inv=Invitation(email=email,full_name=data.get("full_name",""),role=data.get("role","IT Yardımcısı"),
                   firm=data.get("firm",""),token=token,expires_at=datetime.utcnow()+timedelta(days=7),invited_by=session["user_id"])
    db.session.add(inv); db.session.commit()
    url=f"{request.host_url}register?token={token}"
    result=send_invite_email(email,data.get("full_name",""),url,data.get("role",""))
    return jsonify({"ok":result.get("ok"),"invite_url":url})

@app.route("/register", methods=["GET","POST"])
def register():
    token=request.args.get("token") or (request.get_json() or {}).get("token")
    inv=Invitation.query.filter_by(token=token,used=False).first()
    if not inv or inv.expires_at<datetime.utcnow(): return render_template("error.html",msg="Geçersiz davet"),400
    if request.method=="POST":
        data=request.get_json() or request.form
        user=User(username=data.get("username","").strip().lower(),full_name=inv.full_name,email=inv.email,role=inv.role,firm=inv.firm)
        user.set_password(data.get("password",""))
        db.session.add(user); inv.used=True; db.session.commit()
        session["user_id"]=user.id
        return jsonify({"ok":True}) if request.is_json else redirect(url_for("dashboard"))
    return render_template("register.html",invitation=inv)

# ── REPORT ──
@app.route("/api/report/pdf")
@login_required
def download_report():
    user=db.session.get(User, session["user_id"]); month=request.args.get("month",date.today().month,type=int); year=request.args.get("year",date.today().year,type=int)
    tasks=Task.query.filter(Task.user_id==user.id,db.extract("month",Task.created_at)==month,db.extract("year",Task.created_at)==year).all()
    pdf=generate_monthly_pdf(user,tasks,month,year)
    resp = send_file(pdf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"IT_Rapor_{user.username}_{year}_{month:02d}.pdf")
    resp.headers["Content-Disposition"] = f"inline; filename=IT_Rapor_{user.username}_{year}_{month:02d}.pdf"
    return resp

@app.route("/api/report/send", methods=["POST"])
@login_required
def send_report():
    user=db.session.get(User, session["user_id"]); data=request.get_json() or {}
    month=data.get("month",date.today().month); year=data.get("year",date.today().year)
    tasks=Task.query.filter(Task.user_id==user.id,db.extract("month",Task.created_at)==month,db.extract("year",Task.created_at)==year).all()
    pdf=generate_monthly_pdf(user,tasks,month,year)
    return jsonify(send_report_email(user,pdf,month,year,cc=data.get("cc"),o365_token=session.get("o365_token")))

@app.route("/api/me")
@login_required
def me(): return jsonify(db.session.get(User, session["user_id"]).to_dict())

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
@login_required
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
@login_required
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

if __name__ == "__main__":
    with app.app_context(): init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
