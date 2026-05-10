"""考勤 API：活体挑战 → 帧序列校验 → 人脸比对 → 写入考勤记录"""
import io
import time
from datetime import datetime
from typing import List

from flask import Blueprint, jsonify, request, send_file

import config
from .. import face_engine, liveness
from ..auth import login_required, teacher_required, current_user
from ..models import execute, query_all, query_one

bp_attendance = Blueprint("attendance", __name__)


# -----------------------------------------------------------------------------
# 1. 活体挑战
# -----------------------------------------------------------------------------
@bp_attendance.route("/challenge", methods=["POST"])
@login_required
def issue_challenge():
    """生成一次性活体挑战，返回 token + 动作列表。"""
    sess = liveness.create_session(n=2)
    return jsonify({
        "token": sess.token,
        "challenges": sess.challenges,
        "instructions": [liveness.ACTIONS[c] for c in sess.challenges],
        "ear_threshold": config.EAR_BLINK_THRESHOLD,
        "mar_threshold": config.MAR_OPEN_THRESHOLD,
        "yaw_threshold": config.HEAD_YAW_THRESHOLD,
    })


# -----------------------------------------------------------------------------
# 2. 提交帧序列：校验活体并执行人脸识别 + 情绪分析
# -----------------------------------------------------------------------------
@bp_attendance.route("/verify", methods=["POST"])
@login_required
def verify_and_recognize():
    data = request.get_json() or {}
    token = data.get("token")
    frames_b64 = data.get("frames") or []
    if not token:
        return jsonify({"error": "缺少 token"}), 400
    if len(frames_b64) < config.LIVENESS_FRAME_MIN:
        return jsonify({"error": "帧数过少，请重新挑战"}), 400
    if len(frames_b64) > config.LIVENESS_FRAME_MAX:
        frames_b64 = frames_b64[-config.LIVENESS_FRAME_MAX:]

    sess = liveness.get_session(token)
    if not sess or sess.used:
        return jsonify({"error": "挑战 token 失效，请重新发起"}), 400

    # 解码每一帧（保持帧顺序与 metrics 对齐）
    metrics: List[liveness.FrameMetric] = []
    decoded_frames: List = []
    for b64 in frames_b64:
        img = face_engine.decode_dataurl(b64)
        decoded_frames.append(img)
        if img is None:
            metrics.append(liveness.FrameMetric(False))
        else:
            metrics.append(liveness.measure_frame(img))

    # 校验全部动作
    results = {a: liveness.verify_action(a, metrics) for a in sess.challenges}
    liveness_passed = all(results.values())

    # 人脸比对（取最后一张有效帧做识别 / 情绪分析）
    matched_student = None
    distance = None
    emotion = "unknown"

    valid_idxs = [i for i, m in enumerate(metrics) if m.has_face]
    if liveness_passed and valid_idxs:
        target_img = decoded_frames[valid_idxs[-1]]
        face_box = face_engine.detect_faces(target_img, upsample=1)
        if face_box:
            biggest = max(face_box, key=lambda r: r.width() * r.height())
            enc = face_engine.encode_face_with_enhancement(target_img, biggest, min_size=120)
            gallery_rows = query_all(
                "SELECT id, encoding FROM students WHERE encoding IS NOT NULL"
            )
            gallery = [(r["id"], face_engine.blob_to_encoding(r["encoding"])) for r in gallery_rows]
            sid, dist = face_engine.match_one(enc, gallery)
            distance = round(float(dist), 4) if dist != float("inf") else None
            if sid:
                matched_student = query_one(
                    "SELECT id, student_no, name, class_name, photo_path FROM students WHERE id=?",
                    (sid,),
                )
            # 情绪分析
            face_roi = face_engine.crop_face(target_img, biggest)
            emotion = face_engine.analyze_emotion(face_roi)

    # 标记会话已使用（一次性）
    liveness.consume_session(token)

    # 写入数据库
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if liveness_passed and matched_student:
        status = "success"
        execute(
            "INSERT INTO attendance_records(student_id,student_no,name,timestamp,status,"
            "liveness_passed,emotion,note) VALUES (?,?,?,?,?,?,?,?)",
            (matched_student["id"], matched_student["student_no"], matched_student["name"],
             now, status, 1, emotion, f"distance={distance}"),
        )
        if emotion and emotion != "unknown":
            execute(
                "INSERT INTO emotions(student_id,student_no,name,emotion,source,timestamp) "
                "VALUES (?,?,?,?,?,?)",
                (matched_student["id"], matched_student["student_no"], matched_student["name"],
                 emotion, "attendance", now),
            )
    else:
        status = "fail" if not liveness_passed else "unknown"
        execute(
            "INSERT INTO attendance_records(student_id,student_no,name,timestamp,status,"
            "liveness_passed,emotion,note) VALUES (?,?,?,?,?,?,?,?)",
            (None, None, None, now, status, 1 if liveness_passed else 0,
             emotion if liveness_passed else None,
             "活体未通过" if not liveness_passed else "未匹配到学生"),
        )

    return jsonify({
        "ok": True,
        "liveness_passed": liveness_passed,
        "actions_result": results,
        "matched_student": matched_student,
        "distance": distance,
        "emotion": emotion,
        "emotion_cn": config.EMOTION_CN.get(emotion, emotion),
        "status": status,
        "timestamp": now,
    })


# -----------------------------------------------------------------------------
# 3. 考勤记录查询
# -----------------------------------------------------------------------------
@bp_attendance.route("/records", methods=["GET"])
@login_required
def list_records():
    user = current_user()
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    student_no = (request.args.get("student_no") or "").strip()
    status = request.args.get("status")

    sql = "SELECT * FROM attendance_records WHERE 1=1"
    params = []
    if user["role"] == "student":
        sid = user.get("student_id")
        if not sid:
            return jsonify({"items": []})
        sql += " AND student_id=?"
        params.append(sid)
    if date_from:
        sql += " AND timestamp >= ?"
        params.append(date_from + " 00:00:00")
    if date_to:
        sql += " AND timestamp <= ?"
        params.append(date_to + " 23:59:59")
    if student_no:
        sql += " AND student_no=?"
        params.append(student_no)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY timestamp DESC LIMIT 1000"
    items = query_all(sql, tuple(params))
    for it in items:
        it["emotion_cn"] = config.EMOTION_CN.get(it.get("emotion"), it.get("emotion"))
    return jsonify({"items": items})


@bp_attendance.route("/export", methods=["GET"])
@teacher_required
def export_records():
    """导出 Excel 格式考勤记录。"""
    import pandas as pd

    rows = query_all(
        "SELECT id,student_no,name,timestamp,status,liveness_passed,emotion,note "
        "FROM attendance_records ORDER BY timestamp DESC"
    )
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["id", "student_no", "name", "timestamp", "status",
                                   "liveness_passed", "emotion", "note"])
    df["liveness_passed"] = df["liveness_passed"].map({1: "通过", 0: "未通过"}).fillna("-")
    df["emotion_cn"] = df["emotion"].map(lambda x: config.EMOTION_CN.get(x, x or "-"))
    df = df.rename(columns={
        "id": "记录ID", "student_no": "学号", "name": "姓名",
        "timestamp": "考勤时间", "status": "结果", "liveness_passed": "活体检测",
        "emotion": "情绪(原始)", "emotion_cn": "情绪", "note": "备注",
    })

    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="考勤记录")
    bio.seek(0)
    return send_file(bio,
                     as_attachment=True,
                     download_name=f"attendance_{int(time.time())}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
