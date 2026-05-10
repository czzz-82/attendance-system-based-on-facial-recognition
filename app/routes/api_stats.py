"""统计 API：考勤情况、活动参与频次、情绪分布"""
from flask import Blueprint, jsonify, request

import config
from ..auth import login_required, current_user
from ..models import query_all, query_one

bp_stats = Blueprint("stats", __name__)


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
        })

    students = query_one("SELECT COUNT(*) c FROM students")["c"]
    att_total = query_one("SELECT COUNT(*) c FROM attendance_records")["c"]
    att_ok = query_one("SELECT COUNT(*) c FROM attendance_records WHERE status='success'")["c"]
    activities = query_one("SELECT COUNT(*) c FROM activities")["c"]
    return jsonify({
        "students": students,
        "attendance_total": att_total,
        "attendance_success": att_ok,
        "activities": activities,
    })


@bp_stats.route("/activities", methods=["GET"])
@login_required
def stats_activities():
    """每个学生的活动参与频次。"""
    user = current_user()
    if user["role"] == "student":
        sid = user.get("student_id")
        rows = query_all(
            "SELECT s.student_no,s.name,COUNT(ap.id) cnt FROM students s "
            "LEFT JOIN activity_participation ap ON s.id=ap.student_id "
            "WHERE s.id=? GROUP BY s.id", (sid,)
        )
    else:
        rows = query_all(
            "SELECT s.student_no,s.name,COUNT(ap.id) cnt FROM students s "
            "LEFT JOIN activity_participation ap ON s.id=ap.student_id "
            "GROUP BY s.id ORDER BY cnt DESC, s.student_no"
        )
    return jsonify({"items": rows})


@bp_stats.route("/emotions", methods=["GET"])
@login_required
def stats_emotions():
    """情绪分布：可按 student_no、source、日期范围过滤。"""
    user = current_user()
    student_no = (request.args.get("student_no") or "").strip()
    source = request.args.get("source")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    sql = "SELECT emotion, COUNT(*) cnt FROM emotions WHERE 1=1"
    params = []
    if user["role"] == "student":
        sid = user.get("student_id")
        sql += " AND student_id=?"
        params.append(sid)
    if student_no:
        sql += " AND student_no=?"
        params.append(student_no)
    if source:
        sql += " AND source=?"
        params.append(source)
    if date_from:
        sql += " AND timestamp >= ?"
        params.append(date_from + " 00:00:00")
    if date_to:
        sql += " AND timestamp <= ?"
        params.append(date_to + " 23:59:59")
    sql += " GROUP BY emotion ORDER BY cnt DESC"
    rows = query_all(sql, tuple(params))
    items = [{"emotion": r["emotion"],
              "label": config.EMOTION_CN.get(r["emotion"], r["emotion"]),
              "count": r["cnt"]} for r in rows]
    return jsonify({"items": items})


@bp_stats.route("/emotions/timeline", methods=["GET"])
@login_required
def emotions_timeline():
    """按日聚合的情绪时间线（折线图）。"""
    user = current_user()
    sql = ("SELECT date(timestamp) d, emotion, COUNT(*) cnt FROM emotions WHERE 1=1")
    params = []
    if user["role"] == "student":
        sql += " AND student_id=?"
        params.append(user.get("student_id"))
    sql += " GROUP BY d, emotion ORDER BY d"
    rows = query_all(sql, tuple(params))
    return jsonify({"items": rows})
