from flask import Blueprint, current_app, jsonify, render_template
from flask_login import current_user
from sqlalchemy import text

from .extensions import db
from .models import ScenarioTopic, SkillModule


bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    skills = SkillModule.query.filter_by(is_published=True).order_by(SkillModule.sort_order).limit(6).all()
    topics = ScenarioTopic.query.filter_by(is_published=True).limit(5).all()
    return render_template("landing.html", skills=skills, topics=topics)


@bp.get("/health")
def health():
    return jsonify(
        status="ok",
        service="valedgari",
        version=current_app.config["APP_VERSION"],
    )


@bp.get("/health/live")
def health_live():
    return jsonify(status="ok", check="liveness", service="valedgari")


@bp.get("/health/ready")
def health_ready():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        current_app.logger.exception("readiness database check failed")
        return jsonify(status="error", check="database"), 503
    return jsonify(
        status="ok",
        check="readiness",
        database="available",
        version=current_app.config["APP_VERSION"],
    )

