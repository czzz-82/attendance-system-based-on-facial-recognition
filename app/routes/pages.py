"""HTML 页面路由"""
from flask import Blueprint, render_template, redirect, url_for, session

from ..auth import login_required, current_user

bp_pages = Blueprint("pages", __name__)


@bp_pages.route("/")
def home():
    if "uid" not in session:
        return redirect(url_for("auth.login_page"))
    return redirect(url_for("pages.dashboard"))


@bp_pages.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user())


@bp_pages.route("/attendance")
@login_required
def attendance_page():
    return render_template("attendance.html", user=current_user())


@bp_pages.route("/students")
@login_required
def students_page():
    if session.get("role") != "teacher":
        return redirect(url_for("pages.dashboard"))
    return render_template("students.html", user=current_user())


@bp_pages.route("/group")
@login_required
def group_page():
    if session.get("role") != "teacher":
        return redirect(url_for("pages.dashboard"))
    return render_template("group_photo.html", user=current_user())


@bp_pages.route("/records")
@login_required
def records_page():
    return render_template("records.html", user=current_user())


@bp_pages.route("/stats")
@login_required
def stats_page():
    return render_template("stats.html", user=current_user())
