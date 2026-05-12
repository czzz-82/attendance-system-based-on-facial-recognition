"""合照识别 API：上传合照，批量检测人脸 → 比对 → 保存完整分析档案。"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from flask import Blueprint, jsonify, request
from PIL import Image, ImageDraw, ImageFont

import config
from .. import face_engine
from ..auth import teacher_required
from ..models import execute, query_all, query_one, get_conn

bp_group = Blueprint("group", __name__)

GROUP_FACE_MIN_SIZE = 80
GROUP_MATCH_THRESHOLD = max(config.FACE_MATCH_THRESHOLD, 0.40)
SR_SAMPLE_LIMIT = 8


def _ensure_analysis_column():
    """兼容已存在的旧数据库，为 activities 增加 analysis_json 列。"""
    with get_conn() as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()]
        if "analysis_json" not in cols:
            conn.execute("ALTER TABLE activities ADD COLUMN analysis_json TEXT")


def _font(size=22):
    """OpenCV putText 不支持中文；使用 PIL + Windows 中文字体绘制姓名。"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arialuni.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _draw_labels_bgr(img_bgr, labels):
    """在 BGR 图上批量绘制中文标签。labels: (text, x, y, color_bgr)。"""
    if not labels:
        return img_bgr
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)
    font = _font(22)
    for text, x, y, color_bgr in labels:
        text = str(text)
        color_rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
        x = max(0, int(x))
        y = max(0, int(y))
        try:
            bbox = draw.textbbox((x, y), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = draw.textsize(text, font=font)
        bg_y1 = max(0, y - th - 8)
        bg_y2 = max(th + 8, y)
        draw.rounded_rectangle((x, bg_y1, x + tw + 12, bg_y2), radius=5, fill=color_rgb)
        draw.text((x + 6, bg_y1 + 3), text, font=font, fill=(255, 255, 255))
    return cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)


def _save_img(img_bgr, prefix, ext="jpg"):
    fname = f"{prefix}_{uuid.uuid4().hex[:10]}.{ext}"
    fpath = Path(config.ACTIVITIES_FOLDER) / fname
    cv2.imwrite(str(fpath), img_bgr)
    return f"uploads/activities/{fname}"


def _make_sr_sample(img, face, idx, force_demo=False):
    """保存局部人脸超分前/后样本，用于当前结果与历史档案展示。"""
    before = face_engine.crop_face(img, face, margin=22)
    if before.size == 0:
        return None
    after = face_engine.enhance_face_image(before)
    before_rel = _save_img(before, f"sr_before_{idx}")
    after_rel = _save_img(after, f"sr_after_{idx}")
    return {
        "before": before_rel,
        "after": after_rel,
        "face_size": f"{face.width()}×{face.height()}",
        "triggered": bool(face.width() < GROUP_FACE_MIN_SIZE or face.height() < GROUP_FACE_MIN_SIZE),
        "demo": bool(force_demo),
    }


def _parse_analysis(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


@bp_group.route("/upload", methods=["POST"])
@teacher_required
def upload_group_photo():
    _ensure_analysis_column()
    name = (request.form.get("name") or "未命名活动").strip()
    held_on = (request.form.get("held_on") or datetime.now().strftime("%Y-%m-%d")).strip()
    file = request.files.get("photo")
    if not file:
        return jsonify({"error": "请上传合照"}), 400

    raw = file.read()
    img = face_engine.decode_image(raw)
    if img is None:
        return jsonify({"error": "图片解码失败"}), 400

    original_rel = _save_img(img, "group_original")

    faces = face_engine.detect_faces(img, upsample=2)
    if not faces:
        return jsonify({"error": "未检测到任何人脸"}), 400
    faces = sorted(faces, key=lambda r: (r.top(), r.left()))

    gallery_rows = query_all("SELECT id, student_no, name, encoding FROM students WHERE encoding IS NOT NULL")
    gallery = [(r["id"], face_engine.blob_to_encoding(r["encoding"])) for r in gallery_rows]
    name_lookup = {r["id"]: r for r in gallery_rows}

    annotated = img.copy()
    matched_set = {}
    emotions_count = {}
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    matched_details = []
    unmatched_details = []
    unmatched = 0
    labels = []
    sr_samples = []
    sr_triggered_count = 0
    sr_candidate_faces = []

    for index, face in enumerate(faces, start=1):
        x, y, w, h = face.left(), face.top(), face.width(), face.height()
        triggered_sr = w < GROUP_FACE_MIN_SIZE or h < GROUP_FACE_MIN_SIZE
        sr_triggered_count += 1 if triggered_sr else 0
        sr_candidate_faces.append((face, not triggered_sr))

        try:
            enc = face_engine.encode_face_with_enhancement(img, face, min_size=GROUP_FACE_MIN_SIZE)
        except Exception as exc:
            color = (0, 165, 255)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            labels.append((f"#{index} 编码失败", x, max(24, y - 6), color))
            unmatched += 1
            unmatched_details.append({"index": index, "reason": f"编码失败：{exc}", "face_size": f"{w}×{h}"})
            continue

        sid, dist = face_engine.match_one(enc, gallery, threshold=GROUP_MATCH_THRESHOLD)
        roi = face_engine.crop_face(img, face)
        emotion = face_engine.analyze_emotion(roi)
        emotions_count[emotion] = emotions_count.get(emotion, 0) + 1

        if sid:
            stu = name_lookup[sid]
            if sid not in matched_set or float(dist) < matched_set[sid]["distance"]:
                matched_set[sid] = {
                    "student_id": sid,
                    "student_no": stu["student_no"],
                    "name": stu["name"],
                    "emotion": emotion,
                    "emotion_cn": config.EMOTION_CN.get(emotion, emotion),
                    "distance": float(dist),
                    "face_size": f"{w}×{h}",
                    "sr_triggered": triggered_sr,
                }
            color = (0, 190, 90)
            label = f"{stu['name']} {float(dist):.2f}"
        else:
            unmatched += 1
            color = (0, 80, 255)
            label = f"#{index} 未匹配"
            unmatched_details.append({
                "index": index,
                "reason": "距离超过阈值或不在学生库",
                "distance": round(float(dist), 4) if dist != float("inf") else None,
                "face_size": f"{w}×{h}",
                "sr_triggered": triggered_sr,
            })

        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        labels.append((label, x, max(24, y - 6), color))

    annotated = _draw_labels_bgr(annotated, labels)

    true_sr = [(f, demo) for f, demo in sr_candidate_faces if not demo]
    demo_sr = sorted([(f, demo) for f, demo in sr_candidate_faces if demo], key=lambda item: item[0].width() * item[0].height())
    for idx, (face, is_demo) in enumerate((true_sr + demo_sr)[:SR_SAMPLE_LIMIT], start=1):
        sample = _make_sr_sample(img, face, idx, force_demo=is_demo)
        if sample:
            sr_samples.append(sample)

    annotated_rel = _save_img(annotated, "group")

    aid = execute(
        "INSERT INTO activities(name,held_on,photo_path,detected,matched) VALUES (?,?,?,?,?)",
        (name, held_on, annotated_rel, len(faces), len(matched_set)),
    )

    for sid, info in matched_set.items():
        try:
            execute("INSERT OR IGNORE INTO activity_participation(activity_id,student_id) VALUES (?,?)", (aid, sid))
        except Exception:
            pass
        if info["emotion"] and info["emotion"] != "unknown":
            execute(
                "INSERT INTO emotions(student_id,student_no,name,emotion,source,timestamp) VALUES (?,?,?,?,?,?)",
                (sid, info["student_no"], info["name"], info["emotion"], "group_photo", now_ts),
            )
        matched_details.append({
            "student_no": info["student_no"],
            "name": info["name"],
            "emotion": info["emotion"],
            "emotion_cn": info["emotion_cn"],
            "distance": round(info["distance"], 4),
            "face_size": info["face_size"],
            "sr_triggered": info["sr_triggered"],
        })
    matched_details.sort(key=lambda item: item["student_no"])

    analysis = {
        "version": 1,
        "activity_name": name,
        "held_on": held_on,
        "created_at": now_ts,
        "original": original_rel,
        "annotated": annotated_rel,
        "detected": len(faces),
        "matched": len(matched_set),
        "unmatched": unmatched,
        "match_threshold": GROUP_MATCH_THRESHOLD,
        "sr_triggered": sr_triggered_count,
        "sr_samples": sr_samples,
        "students": matched_details,
        "unmatched_faces": unmatched_details,
        "emotions": {
            "raw": emotions_count,
            "cn": {config.EMOTION_CN.get(k, k): v for k, v in emotions_count.items()},
        },
    }
    execute("UPDATE activities SET analysis_json=? WHERE id=?", (json.dumps(analysis, ensure_ascii=False), aid))

    return jsonify({"ok": True, "activity_id": aid, **analysis})


@bp_group.route("/activities", methods=["GET"])
@teacher_required
def list_activities():
    _ensure_analysis_column()
    rows = query_all(
        "SELECT id,name,held_on,photo_path,detected,matched,created_at,"
        "CASE WHEN analysis_json IS NULL OR analysis_json='' THEN 0 ELSE 1 END AS has_analysis "
        "FROM activities ORDER BY held_on DESC, id DESC"
    )
    return jsonify({"items": rows})


@bp_group.route("/activities/<int:aid>", methods=["GET"])
@teacher_required
def activity_detail(aid):
    _ensure_analysis_column()
    act = query_one("SELECT * FROM activities WHERE id=?", (aid,))
    if not act:
        return jsonify({"error": "活动不存在"}), 404
    parts = query_all(
        "SELECT s.id, s.student_no, s.name, s.class_name "
        "FROM activity_participation ap JOIN students s ON ap.student_id=s.id "
        "WHERE ap.activity_id=? ORDER BY s.student_no",
        (aid,),
    )
    analysis = _parse_analysis(act.get("analysis_json"))
    if analysis is None:
        analysis = {
            "version": 0,
            "activity_name": act.get("name"),
            "held_on": act.get("held_on"),
            "created_at": act.get("created_at"),
            "original": None,
            "annotated": act.get("photo_path"),
            "detected": act.get("detected"),
            "matched": act.get("matched"),
            "unmatched": max(0, (act.get("detected") or 0) - (act.get("matched") or 0)),
            "sr_triggered": None,
            "sr_samples": [],
            "students": [{"student_no": p["student_no"], "name": p["name"], "class_name": p.get("class_name")} for p in parts],
            "unmatched_faces": [],
            "emotions": {"raw": {}, "cn": {}},
            "legacy": True,
        }
    act.pop("analysis_json", None)
    return jsonify({"activity": act, "participants": parts, "analysis": analysis})
