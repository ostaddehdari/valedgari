import json
import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    Child,
    PaymentAllocation,
    ParentingAssessment,
    ProjectAuditLog,
    ProjectMembership,
    ScenarioAttempt,
    ScenarioLevel,
    ScenarioTopic,
    SkillModule,
    SkillProgress,
    SponsoredProject,
    utcnow,
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


def normalize_support_code(value):
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return re.sub(r"[^A-Z0-9-]", "", (value or "").translate(translation).upper().strip())


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
    sponsored_memberships = ProjectMembership.query.filter(
        ProjectMembership.user_id == current_user.id,
        ProjectMembership.status.in_(["active", "pending"]),
    ).all()
    return render_template(
        "parent/dashboard.html",
        child=child,
        assessment=assessment,
        completed=completed,
        sponsored_memberships=sponsored_memberships,
    )


@bp.route("/projects", methods=["GET", "POST"])
@login_required
def projects():
    if current_user.is_admin:
        return redirect(url_for("admin.projects"))
    if request.method == "POST":
        action = request.form.get("action", "join")
        if action == "join":
            code = normalize_support_code(request.form.get("code"))
            project = SponsoredProject.query.filter_by(code=code).first()
            if not project:
                flash("کد حمایت پیدا نشد؛ کد را دقیقاً مطابق پیام سازمان وارد کنید.", "danger")
            else:
                existing = ProjectMembership.query.filter_by(
                    project_id=project.id, user_id=current_user.id
                ).first()
                if existing and existing.status in {"active", "pending"}:
                    flash("شما قبلاً عضو این پروژه شده‌اید.", "info")
                else:
                    problem = project.acceptance_problem()
                    if problem:
                        flash(problem, "warning")
                    else:
                        gross, organization_amount, parent_amount = project.calculate_split()
                        membership = existing or ProjectMembership(
                            project_id=project.id,
                            user_id=current_user.id,
                            source="support_code",
                            joined_code=code,
                        )
                        membership.status = "active" if parent_amount == 0 else "pending"
                        membership.joined_code = code
                        membership.joined_at = utcnow()
                        membership.ended_at = None
                        if not existing:
                            db.session.add(membership)
                            db.session.flush()
                        allocation = PaymentAllocation(
                            membership_id=membership.id,
                            service_name=(project.eligible_services or ["دسترسی والدیار"])[0],
                            gross_amount_toman=gross,
                            organization_amount_toman=organization_amount,
                            parent_amount_toman=parent_amount,
                            status="parent_paid" if parent_amount == 0 else "reserved",
                            parent_paid_at=utcnow() if parent_amount == 0 else None,
                        )
                        db.session.add(allocation)
                        db.session.flush()
                        db.session.add(
                            ProjectAuditLog(
                                project_id=project.id,
                                actor_id=current_user.id,
                                action="parent_joined",
                                details_json=json.dumps(
                                    {
                                        "membership_id": membership.id,
                                        "allocation_id": allocation.id,
                                        "gross": gross,
                                        "organization_share": organization_amount,
                                        "parent_share": parent_amount,
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                        )
                        db.session.commit()
                        flash(
                            f"عضویت ثبت شد؛ سهم سازمان {organization_amount:,} و سهم شما {parent_amount:,} تومان است.",
                            "success",
                        )
                        return redirect(url_for("parent.projects"))
        elif action == "cancel":
            membership = db.session.get(
                ProjectMembership, request.form.get("membership_id", type=int)
            )
            if not membership or membership.user_id != current_user.id:
                abort(404)
            if any(item.status in {"parent_paid", "settled"} for item in membership.allocations):
                flash("برای لغو عضویت پرداخت‌شده با پشتیبانی تماس بگیرید.", "warning")
            else:
                membership.status = "cancelled"
                membership.ended_at = utcnow()
                for allocation in membership.allocations:
                    if allocation.status == "reserved":
                        allocation.status = "cancelled"
                db.session.add(
                    ProjectAuditLog(
                        project_id=membership.project_id,
                        actor_id=current_user.id,
                        action="parent_cancelled_membership",
                        details_json=json.dumps({"membership_id": membership.id}),
                    )
                )
                db.session.commit()
                flash("عضویت و رزرو بودجه شما لغو شد.", "info")
                return redirect(url_for("parent.projects"))

    memberships = ProjectMembership.query.filter_by(user_id=current_user.id).order_by(
        ProjectMembership.joined_at.desc()
    ).all()
    preview = None
    preview_code = normalize_support_code(request.args.get("code"))
    if preview_code:
        preview = SponsoredProject.query.filter_by(code=preview_code).first()
    return render_template(
        "parent/projects.html",
        memberships=memberships,
        preview=preview,
        preview_code=preview_code,
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

