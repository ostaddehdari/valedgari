from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import text

from .extensions import db
from .models import (
    BackgroundJob,
    Course,
    CourseEnrollment,
    CourseSkillMembership,
    ScenarioTopic,
    SkillModule,
)
from .course_engine import COURSE_LEVELS


bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    skills = SkillModule.query.filter_by(is_published=True).order_by(SkillModule.sort_order).limit(6).all()
    topics = ScenarioTopic.query.filter_by(is_published=True).limit(5).all()
    courses = Course.query.filter_by(status="published").order_by(
        Course.is_featured.desc(), Course.sort_order, Course.id
    ).limit(10).all()
    return render_template("landing.html", skills=skills, topics=topics, courses=courses)


@bp.get("/courses")
def courses():
    query = Course.query.filter_by(status="published")
    search = request.args.get("q", "").strip()
    level = request.args.get("level", "")
    skill_id = request.args.get("skill_id", type=int)
    price = request.args.get("price", "")
    if search:
        query = query.filter(Course.title.contains(search))
    if level in COURSE_LEVELS:
        query = query.filter_by(level=level)
    if skill_id:
        query = query.join(CourseSkillMembership).filter(
            CourseSkillMembership.skill_id == skill_id
        )
    if price == "free":
        query = query.filter(Course.price_toman <= 0)
    elif price == "paid":
        query = query.filter(Course.price_toman > 0)
    rows = query.order_by(Course.is_featured.desc(), Course.sort_order, Course.id).all()
    return render_template(
        "courses.html",
        courses=rows,
        skills=SkillModule.query.filter_by(is_published=True).order_by(SkillModule.title).all(),
        levels=COURSE_LEVELS,
        selected_level=level,
        selected_skill_id=skill_id,
        selected_price=price,
        search=search,
    )


@bp.get("/courses/<slug>")
def course_detail(slug):
    course = Course.query.filter_by(slug=slug, status="published").first()
    if not course:
        abort(404)
    enrollment = None
    if current_user.is_authenticated:
        enrollment = CourseEnrollment.query.filter_by(
            course_id=course.id, user_id=current_user.id
        ).filter(CourseEnrollment.status.in_(["active", "completed"])).order_by(
            CourseEnrollment.enrolled_at.desc()
        ).first()
    return render_template("course_detail.html", course=course, enrollment=enrollment)


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


@bp.get("/health/release")
def health_release():
    """Deployment gate: database, migration marker and terminal queue failures."""
    try:
        db.session.execute(text("SELECT 1"))
        migration = db.session.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one_or_none()
    except Exception as exc:
        db.session.rollback()
        if "alembic_version" not in str(exc):
            current_app.logger.exception("release database check failed")
            return jsonify(status="error", check="database"), 503
        migration = "unversioned"
    failed_jobs = BackgroundJob.query.filter_by(status="failed").count()
    response = jsonify(
        status="ok" if failed_jobs == 0 else "warning",
        check="release",
        database="available",
        migration=migration or "unknown",
        failed_jobs=failed_jobs,
        version=current_app.config["APP_VERSION"],
    )
    return (response, 200) if failed_jobs == 0 else (response, 503)

