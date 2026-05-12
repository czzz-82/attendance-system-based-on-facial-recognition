"""统计 API：考勤、合照参与、情绪分布与时间趋势。"""
from flask import Blueprint, jsonify, request

import config
from ..auth import login_required, current_user
from ..models import query_all, query_one

bp_stats = Blueprint("stats", __name__)


def _current_student_filter(user):
    """学生角色只能看自己的数据。"""
    if user["role"] == "student":
        return user.get("student_id")
    return None


def _emotion_filters(user):
    """复用情绪筛选条件。"""
    student_no = (request.args.get("student_no") or "").strip()
    source = (request.args.get("source") or "").strip()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()

    where = ["1=1"]
    params = []
    if user["role"] == "student":
        where.append("student_id=?")
        params.append(user.get("student_id"))
    elif student_no:
        where.append("student_no=?")
        params.append(student_no)
    if source:
        where.append("source=?")
        params.append(source)
    if date_from:
        where.append("timestamp >= ?")
        params.append(date_from + " 00:00:00")
    if date_to:
        where.append("timestamp <= ?")
        params.append(date_to + " 23:59:59")
    return " AND ".join(where), params


@bp_stats.route("/overview", methods=["GET"])
@login_required
def overview():
    user = current_user()
    if user["role"] == "student":
        sid = user.get("student_id")
        att_total = query_one(
            "SELECT COUNT(*) c FROM attendance_records WHERE student_id=?", (sid,)
        )["c"]
        att_ok = query_one(
            "SELECT COUNT(*) c FROM attendance_records WHERE student_id=? AND status='success'",
            (sid,),
        )["c"]
        act_total = query_one(
            "SELECT COUNT(*) c FROM activity_participation WHERE student_id=?", (sid,)
        )["c"]
        return jsonify({
            "students": 1,
            "attendance_total": att_total,
            "attendance_success": att_ok,
            "activities_joined": act_total,
            "participation_total": att_ok + act_total,
        })

    students = query_one("SELECT COUNT(*) c FROM students")["c"]
    att_total = query_one("SELECT COUNT(*) c FROM attendance_records")["c"]
    att_ok = query_one("SELECT COUNT(*) c FROM attendance_records WHERE status='success'")["c"]
    activities = query_one("SELECT COUNT(*) c FROM activities")["c"]
    group_joined = query_one("SELECT COUNT(*) c FROM activity_participation")["c"]
    return jsonify({
        "students": students,
        "attendance_total": att_total,
        "attendance_success": att_ok,
        "activities": activities,
        "group_participation": group_joined,
        "participation_total": att_ok + group_joined,
    })


@bp_stats.route("/activities", methods=["GET"])
@login_required
def stats_activities():
    """综合参与频次：考勤成功次数 + 合照活动参与次数。

    之前这里只统计 activity_participation，所以普通考勤测试不会让柱状图变化。
    现在改为综合指标，更符合验收时“做一次测试就能看到统计变化”的预期。
    """
    user = current_user()
    sid_filter = _current_student_filter(user)
    params = []
    where = ""
    if sid_filter:
        where = "WHERE s.id=?"
        params.append(sid_filter)

    rows = query_all(
        f"""
        SELECT
            s.id,
            s.student_no,
            s.name,
            COALESCE(att.attendance_cnt, 0) AS attendance_cnt,
            COALESCE(gp.group_cnt, 0) AS group_cnt,
            COALESCE(att.attendance_cnt, 0) + COALESCE(gp.group_cnt, 0) AS cnt
        FROM students s
        LEFT JOIN (
            SELECT student_id, COUNT(*) AS attendance_cnt
            FROM attendance_records
            WHERE status='success' AND student_id IS NOT NULL
            GROUP BY student_id
        ) att ON att.student_id=s.id
        LEFT JOIN (
            SELECT student_id, COUNT(*) AS group_cnt
            FROM activity_participation
            GROUP BY student_id
        ) gp ON gp.student_id=s.id
        {where}
        ORDER BY cnt DESC, attendance_cnt DESC, group_cnt DESC, s.student_no
        """,
        tuple(params),
    )
    return jsonify({"items": rows})


@bp_stats.route("/attendance/timeline", methods=["GET"])
@login_required
def attendance_timeline():
    """考勤成功/失败时间趋势，按分钟聚合，适合课堂现场连续测试展示。"""
    user = current_user()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    student_no = (request.args.get("student_no") or "").strip()

    where = ["1=1"]
    params = []
    if user["role"] == "student":
        where.append("student_id=?")
        params.append(user.get("student_id"))
    elif student_no:
        where.append("student_no=?")
        params.append(student_no)
    if date_from:
        where.append("timestamp >= ?")
        params.append(date_from + " 00:00:00")
    if date_to:
        where.append("timestamp <= ?")
        params.append(date_to + " 23:59:59")

    rows = query_all(
        f"""
        SELECT substr(timestamp, 1, 16) AS t, status, COUNT(*) AS cnt
        FROM attendance_records
        WHERE {' AND '.join(where)}
        GROUP BY t, status
        ORDER BY t
        """,
        tuple(params),
    )
    return jsonify({"items": rows})


@bp_stats.route("/emotions", methods=["GET"])
@login_required
def stats_emotions():
    """情绪分布：可按 student_no、source、日期范围过滤。"""
    user = current_user()
    where_sql, params = _emotion_filters(user)
    rows = query_all(
        f"SELECT emotion, COUNT(*) cnt FROM emotions WHERE {where_sql} GROUP BY emotion ORDER BY cnt DESC",
        tuple(params),
    )
    items = [{
        "emotion": r["emotion"],
        "label": config.EMOTION_CN.get(r["emotion"], r["emotion"]),
        "count": r["cnt"],
    } for r in rows]
    return jsonify({"items": items})


@bp_stats.route("/emotions/timeline", methods=["GET"])
@login_required
def emotions_timeline():
    """情绪时间趋势。

    按分钟聚合而不是按天聚合。这样你连续做两次考勤测试时，折线图会立刻出现两个时间点；
    旧版按 date(timestamp) 聚合，同一天的多次测试会挤在一个点上，看起来像“没动”。
    """
    user = current_user()
    where_sql, params = _emotion_filters(user)
    rows = query_all(
        f"""
        SELECT substr(timestamp, 1, 16) AS t, emotion, COUNT(*) cnt
        FROM emotions
        WHERE {where_sql}
        GROUP BY t, emotion
        ORDER BY t
        """,
        tuple(params),
    )
    for row in rows:
        row["label"] = config.EMOTION_CN.get(row.get("emotion"), row.get("emotion"))
    return jsonify({"items": rows})


@bp_stats.route("/system", methods=["GET"])
@login_required
def system_status():
    """返回模型/依赖状态，供前端仪表盘展示。"""
    import os

    def module_available(name: str) -> bool:
        try:
            if name in {"gfpgan", "basicsr"}:
                from ..face_enhancer import _install_torchvision_compat
                _install_torchvision_compat()
            __import__(name)
            return True
        except Exception:
            return False

    shape_ok = os.path.exists(config.SHAPE_PREDICTOR_PATH)
    rec_ok = os.path.exists(config.FACE_REC_MODEL_PATH)
    live_ok = os.path.exists(config.LIVENESS_MODEL_PATH)
    return jsonify({
        "dlib_models_ready": bool(shape_ok and rec_ok),
        "dlib_detail": f"landmarks={'ready' if shape_ok else 'missing'}; recognition={'ready' if rec_ok else 'missing'}",
        "liveness_weight_ready": bool(live_ok),
        "liveness_detail": config.LIVENESS_MODEL_PATH if live_ok else "未找到 best_model.pth",
        "gfpgan_available": module_available("gfpgan"),
        "deepface_available": module_available("deepface"),
    })
