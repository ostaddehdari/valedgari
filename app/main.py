from flask import Blueprint, jsonify, render_template
from flask_login import current_user

from .models import ScenarioTopic, SkillModule


bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    skills = SkillModule.query.filter_by(is_published=True).order_by(SkillModule.sort_order).limit(6).all()
    topics = ScenarioTopic.query.filter_by(is_published=True).limit(5).all()
    return render_template("landing.html", skills=skills, topics=topics)


@bp.get("/health")
def health():
    return jsonify(status="ok", service="valedgari", authenticated=current_user.is_authenticated)

