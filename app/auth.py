"""认证 / 权限装饰器（基于 Flask session）"""
from functools import wraps

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .models import query_one, execute


def hash_password(pw: str) -> str:
    return generate_password_hash(pw)


def verify_password(stored: str, pw: str) -> bool:
    return check_password_hash(stored, pw)


def login_user(user: dict):
    session["uid"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["student_id"] = user.get("student_id")


def logout_user():
    session.clear()


def current_user():
    if "uid" not in session:
        return None
    return {
        "id": session["uid"],
        "username": session.get("username"),
        "role": session.get("role"),
        "student_id": session.get("student_id"),
    }


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("auth.login_page"))
        return view(*args, **kwargs)
    return wrapper


def teacher_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("auth.login_page"))
        if session.get("role") != "teacher":
            return jsonify({"error": "需要教师权限"}), 403
        return view(*args, **kwargs)
    return wrapper


def ensure_default_admin():
    """启动时确保至少存在一个 teacher 账号 admin/admin123。"""
    row = query_one("SELECT id FROM users WHERE username=?", ("admin",))
    if not row:
        execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
            ("admin", hash_password("admin123"), "teacher"),
        )
