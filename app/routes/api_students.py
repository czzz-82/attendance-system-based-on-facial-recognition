"""学生管理 API（增删改查 + 批量导入 + 学生账号辅助创建）。

说明：这里只增强管理接口，不改动人脸识别核心算法。
"""
import os
import re
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request

import config
from .. import face_engine
from ..auth import teacher_required, login_required, current_user, hash_password
from ..models import execute, query_all, query_one

bp_students = Blueprint("students", __name__)


def allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in config.ALLOWED_IMG_EXT


def parse_student_filename(filename: str):
    """解析 学号_姓名_班级.jpg / 学号-姓名-班级.jpg。"""
    stem = Path(filename).stem.strip()
    m = re.match(r"^(\d{4,})[_\-\s]+(.+)$", stem) or re.match(r"^(\d{4,})(.+)$", stem)
    if not m:
        return None, None, ""
    student_no = m.group(1).strip()
    rest = m.group(2).strip(" _-")
    sep = "_" if "_" in rest else "-"
    parts = [p.strip() for p in rest.split(sep) if p.strip()] if sep in rest else [rest]
    name = parts[0] if parts else rest
    class_name = parts[1] if len(parts) >= 2 else ""
    return student_no, name, class_name


def _save_photo(raw: bytes, filename: str, student_no: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "jpg").lower()
    if ext not in config.ALLOWED_IMG_EXT:
        ext = "jpg"
    fname = f"{student_no}_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = Path(config.STUDENTS_FOLDER) / fname
    fpath.write_bytes(raw)
    return f"uploads/students/{fname}"


def _remove_static_file(rel_path: str):
    if not rel_path:
        return
    full = Path(config.BASE_DIR) / "app" / "static" / rel_path
    try:
        if full.exists() and full.is_file():
            full.unlink()
    except OSError:
        pass


def _create_student_account(student_id: int, student_no: str):
    default_password = student_no[-6:] if len(student_no) >= 6 else "123456"
    old = query_one("SELECT id FROM users WHERE username=?", (student_no,))
    if not old:
        execute(
            "INSERT INTO users(username,password_hash,role,student_id) VALUES (?,?,?,?)",
            (student_no, hash_password(default_password), "student", student_id),
        )
    return default_password


def add_or_update_student_from_image(student_no: str, name: str, class_name: str,
                                     raw: bytes, filename: str, update_existing=True):
    img = face_engine.decode_image(raw)
    if img is None:
        raise ValueError("图片解码失败")
    enc = face_engine.encode_first_face(img)
    if enc is None:
        raise ValueError("未检测到清晰人脸")
    photo_path = _save_photo(raw, filename, student_no)
    old = query_one("SELECT id, photo_path FROM students WHERE student_no=?", (student_no,))
    if old:
        if not update_existing:
            raise ValueError("学号已存在")
        execute(
            "UPDATE students SET name=?,class_name=?,photo_path=?,encoding=? WHERE id=?",
            (name, class_name, photo_path, face_engine.encoding_to_blob(enc), old["id"]),
        )
        _remove_static_file(old.get("photo_path"))
        sid = old["id"]
    else:
        sid = execute(
            "INSERT INTO students(student_no,name,class_name,photo_path,encoding) VALUES (?,?,?,?,?)",
            (student_no, name, class_name, photo_path, face_engine.encoding_to_blob(enc)),
        )
    _create_student_account(sid, student_no)
    return {"id": sid, "student_no": student_no, "name": name, "class_name": class_name, "photo_path": photo_path}


@bp_students.route("", methods=["GET"])
@login_required
def list_students():
    user = current_user()
    if user["role"] == "student":
        sid = user.get("student_id")
        rows = query_all(
            "SELECT id,student_no,name,class_name,photo_path FROM students WHERE id=?", (sid,)
        ) if sid else []
        return jsonify({"items": rows})
    rows = query_all("SELECT id,student_no,name,class_name,photo_path FROM students ORDER BY student_no")
    return jsonify({"items": rows})


@bp_students.route("", methods=["POST"])
@teacher_required
def add_student():
    student_no = (request.form.get("student_no") or "").strip()
    name = (request.form.get("name") or "").strip()
    class_name = (request.form.get("class_name") or "").strip()
    file = request.files.get("photo")
    if not student_no or not name:
        return jsonify({"error": "学号和姓名必填"}), 400
    if query_one("SELECT id FROM students WHERE student_no=?", (student_no,)):
        return jsonify({"error": "该学号已存在；如需修改请点击列表中的编辑"}), 400
    if not file or not allowed_image(file.filename):
        return jsonify({"error": "请上传 jpg/png/bmp/webp 图片"}), 400
    try:
        info = add_or_update_student_from_image(student_no, name, class_name, file.read(), file.filename, update_existing=False)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **info})


@bp_students.route("/<int:sid>", methods=["PUT"])
@teacher_required
def update_student(sid):
    row = query_one("SELECT * FROM students WHERE id=?", (sid,))
    if not row:
        return jsonify({"error": "学生不存在"}), 404
    student_no = (request.form.get("student_no") or row["student_no"]).strip()
    name = (request.form.get("name") or row["name"]).strip()
    class_name = (request.form.get("class_name") or "").strip()
    file = request.files.get("photo")
    if not student_no or not name:
        return jsonify({"error": "学号和姓名必填"}), 400
    dup = query_one("SELECT id FROM students WHERE student_no=? AND id<>?", (student_no, sid))
    if dup:
        return jsonify({"error": "该学号已被其他学生使用"}), 400

    photo_path = row["photo_path"]
    encoding_blob = row["encoding"]
    old_photo = row["photo_path"]
    if file and file.filename:
        if not allowed_image(file.filename):
            return jsonify({"error": "图片格式不支持"}), 400
        raw = file.read()
        img = face_engine.decode_image(raw)
        if img is None:
            return jsonify({"error": "图片解码失败"}), 400
        enc = face_engine.encode_first_face(img)
        if enc is None:
            return jsonify({"error": "未检测到人脸"}), 400
        photo_path = _save_photo(raw, file.filename, student_no)
        encoding_blob = face_engine.encoding_to_blob(enc)
    execute(
        "UPDATE students SET student_no=?,name=?,class_name=?,photo_path=?,encoding=? WHERE id=?",
        (student_no, name, class_name, photo_path, encoding_blob, sid),
    )
    if photo_path != old_photo:
        _remove_static_file(old_photo)
    return jsonify({"ok": True})


@bp_students.route("/<int:sid>", methods=["DELETE"])
@teacher_required
def delete_student(sid):
    row = query_one("SELECT photo_path FROM students WHERE id=?", (sid,))
    if not row:
        return jsonify({"error": "学生不存在"}), 404
    execute("DELETE FROM students WHERE id=?", (sid,))
    _remove_static_file(row.get("photo_path"))
    return jsonify({"ok": True})


@bp_students.route("/import", methods=["POST"])
@teacher_required
def batch_import():
    files = request.files.getlist("photos")
    update_existing = (request.form.get("update_existing", "1") != "0")
    if not files:
        return jsonify({"error": "未上传任何文件"}), 400
    success, failed = [], []
    for f in files:
        try:
            if not allowed_image(f.filename):
                raise ValueError("图片格式不支持")
            student_no, name, class_name = parse_student_filename(f.filename)
            if not student_no or not name:
                raise ValueError("文件名应为 学号_姓名[_班级].jpg 或 学号-姓名-班级.jpg")
            info = add_or_update_student_from_image(student_no, name, class_name, f.read(), f.filename, update_existing)
            success.append(info)
        except Exception as exc:
            failed.append({"file": f.filename, "reason": str(exc)})
    return jsonify({"ok": True, "success": success, "failed": failed})


@bp_students.route("/<int:sid>/account", methods=["POST"])
@teacher_required
def create_account(sid):
    stu = query_one("SELECT id, student_no FROM students WHERE id=?", (sid,))
    if not stu:
        return jsonify({"error": "学生不存在"}), 404
    default_password = _create_student_account(stu["id"], stu["student_no"])
    return jsonify({"ok": True, "username": stu["student_no"], "default_password": default_password})
