"""合照识别 API：上传一张大合照，批量检测人脸 → 比对 → 写参与表。"""
import os
import time
import uuid
from datetime import datetime

import cv2
from flask import Blueprint, jsonify, request

import config
from .. import face_engine
from ..auth import teacher_required
from ..models import execute, query_all, query_one

bp_group = Blueprint("group", __name__)


@bp_group.route("/upload", methods=["POST"])
@teacher_required
def upload_group_photo():
    name = (request.form.get("name") or "未命名活动").strip()
    held_on = (request.form.get("held_on") or datetime.now().strftime("%Y-%m-%d")).strip()
    file = request.files.get("photo")
    if not file:
        return jsonify({"error": "请上传合照"}), 400

    raw = file.read()
    img = face_engine.decode_image(raw)
    if img is None:
        return jsonify({"error": "图片解码失败"}), 400

    # 合照人脸通常较小，使用 upsample=2 提高小脸检出率
    faces = face_engine.detect_faces(img, upsample=2)
    if not faces:
        return jsonify({"error": "未检测到任何人脸"}), 400

    # 取人脸库
    gallery_rows = query_all("SELECT id, student_no, name, encoding FROM students WHERE encoding IS NOT NULL")
    gallery = [(r["id"], face_engine.blob_to_encoding(r["encoding"])) for r in gallery_rows]
    name_lookup = {r["id"]: r for r in gallery_rows}

    # 保存合照（带框）
    annotated = img.copy()
    matched_set = {}
    emotions_count = {}
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    matched_details = []
    unmatched = 0

    for face in faces:
        try:
            # 合照人脸通常更小，我们将 min_size 设为 80。
            # 意味着只要合照中的人脸小于 80x80 像素，就会先被放大变清晰，再去识别
            enc = face_engine.encode_face_with_enhancement(img, face, min_size=80)
        except Exception:
            continue
        sid, dist = face_engine.match_one(enc, gallery)
        x, y, w, h = face.left(), face.top(), face.width(), face.height()
        # 情绪分析
        roi = face_engine.crop_face(img, face)
        emotion = face_engine.analyze_emotion(roi)
        emotions_count[emotion] = emotions_count.get(emotion, 0) + 1

        if sid:
            stu = name_lookup[sid]
            matched_set[sid] = {"student_id": sid, "student_no": stu["student_no"],
                                "name": stu["name"], "emotion": emotion, "distance": float(dist)}
            color = (0, 200, 0)
            label = stu["name"]
        else:
            unmatched += 1
            color = (0, 0, 255)
            label = "?"
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        cv2.putText(annotated, label, (x, y - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)

    # 持久化合照
    fname = f"group_{uuid.uuid4().hex[:10]}.jpg"
    fpath = os.path.join(config.ACTIVITIES_FOLDER, fname)
    cv2.imwrite(fpath, annotated)
    rel_path = f"uploads/activities/{fname}"

    # 入库 activity 主记录
    aid = execute(
        "INSERT INTO activities(name,held_on,photo_path,detected,matched) VALUES (?,?,?,?,?)",
        (name, held_on, rel_path, len(faces), len(matched_set)),
    )

    # 写入参与记录 + 情绪表
    for sid, info in matched_set.items():
        try:
            execute(
                "INSERT OR IGNORE INTO activity_participation(activity_id,student_id) VALUES (?,?)",
                (aid, sid),
            )
        except Exception:
            pass
        if info["emotion"] and info["emotion"] != "unknown":
            execute(
                "INSERT INTO emotions(student_id,student_no,name,emotion,source,timestamp) "
                "VALUES (?,?,?,?,?,?)",
                (sid, info["student_no"], info["name"], info["emotion"], "group_photo", now_ts),
            )
        matched_details.append({
            "student_no": info["student_no"], "name": info["name"],
            "emotion": info["emotion"],
            "emotion_cn": config.EMOTION_CN.get(info["emotion"], info["emotion"]),
            "distance": round(info["distance"], 4),
        })

    return jsonify({
        "ok": True,
        "activity_id": aid,
        "annotated": rel_path,
        "detected": len(faces),
        "matched": len(matched_set),
        "unmatched": unmatched,
        "students": matched_details,
        "emotions": {
            "raw": emotions_count,
            "cn": {config.EMOTION_CN.get(k, k): v for k, v in emotions_count.items()},
        },
    })


@bp_group.route("/activities", methods=["GET"])
@teacher_required
def list_activities():
    rows = query_all(
        "SELECT id,name,held_on,photo_path,detected,matched,created_at "
        "FROM activities ORDER BY held_on DESC, id DESC"
    )
    return jsonify({"items": rows})


@bp_group.route("/activities/<int:aid>", methods=["GET"])
@teacher_required
def activity_detail(aid):
    act = query_one("SELECT * FROM activities WHERE id=?", (aid,))
    if not act:
        return jsonify({"error": "活动不存在"}), 404
    parts = query_all(
        "SELECT s.id, s.student_no, s.name, s.class_name "
        "FROM activity_participation ap JOIN students s ON ap.student_id=s.id "
        "WHERE ap.activity_id=? ORDER BY s.student_no",
        (aid,),
    )
    return jsonify({"activity": act, "participants": parts})
