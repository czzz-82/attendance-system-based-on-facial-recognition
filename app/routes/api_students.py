"""学生管理 API（增删改查 + 批量导入 + 人脸特征建库）"""
import io
import os
import time
import uuid

from flask import Blueprint, jsonify, request, send_from_directory
import pandas as pd

import config
from .. import face_engine
from ..auth import teacher_required, login_required, current_user
from ..models import execute, query_all, query_one, get_conn

bp_students = Blueprint("students", __name__)


@bp_students.route("", methods=["GET"])
@login_required
def list_students():
    user = current_user()
    if user["role"] == "student":
        # 学生只能看自己
        sid = user.get("student_id")
        if not sid:
            return jsonify({"items": []})
        rows = query_all(
            "SELECT id,student_no,name,class_name,photo_path FROM students WHERE id=?",
            (sid,),
        )
        return jsonify({"items": rows})
    rows = query_all(
        "SELECT id,student_no,name,class_name,photo_path FROM students ORDER BY student_no"
    )
    return jsonify({"items": rows})


@bp_students.route("", methods=["POST"])
@teacher_required
def add_student():
    """单个添加学生：multipart 表单，含字段 student_no/name/class_name + 文件 photo。"""
    student_no = (request.form.get("student_no") or "").strip()
    name = (request.form.get("name") or "").strip()
    class_name = (request.form.get("class_name") or "").strip()
    file = request.files.get("photo")
    if not student_no or not name:
        return jsonify({"error": "学号和姓名必填"}), 400
    if query_one("SELECT id FROM students WHERE student_no=?", (student_no,)):
        return jsonify({"error": "该学号已存在"}), 400
    if not file:
        return jsonify({"error": "请上传一张正面免冠照"}), 400

    raw = file.read()
    img = face_engine.decode_image(raw)
    if img is None:
        return jsonify({"error": "图片解码失败"}), 400
    encoding = face_engine.encode_first_face(img)
    if encoding is None:
        return jsonify({"error": "未在照片中检测到清晰人脸"}), 400

    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg").lower()
    if ext not in config.ALLOWED_IMG_EXT:
        ext = "jpg"
    fname = f"{student_no}_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(config.STUDENTS_FOLDER, fname)
    with open(fpath, "wb") as f:
        f.write(raw)
    rel_path = f"uploads/students/{fname}"
    sid = execute(
        "INSERT INTO students(student_no,name,class_name,photo_path,encoding) VALUES (?,?,?,?,?)",
        (student_no, name, class_name, rel_path, face_engine.encoding_to_blob(encoding)),
    )
    return jsonify({"ok": True, "id": sid, "photo_path": rel_path})


@bp_students.route("/<int:sid>", methods=["PUT"])
@teacher_required
def update_student(sid):
    student_no = (request.form.get("student_no") or "").strip()
    name = (request.form.get("name") or "").strip()
    class_name = (request.form.get("class_name") or "").strip()
    file = request.files.get("photo")
    if not student_no or not name:
        return jsonify({"error": "学号和姓名必填"}), 400
    row = query_one("SELECT * FROM students WHERE id=?", (sid,))
    if not row:
        return jsonify({"error": "学生不存在"}), 404

    photo_path = row["photo_path"]
    encoding_blob = row["encoding"]
    if file:
        raw = file.read()
        img = face_engine.decode_image(raw)
        if img is None:
            return jsonify({"error": "图片解码失败"}), 400
        enc = face_engine.encode_first_face(img)
        if enc is None:
            return jsonify({"error": "未检测到人脸"}), 400
        ext = (file.filename.rsplit(".", 1)[-1] or "jpg").lower()
        fname = f"{student_no}_{uuid.uuid4().hex[:8]}.{ext}"
        fpath = os.path.join(config.STUDENTS_FOLDER, fname)
        with open(fpath, "wb") as f:
            f.write(raw)
        photo_path = f"uploads/students/{fname}"
        encoding_blob = face_engine.encoding_to_blob(enc)

    execute(
        "UPDATE students SET student_no=?,name=?,class_name=?,photo_path=?,encoding=? WHERE id=?",
        (student_no, name, class_name, photo_path, encoding_blob, sid),
    )
    return jsonify({"ok": True})


@bp_students.route("/<int:sid>", methods=["DELETE"])
@teacher_required
def delete_student(sid):
    row = query_one("SELECT photo_path FROM students WHERE id=?", (sid,))
    if not row:
        return jsonify({"error": "学生不存在"}), 404
    execute("DELETE FROM students WHERE id=?", (sid,))
    if row["photo_path"]:
        full = os.path.join(config.BASE_DIR, "app", "static", row["photo_path"])
        if os.path.exists(full):
            try:
                os.remove(full)
            except OSError:
                pass
    return jsonify({"ok": True})


@bp_students.route("/import", methods=["POST"])
@teacher_required
def batch_import():
    """批量导入：上传 zip 解出来的多张照片（文件名为 学号_姓名.jpg），逐张构建特征。

    更简单的做法：前端逐张调用 / 此处接受 multipart 多文件，
    文件名格式 `学号_姓名_班级.jpg`（班级可选）。
    """
    files = request.files.getlist("photos")
    if not files:
        return jsonify({"error": "未上传任何文件"}), 400

    success, failed = [], []
    for f in files:
        try:
            stem = os.path.splitext(f.filename)[0]
            parts = stem.split("_")
            if len(parts) < 2:
                failed.append({"file": f.filename, "reason": "文件名应为 学号_姓名[_班级]"})
                continue
            student_no = parts[0].strip()
            name = parts[1].strip()
            class_name = parts[2].strip() if len(parts) > 2 else ""
            if query_one("SELECT id FROM students WHERE student_no=?", (student_no,)):
                failed.append({"file": f.filename, "reason": "学号已存在"})
                continue
            raw = f.read()
            img = face_engine.decode_image(raw)
            if img is None:
                failed.append({"file": f.filename, "reason": "图片解码失败"})
                continue
            enc = face_engine.encode_first_face(img)
            if enc is None:
                failed.append({"file": f.filename, "reason": "未检测到人脸"})
                continue
            ext = (f.filename.rsplit(".", 1)[-1] or "jpg").lower()
            fname = f"{student_no}_{uuid.uuid4().hex[:6]}.{ext}"
            fpath = os.path.join(config.STUDENTS_FOLDER, fname)
            with open(fpath, "wb") as wf:
                wf.write(raw)
            execute(
                "INSERT INTO students(student_no,name,class_name,photo_path,encoding) "
                "VALUES (?,?,?,?,?)",
                (student_no, name, class_name, f"uploads/students/{fname}",
                 face_engine.encoding_to_blob(enc)),
            )
            success.append({"student_no": student_no, "name": name})
        except Exception as e:
            failed.append({"file": f.filename, "reason": str(e)})

    return jsonify({"ok": True, "success": success, "failed": failed})
