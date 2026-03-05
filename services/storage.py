"""Config Backup Dosya Depolama Servisi"""
import os, uuid
from werkzeug.utils import secure_filename

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/srv/it_tracker/backups")
ALLOWED_EXTENSIONS = {".cfg",".conf",".txt",".bin",".xml",".json",".tar",".gz",".zip",".backup"}

def save_backup_file(file_obj, task_id: int, user_id: int) -> str:
    """Yüklenen dosyayı güvenli isimle kaydeder, tam yolu döner."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    orig  = secure_filename(file_obj.filename)
    ext   = os.path.splitext(orig)[1].lower()
    fname = f"task{task_id}_user{user_id}_{uuid.uuid4().hex[:8]}{ext}"
    path  = os.path.join(BACKUP_DIR, fname)
    file_obj.save(path)
    return path

def get_backup_path(filename: str) -> str:
    return os.path.join(BACKUP_DIR, filename)
