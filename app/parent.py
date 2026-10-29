import json
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    Child,
    ParentingAssessment,
    ScenarioAttempt,
    ScenarioLevel,
    ScenarioTopic,
    SkillModule,
    SkillProgress,
)


bp = Blueprint("parent", __name__, url_prefix="/dashboard")

ASSESSMENT_QUESTIONS = [
    "قبل از پاسخ‌دادن، احساس فرزندم را می‌شنوم و نام‌گذاری می‌کنم.",
    "قوانین خانه روشن، کوتاه و از قبل قابل پیش‌بینی‌اند.",
    "در زمان عصبانیت از تحقیر، تهدید و مقایسه پرهیز می‌کنم.",
    "به فرزندم در انتخاب راه‌حل و پذیرفتن پیامد طبیعی نقش می‌دهم.",
    "رفتار را نقد می‌کنم، نه شخصیت و ارزشمندی فرزندم را.",
    "برای گفت‌وگو زمان مناسب انتخاب می‌کنم، نه اوج تعارض را.",
    "موفقیت‌های کوچک و تلاش فرزندم را مشخص و واقعی بازتاب می‌دهم.",
    "بعد از اشتباه خودم عذرخواهی و رابطه را ترمیم می‌کنم.",
]


def owned_child(child_id=None):
    child_id = child_id or session.get("active_child_id")
    if not child_id:
        return current_user.children[0] if current_user.children else None
    child = db.session.get(Child, int(child_id))
    if not child or child.user_id != current_user.id:
        abort(404)
    return child


@bp.get("/")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    child = owned_child()
    if child:
        session["active_child_id"] = child.id
    assessment = None
    progress = []
    if child:
        assessment = (
            ParentingAssessment.query.filter_by(user_id=current_user.id, child_id=child.id)
            .order_by(ParentingAssessment.created_at.desc())
            .first()
        )
        progress = SkillProgress.query.filter_by(user_id=current_user.id, child_id=child.id).all()
    completed = sum(1 for item in progress if item.percent >= 100)
    return render_template(
        "parent/dashboard.html", child=child, assessment=assessment, completed=completed
    )


@bp.route("/children", methods=["GET", "POST"])
@login_required
def children():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            birth_year = int(request.form.get("birth_year", "0"))
        except ValueError:
            birth_year = 0
        current_jalali_year = 1405
        if len(name) < 2 or not (1384 <= birth_year <= current_jalali_year):
            flash("نام و سال تولد شمسی معتبر وارد کنید.", "danger")
        else:
            child = Child(
                user_id=current_user.id,
                name=name,
                birth_year=birth_year,
                gender=request.form.get("gender", "unspecified"),
                notes=request.form.get("notes", "").strip()[:400],
            )
            db.session.add(child)
            db.session.commit()
            session["active_child_id"] = child.id
            flash(f"پرونده {child.name} ساخته شد.", "success")
            return redirect(url_for("parent.dashboard"))
    return render_template("parent/children.html")


@bp.post("/children/<int:child_id>/activate")
@login_required
def activate_child(child_id):
    child = owned_child(child_id)
    session["active_child_id"] = child.id
    flash(f"اکنون مسیر اختصاصی {child.name} را می‌بینید.", "info")
    return redirect(request.referrer or url_for("parent.dashboard"))


@bp.route("/assessment", methods=["GET", "POST"])
@login_required
def assessment():
    child = owned_child()
    if not child:
        flash("ابتدا پرونده یک فرزند را بسازید.", "warning")
        return redirect(url_for("parent.children"))
    if request.method == "POST":
        answers = []
        for index in range(len(ASSESSMENT_QUESTIONS)):
            try:
                value = int(request.form.get(f"q{index}", "0"))
            except ValueError:
                value = 0
            if value not in range(1, 6):
                flash("لطفاً به همه گزاره‌ها پاسخ دهید.", "danger")
                return render_template("parent/assessment.html", child=child, questions=ASSESSMENT_QUESTIONS)
            answers.append(value)
        score = round(sum(answers) / (len(answers) * 5) * 100)
        if score >= 80:
            level = "پایه مقتدرانه و پایدار"
        elif score >= 60:
            level = "مسیر رو به رشد"
        elif score >= 40:
            level = "نیازمند تمرین هدفمند"
        else:
            level = "شروع بازسازی ارتباط"
        result = ParentingAssessment(
            user_id=current_user.id,
            child_id=child.id,
            score=score,
            level=level,
            answers_json=json.dumps(answers),
        )
        db.session.add(result)
        db.session.commit()
        flash("سنجش ذخیره شد و مسیر پیشنهادی شما آماده است.", "success")
        return redirect(url_for("parent.dashboard"))
    return render_template("parent/assessment.html", child=child, questions=ASSESSMENT_QUESTIONS)


@bp.route("/skills", methods=["GET", "POST"])
@login_required
def skills():
    child = owned_child()
    if not child:
        return redirect(url_for("parent.children"))
    if request.method == "POST":
        module = db.session.get(SkillModule, request.form.get("module_id", type=int))
        if not module:
            abort(404)
        progress = SkillProgress.query.filter_by(
            user_id=current_user.id, child_id=child.id, module_id=module.id
        ).first()
        if not progress:
            progress = SkillProgress(
                user_id=current_user.id, child_id=child.id, module_id=module.id
            )
            db.session.add(progress)
        progress.percent = min(100, max(0, request.form.get("percent", 100, type=int)))
        progress.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"پیشرفت «{module.title}» برای {child.name} ثبت شد.", "success")
        return redirect(url_for("parent.skills"))
    modules = SkillModule.query.filter_by(is_published=True).order_by(SkillModule.sort_order).all()
    progress_map = {
        item.module_id: item.percent
        for item in SkillProgress.query.filter_by(user_id=current_user.id, child_id=child.id)
    }
    return render_template("parent/skills.html", child=child, modules=modules, progress_map=progress_map)


@bp.route("/scenario", methods=["GET", "POST"])
@login_required
def scenario():
    child = owned_child()
    if not child:
        return redirect(url_for("parent.children"))
    topics = ScenarioTopic.query.filter_by(is_published=True).all()
    selected_topic = request.values.get("topic_id", type=int)
    selected_level = request.values.get("level", 1, type=int)
    level = None
    if selected_topic:
        level = ScenarioLevel.query.filter_by(topic_id=selected_topic, level=selected_level).first()
    if request.method == "POST" and level:
        db.session.add(
            ScenarioAttempt(
                user_id=current_user.id,
                child_id=child.id,
                level_id=level.id,
                selected_node_id=request.form.get("node_id", type=int),
            )
        )
        db.session.commit()
    return render_template(
        "parent/scenario.html",
        child=child,
        topics=topics,
        selected_topic=selected_topic,
        selected_level=selected_level,
        level=level,
    )

