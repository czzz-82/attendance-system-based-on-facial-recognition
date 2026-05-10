"""Flask 工厂与蓝图注册"""
import os

from flask import Flask

import config
from .models import init_schema
from .auth import ensure_default_admin


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["JSON_AS_ASCII"] = False

    os.makedirs(config.STUDENTS_FOLDER, exist_ok=True)
    os.makedirs(config.ACTIVITIES_FOLDER, exist_ok=True)

    init_schema()
    ensure_default_admin()

    from .routes.pages import bp_pages
    from .routes.auth_routes import bp_auth
    from .routes.api_students import bp_students
    from .routes.api_attendance import bp_attendance
    from .routes.api_group import bp_group
    from .routes.api_stats import bp_stats

    app.register_blueprint(bp_pages)
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_students, url_prefix="/api/students")
    app.register_blueprint(bp_attendance, url_prefix="/api/attendance")
    app.register_blueprint(bp_group, url_prefix="/api/group")
    app.register_blueprint(bp_stats, url_prefix="/api/stats")

    @app.errorhandler(413)
    def too_large(_):
        return {"error": "上传文件过大"}, 413

    return app
