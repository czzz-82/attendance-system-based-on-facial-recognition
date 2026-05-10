"""登录、注销、注册（教师可创建学生账号）"""
from flask import Blueprint, jsonify, render_template, request, session, redirect, url_for

from ..auth import (current_user, hash_password, login_user, logout_user,
                    teacher_required, verify_password)
from ..models import execute, query_one

bp_auth = Blueprint("auth", __name__)


@bp_auth.route("/login", methods=["GET"])
def login_page():
    if "uid" in session:
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html")


@bp_auth.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    user = query_one("SELECT * FROM users WHERE username=?", (username,))
    if not user or not verify_password(user["password_hash"], password):
        return jsonify({"error": "用户名或密码错误"}), 401
    login_user(user)
    return jsonify({"ok": True, "user": current_user()})


@bp_auth.route("/api/logout", methods=["POST"])
def api_logout():
    logout_user()
    return jsonify({"ok": True})


@bp_auth.route("/api/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    return jsonify({"user": user})


@bp_auth.route("/api/users", methods=["POST"])
@teacher_required
def api_create_user():
    """教师可为学生创建账号；学生账号 username 默认为学号。"""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or "123456"
    role = data.get("role") or "student"
    student_id = data.get("student_id")
    if role not in ("teacher", "student"):
        return jsonify({"error": "role 不合法"}), 400
    if not username:
        return jsonify({"error": "username 必填"}), 400
    if query_one("SELECT id FROM users WHERE username=?", (username,)):
        return jsonify({"error": "用户名已存在"}), 400
    uid = execute(
        "INSERT INTO users(username,password_hash,role,student_id) VALUES (?,?,?,?)",
        (username, hash_password(password), role, student_id),
    )
    return jsonify({"ok": True, "id": uid})
