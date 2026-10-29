import csv
import io
import json
import re
from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    AssessmentInstrument,
    AssessmentQuestion,
    AssistantConversation,
    AssistantFeedback,
    AssistantMessage,
    Child,
    ChildProfileSnapshot,
    DailyAction,
    DecisionNode,
    DynamicForm,
    Organization,
    PaymentAllocation,
    ParentingAssessment,
    ParentingStyleAssessment,
    PersonalizationRule,
    ProjectAuditLog,
    ProjectMembership,
    ScenarioLevel,
    ScenarioTopic,
    SafetyProtocol,
    SkillModule,
    SponsoredProject,
    User,
    HomeActionOutcome,
    MicroLesson,
    PlanReview,
    RecommendationRun,
    SkillDomain,
    WeeklyPlan,
    utcnow,
)
from .security import admin_required


bp = Blueprint("admin", __name__, url_prefix="/admin")
PROJECT_STATUSES = {"draft", "active", "paused", "closed"}
ALLOCATION_TRANSITIONS = {
    "reserved": {"parent_paid", "cancelled"},
    "parent_paid": {"settled", "cancelled"},
    "settled": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


def make_slug(value):
    value = (value or "form").strip().lower()
    value = re.sub(r"[^a-z0-9\-]+", "-", value).strip("-")
    return value or f"form-{DynamicForm.query.count() + 1}"


def normalize_digits(value):
    return (value or "").translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


def parse_int(value, default=0):
    cleaned = normalize_digits(value).replace(",", "").replace("٬", "").strip()
    try:
        return int(cleaned) if cleaned else default
    except ValueError:
        return default


def normalize_project_code(value):
    return re.sub(r"[^A-Z0-9-]", "", normalize_digits(value).upper().strip())


def parse_iso_date(value):
    try:
        return date.fromisoformat(normalize_digits(value)) if value else None
    except ValueError:
        return None


def audit_project(project, action, details=None):
    db.session.add(
        ProjectAuditLog(
            project_id=project.id,
            actor_id=current_user.id,
            action=action,
            details_json=json.dumps(details or {}, ensure_ascii=False),
        )
    )


def project_form_values(project=None):
    pricing_model = request.form.get("pricing_model", "percent")
    status = request.form.get("status", "draft")
    code = normalize_project_code(request.form.get("code"))
    values = {
        "name": request.form.get("name", "").strip(),
        "code": code,
        "description": request.form.get("description", "").strip()[:700],
        "status": status if status in PROJECT_STATUSES else "draft",
        "pricing_model": pricing_model if pricing_model in {"percent", "fixed"} else "percent",
        "service_price_toman": parse_int(request.form.get("service_price_toman")),
        "organization_share_percent": parse_int(
            request.form.get("organization_share_percent"), 70
        ),
        "organization_fixed_toman": parse_int(request.form.get("organization_fixed_toman")),
        "subsidy_cap_per_parent_toman": parse_int(
            request.form.get("subsidy_cap_per_parent_toman")
        ),
        "total_budget_toman": parse_int(request.form.get("total_budget_toman")),
        "capacity": parse_int(request.form.get("capacity")),
        "starts_on": parse_iso_date(request.form.get("starts_on")),
        "ends_on": parse_iso_date(request.form.get("ends_on")),
        "eligible_services_json": json.dumps(
            [
                item.strip()
                for item in request.form.get("eligible_services", "").splitlines()
                if item.strip()
            ],
            ensure_ascii=False,
        ),
    }
    errors = []
    duplicate = SponsoredProject.query.filter_by(code=code).first() if code else None
    if len(values["name"]) < 3:
        errors.append("عنوان پروژه باید حداقل سه نویسه باشد.")
    if not re.fullmatch(r"[A-Z0-9-]{4,24}", code):
        errors.append("کد حمایت باید ۴ تا ۲۴ نویسه انگلیسی، عدد یا خط تیره باشد.")
    elif duplicate and (not project or duplicate.id != project.id):
        errors.append("این کد حمایت قبلاً استفاده شده است.")
    if values["service_price_toman"] <= 0:
        errors.append("مبلغ پایه خدمت باید بیشتر از صفر باشد.")
    if not 0 <= values["organization_share_percent"] <= 100:
        errors.append("درصد سهم سازمان باید بین صفر تا صد باشد.")
    if values["pricing_model"] == "fixed" and values["organization_fixed_toman"] < 0:
        errors.append("مبلغ ثابت حمایت نامعتبر است.")
    if any(values[key] < 0 for key in ("total_budget_toman", "capacity", "subsidy_cap_per_parent_toman")):
        errors.append("بودجه، ظرفیت و سقف حمایت نمی‌تواند منفی باشد.")
    if values["starts_on"] and values["ends_on"] and values["starts_on"] > values["ends_on"]:
        errors.append("تاریخ پایان باید پس از تاریخ شروع باشد.")
    return values, errors


@bp.get("/")
@login_required
@admin_required
def dashboard():
    stats = {
        "parents": User.query.filter_by(role="parent").count(),
        "children": Child.query.count(),
        "assessments": ParentingAssessment.query.count(),
        "topics": ScenarioTopic.query.count(),
        "forms": DynamicForm.query.count(),
        "projects": SponsoredProject.query.count(),
        "profiles": ChildProfileSnapshot.query.count(),
        "style_assessments": ParentingStyleAssessment.query.count(),
        "recommendations": RecommendationRun.query.count(),
        "outcomes": HomeActionOutcome.query.count(),
        "weekly_plans": WeeklyPlan.query.count(),
        "lessons": MicroLesson.query.filter_by(status="published").count(),
    }
    recent_users = User.query.order_by(User.created_at.desc()).limit(6).all()
    return render_template("admin/dashboard.html", stats=stats, recent_users=recent_users)


def instrument_publish_errors(instrument):
    errors = []
    dimensions = set(instrument.scoring_schema.get("dimensions", {}).keys())
    question_dimensions = {item.dimension for item in instrument.questions}
    if not instrument.source_reference.strip():
        errors.append("منبع دقیق نسخه پرسش‌نامه ثبت نشده است.")
    if not instrument.license_note.strip():
        errors.append("وضعیت مجوز استفاده و ترجمه ثبت نشده است.")
    if len(instrument.questions) < 6:
        errors.append("برای انتشار دست‌کم ۶ سؤال معتبر لازم است.")
    if dimensions and not dimensions.issubset(question_dimensions):
        errors.append("برای همه ابعاد تعریف‌شده باید سؤال وجود داشته باشد.")
    return errors


@bp.route("/assessments/baumrind", methods=["GET", "POST"])
@login_required
@admin_required
def baumrind_instrument():
    instrument = AssessmentInstrument.query.filter_by(framework_slug="baumrind").order_by(
        AssessmentInstrument.created_at.desc()
    ).first()
    if not instrument:
        instrument = AssessmentInstrument(
            framework_slug="baumrind",
            title="چارچوب سبک‌های فرزندپروری بامریند",
            version="awaiting-scientific-approval",
            created_by=current_user.id,
        )
        db.session.add(instrument)
        db.session.commit()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_metadata":
            instrument.title = request.form.get("title", "").strip()[:180]
            instrument.version = request.form.get("version", "").strip()[:40]
            instrument.source_reference = request.form.get("source_reference", "").strip()[:500]
            instrument.license_note = request.form.get("license_note", "").strip()[:500]
            instrument.disclaimer = request.form.get("disclaimer", "").strip()[:700]
            if not instrument.created_by:
                instrument.created_by = current_user.id
            if not instrument.title or not instrument.version:
                flash("عنوان و نسخه ابزار الزامی است.", "danger")
            else:
                if instrument.status == "published":
                    instrument.status = "review"
                    instrument.approved_by = None
                    instrument.approved_at = None
                db.session.commit()
                flash("مشخصات علمی ابزار ذخیره شد؛ تغییر ابزار نیازمند انتشار دوباره است.", "success")
                return redirect(url_for("admin.baumrind_instrument"))
        elif action == "import_questions":
            try:
                payload = json.loads(request.form.get("questions_json", "[]"))
            except ValueError:
                payload = None
            dimensions = set(instrument.scoring_schema.get("dimensions", {}).keys())
            errors = []
            normalized = []
            if not isinstance(payload, list):
                errors.append("ساختار JSON باید یک آرایه از سؤال‌ها باشد.")
            else:
                seen_codes = set()
                for index, item in enumerate(payload, 1):
                    if not isinstance(item, dict):
                        errors.append(f"ردیف {index} ساختار معتبر ندارد.")
                        continue
                    code = re.sub(r"[^a-zA-Z0-9_-]", "", str(item.get("code", "")))[:60]
                    text_value = str(item.get("text", "")).strip()[:700]
                    dimension = str(item.get("dimension", "")).strip()
                    try:
                        weight = float(item.get("weight", 1))
                    except (TypeError, ValueError):
                        weight = 0
                    if not code or code in seen_codes:
                        errors.append(f"کد سؤال در ردیف {index} خالی یا تکراری است.")
                    if len(text_value) < 5:
                        errors.append(f"متن سؤال ردیف {index} کافی نیست.")
                    if dimension not in dimensions:
                        errors.append(f"بُعد سؤال ردیف {index} معتبر نیست.")
                    if weight <= 0:
                        errors.append(f"وزن سؤال ردیف {index} باید مثبت باشد.")
                    seen_codes.add(code)
                    normalized.append(
                        {
                            "code": code,
                            "text": text_value,
                            "dimension": dimension,
                            "weight": weight,
                            "reverse_score": bool(item.get("reverse_score", False)),
                            "is_required": bool(item.get("is_required", True)),
                        }
                    )
            if errors:
                for error in errors[:12]:
                    flash(error, "danger")
            else:
                for question in list(instrument.questions):
                    db.session.delete(question)
                db.session.flush()
                for order, item in enumerate(normalized, 1):
                    db.session.add(
                        AssessmentQuestion(
                            instrument_id=instrument.id,
                            sort_order=order,
                            **item,
                        )
                    )
                instrument.status = "review"
                instrument.approved_by = None
                instrument.approved_at = None
                db.session.commit()
                flash(f"{len(normalized)} سؤال وارد و ابزار به وضعیت بازبینی منتقل شد.", "success")
                return redirect(url_for("admin.baumrind_instrument"))
        elif action == "publish":
            errors = instrument_publish_errors(instrument)
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                instrument.status = "published"
                instrument.approved_by = current_user.id
                instrument.approved_at = utcnow()
                db.session.commit()
                flash("نسخه تأیید و برای والدین منتشر شد.", "success")
                return redirect(url_for("admin.baumrind_instrument"))
        elif action == "unpublish":
            instrument.status = "review"
            instrument.approved_by = None
            instrument.approved_at = None
            db.session.commit()
            flash("انتشار ابزار متوقف شد؛ نتایج قبلی با نسخه خود حفظ می‌شوند.", "info")
            return redirect(url_for("admin.baumrind_instrument"))

    dimensions = instrument.scoring_schema.get("dimensions", {})
    usage_count = ParentingStyleAssessment.query.filter_by(instrument_id=instrument.id).count()
    return render_template(
        "admin/baumrind_instrument.html",
        instrument=instrument,
        dimensions=dimensions,
        usage_count=usage_count,
        publish_errors=instrument_publish_errors(instrument),
    )


@bp.route("/personalization", methods=["GET", "POST"])
@login_required
@admin_required
def personalization_rules():
    topics = ScenarioTopic.query.order_by(ScenarioTopic.id).all()
    topic_id = request.values.get("topic_id", type=int) or (topics[0].id if topics else None)
    selected_topic = db.session.get(ScenarioTopic, topic_id) if topic_id else None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_rule":
            selected_topic = db.session.get(
                ScenarioTopic, request.form.get("topic_id", type=int)
            )
            if not selected_topic:
                abort(404)
            rule_id = request.form.get("rule_id", type=int)
            rule = db.session.get(PersonalizationRule, rule_id) if rule_id else None
            if rule and rule.topic_id != selected_topic.id:
                abort(404)
            name = request.form.get("name", "").strip()[:180]
            title = request.form.get("recommendation_title", "").strip()[:220]
            recommendation_text = request.form.get("recommendation_text", "").strip()
            min_severity = max(1, min(5, request.form.get("min_severity", 1, type=int)))
            max_severity = max(1, min(5, request.form.get("max_severity", 5, type=int)))
            priority = max(0, min(999, request.form.get("priority", 50, type=int)))
            status = request.form.get("status", "draft")
            if status not in {"draft", "published"}:
                status = "draft"
            allowed = {
                "anger_patterns": {"explosion", "withdrawal", "crying", "arguing", "mixed"},
                "triggers": {
                    "direct_pressure",
                    "sudden_change",
                    "fatigue",
                    "screen_limit",
                    "criticism",
                    "sibling_conflict",
                },
                "calming": {
                    "quiet_space",
                    "conversation",
                    "movement",
                    "time",
                    "connection",
                    "structured_choice",
                },
                "priorities": {"anger", "screen", "school", "motivation", "honesty", "friends"},
                "styles": {"مقتدرانه", "مستبدانه", "سهل‌گیرانه"},
                "previous_outcomes": {"helped", "neutral", "worsened", "not_done"},
            }
            conditions = {
                key: [value for value in request.form.getlist(key) if value in values]
                for key, values in allowed.items()
            }
            conditions = {key: value for key, value in conditions.items() if value}
            relationship_min = request.form.get("relationship_score_min", type=int)
            relationship_max = request.form.get("relationship_score_max", type=int)
            if relationship_min is not None:
                conditions["relationship_score_min"] = max(0, min(100, relationship_min))
            if relationship_max is not None:
                conditions["relationship_score_max"] = max(0, min(100, relationship_max))
            errors = []
            if len(name) < 3 or len(title) < 3 or len(recommendation_text) < 10:
                errors.append("نام، عنوان و متن راهکار را کامل وارد کنید.")
            if min_severity > max_severity:
                errors.append("حداقل شدت نمی‌تواند از حداکثر بیشتر باشد.")
            if (
                relationship_min is not None
                and relationship_max is not None
                and relationship_min > relationship_max
            ):
                errors.append("بازه امتیاز رابطه معتبر نیست.")
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                if not rule:
                    rule = PersonalizationRule(
                        topic_id=selected_topic.id,
                        created_by=current_user.id,
                    )
                    db.session.add(rule)
                else:
                    rule.version += 1
                rule.name = name
                rule.status = status
                rule.priority = priority
                rule.min_severity = min_severity
                rule.max_severity = max_severity
                rule.conditions_json = json.dumps(conditions, ensure_ascii=False)
                rule.recommendation_title = title
                rule.recommendation_text = recommendation_text
                rule.reason_template = request.form.get("reason_template", "").strip()[:700]
                rule.avoid_text = request.form.get("avoid_text", "").strip()
                rule.home_action = request.form.get("home_action", "").strip()[:700]
                rule.next_step_text = request.form.get("next_step_text", "").strip()[:700]
                skill = db.session.get(
                    SkillModule, request.form.get("skill_module_id", type=int)
                )
                rule.skill_module_id = skill.id if skill else None
                db.session.commit()
                flash(f"قاعده نسخه {rule.version} ذخیره شد.", "success")
                return redirect(
                    url_for("admin.personalization_rules", topic_id=selected_topic.id)
                )
        elif action == "archive_rule":
            rule = db.session.get(
                PersonalizationRule, request.form.get("rule_id", type=int)
            )
            if not rule:
                abort(404)
            rule.status = "archived"
            rule.version += 1
            db.session.commit()
            flash("قاعده بایگانی شد؛ پیشنهادهای قبلی بدون تغییر باقی می‌مانند.", "info")
            return redirect(url_for("admin.personalization_rules", topic_id=rule.topic_id))

    rules = (
        PersonalizationRule.query.filter_by(topic_id=selected_topic.id)
        .order_by(PersonalizationRule.priority.desc(), PersonalizationRule.id)
        .all()
        if selected_topic
        else []
    )
    edit_rule_id = request.args.get("edit_rule", type=int)
    edit_rule = db.session.get(PersonalizationRule, edit_rule_id) if edit_rule_id else None
    if edit_rule and (not selected_topic or edit_rule.topic_id != selected_topic.id):
        edit_rule = None
    skills = SkillModule.query.filter_by(is_published=True).order_by(SkillModule.sort_order).all()
    stats = {
        "published": PersonalizationRule.query.filter_by(status="published").count(),
        "runs": RecommendationRun.query.count(),
        "outcomes": HomeActionOutcome.query.count(),
        "helped": HomeActionOutcome.query.filter_by(outcome="helped").count(),
    }
    return render_template(
        "admin/personalization.html",
        topics=topics,
        selected_topic=selected_topic,
        rules=rules,
        edit_rule=edit_rule,
        skills=skills,
        stats=stats,
    )


@bp.route("/learning-path", methods=["GET", "POST"])
@login_required
@admin_required
def learning_path():
    domains = SkillDomain.query.order_by(SkillDomain.sort_order).all()
    modules = SkillModule.query.filter_by(is_published=True).order_by(SkillModule.sort_order).all()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_lesson":
            lesson_id = request.form.get("lesson_id", type=int)
            lesson = db.session.get(MicroLesson, lesson_id) if lesson_id else None
            domain = db.session.get(SkillDomain, request.form.get("domain_id", type=int))
            module = db.session.get(SkillModule, request.form.get("module_id", type=int))
            title = request.form.get("title", "").strip()[:180]
            slug = make_slug(request.form.get("slug", ""))[:100]
            objective = request.form.get("objective", "").strip()[:500]
            body = request.form.get("body", "").strip()
            practice = request.form.get("practice", "").strip()[:700]
            pitfall = request.form.get("common_pitfall", "").strip()[:700]
            status = request.form.get("status", "draft")
            duration = max(2, min(30, request.form.get("duration", 7, type=int)))
            duplicate = MicroLesson.query.filter_by(slug=slug).first()
            errors = []
            if not domain or not module:
                errors.append("حوزه و مهارت معتبر را انتخاب کنید.")
            if len(title) < 3 or len(body) < 20 or len(objective) < 10:
                errors.append("عنوان، هدف و متن ریزدرس را کامل وارد کنید.")
            if duplicate and (not lesson or duplicate.id != lesson.id):
                errors.append("شناسه این ریزدرس قبلاً استفاده شده است.")
            if status not in {"draft", "published"}:
                status = "draft"
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                if not lesson:
                    lesson = MicroLesson(slug=slug, created_by=current_user.id)
                    db.session.add(lesson)
                else:
                    lesson.version += 1
                lesson.domain_id = domain.id
                lesson.module_id = module.id
                lesson.title = title
                lesson.slug = slug
                lesson.objective = objective
                lesson.body = body
                lesson.practice = practice
                lesson.common_pitfall = pitfall
                lesson.duration = duration
                lesson.status = status
                db.session.commit()
                flash(f"ریزدَرس نسخه {lesson.version} ذخیره شد.", "success")
                return redirect(url_for("admin.learning_path"))
        elif action == "archive_lesson":
            lesson = db.session.get(MicroLesson, request.form.get("lesson_id", type=int))
            if not lesson:
                abort(404)
            lesson.status = "archived"
            lesson.version += 1
            db.session.commit()
            flash("ریزدَرس بایگانی شد؛ برنامه‌های قبلی همچنان محفوظ‌اند.", "info")
            return redirect(url_for("admin.learning_path"))

    lessons = MicroLesson.query.order_by(MicroLesson.sort_order, MicroLesson.id).all()
    edit_lesson_id = request.args.get("edit_lesson", type=int)
    edit_lesson = db.session.get(MicroLesson, edit_lesson_id) if edit_lesson_id else None
    stats = {
        "domains": len(domains),
        "published_lessons": MicroLesson.query.filter_by(status="published").count(),
        "active_plans": WeeklyPlan.query.filter(
            WeeklyPlan.status.in_(["active", "awaiting_review"])
        ).count(),
        "completed_actions": DailyAction.query.filter_by(status="completed").count(),
        "reviews": PlanReview.query.count(),
    }
    return render_template(
        "admin/learning_path.html",
        domains=domains,
        modules=modules,
        lessons=lessons,
        edit_lesson=edit_lesson,
        stats=stats,
    )


@bp.route("/assistant-control", methods=["GET", "POST"])
@login_required
@admin_required
def assistant_control():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_protocol":
            protocol_id = request.form.get("protocol_id", type=int)
            protocol = db.session.get(SafetyProtocol, protocol_id) if protocol_id else None
            title = request.form.get("title", "").strip()[:180]
            slug = make_slug(request.form.get("slug", ""))[:100]
            response_title = request.form.get("response_title", "").strip()[:220]
            response_text = request.form.get("response_text", "").strip()
            status = request.form.get("status", "draft")
            priority = max(0, min(999, request.form.get("priority", 100, type=int)))
            keywords = [
                item.strip()
                for item in re.split(r"[,،\n]+", request.form.get("trigger_keywords", ""))
                if item.strip()
            ]
            steps = [
                item.strip()
                for item in request.form.get("immediate_steps", "").splitlines()
                if item.strip()
            ]
            duplicate = SafetyProtocol.query.filter_by(slug=slug).first()
            errors = []
            if len(title) < 3 or len(response_title) < 3 or len(response_text) < 30:
                errors.append("عنوان و متن پاسخ ایمنی را کامل وارد کنید.")
            if not keywords or not steps:
                errors.append("دست‌کم یک کلیدواژه و یک قدم فوری لازم است.")
            if duplicate and (not protocol or duplicate.id != protocol.id):
                errors.append("شناسه پروتکل تکراری است.")
            if status not in {"draft", "published"}:
                status = "draft"
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                if not protocol:
                    protocol = SafetyProtocol(slug=slug, created_by=current_user.id)
                    db.session.add(protocol)
                else:
                    protocol.version += 1
                protocol.slug = slug
                protocol.title = title
                protocol.response_title = response_title
                protocol.response_text = response_text
                protocol.trigger_keywords_json = json.dumps(keywords, ensure_ascii=False)
                protocol.immediate_steps_json = json.dumps(steps, ensure_ascii=False)
                protocol.priority = priority
                protocol.status = status
                db.session.commit()
                flash(f"پروتکل نسخه {protocol.version} ذخیره شد.", "success")
                return redirect(url_for("admin.assistant_control"))
        elif action == "archive_protocol":
            protocol = db.session.get(
                SafetyProtocol, request.form.get("protocol_id", type=int)
            )
            if not protocol:
                abort(404)
            protocol.status = "archived"
            protocol.version += 1
            db.session.commit()
            flash("پروتکل بایگانی شد.", "info")
            return redirect(url_for("admin.assistant_control"))

    protocols = SafetyProtocol.query.order_by(
        SafetyProtocol.priority.desc(), SafetyProtocol.id
    ).all()
    edit_protocol_id = request.args.get("edit_protocol", type=int)
    edit_protocol = (
        db.session.get(SafetyProtocol, edit_protocol_id) if edit_protocol_id else None
    )
    recent_messages = (
        AssistantMessage.query.filter_by(role="assistant")
        .order_by(AssistantMessage.created_at.desc())
        .limit(12)
        .all()
    )
    stats = {
        "conversations": AssistantConversation.query.count(),
        "answers": AssistantMessage.query.filter_by(role="assistant").count(),
        "grounded": AssistantMessage.query.filter_by(
            role="assistant", decision_type="grounded"
        ).count(),
        "safety": AssistantMessage.query.filter_by(
            role="assistant", decision_type="safety"
        ).count(),
        "refused": AssistantMessage.query.filter(
            AssistantMessage.role == "assistant",
            AssistantMessage.decision_type.in_(["out_of_scope", "policy_boundary"]),
        ).count(),
        "helpful": AssistantFeedback.query.filter_by(helpful=True).count(),
    }
    return render_template(
        "admin/assistant_control.html",
        protocols=protocols,
        edit_protocol=edit_protocol,
        recent_messages=recent_messages,
        stats=stats,
    )


@bp.route("/projects", methods=["GET", "POST"])
@login_required
@admin_required
def projects():
    organizations = Organization.query.order_by(Organization.name).all()
    if request.method == "POST":
        values, errors = project_form_values()
        organization_id = request.form.get("organization_id", type=int)
        organization = db.session.get(Organization, organization_id) if organization_id else None
        new_organization_name = request.form.get("new_organization_name", "").strip()
        if not organization and len(new_organization_name) < 3:
            errors.append("یک سازمان موجود را انتخاب کنید یا نام سازمان جدید را وارد کنید.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not organization:
                organization = Organization(
                    name=new_organization_name,
                    legal_name=request.form.get("legal_name", "").strip(),
                    registration_no=request.form.get("registration_no", "").strip(),
                    contact_name=request.form.get("contact_name", "").strip(),
                    contact_mobile=normalize_digits(request.form.get("contact_mobile", "")),
                )
                db.session.add(organization)
                db.session.flush()
            project = SponsoredProject(
                organization_id=organization.id,
                created_by=current_user.id,
                **values,
            )
            db.session.add(project)
            db.session.flush()
            audit_project(
                project,
                "project_created",
                {"status": project.status, "code": project.code},
            )
            db.session.commit()
            flash("پروژه سازمانی و دفتر حمایت آن ساخته شد.", "success")
            return redirect(url_for("admin.project_detail", project_id=project.id))

    project_rows = SponsoredProject.query.order_by(SponsoredProject.created_at.desc()).all()
    totals = {
        "organizations": Organization.query.count(),
        "projects": len(project_rows),
        "members": ProjectMembership.query.filter(ProjectMembership.status.in_(["active", "pending"])).count(),
        "committed": sum(item.committed_subsidy_toman for item in project_rows),
    }
    return render_template(
        "admin/projects.html",
        projects=project_rows,
        organizations=organizations,
        totals=totals,
    )


@bp.route("/projects/<int:project_id>", methods=["GET", "POST"])
@login_required
@admin_required
def project_detail(project_id):
    project = db.get_or_404(SponsoredProject, project_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_project":
            values, errors = project_form_values(project)
            organization = db.session.get(
                Organization, request.form.get("organization_id", type=int)
            )
            if not organization:
                errors.append("سازمان انتخاب‌شده معتبر نیست.")
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                before = {"status": project.status, "code": project.code}
                project.organization_id = organization.id
                for key, value in values.items():
                    setattr(project, key, value)
                audit_project(
                    project,
                    "project_updated",
                    {"before": before, "after": {"status": project.status, "code": project.code}},
                )
                db.session.commit()
                flash("تنظیمات پروژه به‌روزرسانی شد.", "success")
                return redirect(url_for("admin.project_detail", project_id=project.id))
        elif action == "allocation_status":
            allocation = db.session.get(
                PaymentAllocation, request.form.get("allocation_id", type=int)
            )
            new_status = request.form.get("status", "")
            if not allocation or allocation.membership.project_id != project.id:
                abort(404)
            if new_status not in ALLOCATION_TRANSITIONS.get(allocation.status, set()):
                flash("این تغییر وضعیت مالی مجاز نیست.", "danger")
            else:
                old_status = allocation.status
                allocation.status = new_status
                allocation.updated_by = current_user.id
                allocation.note = request.form.get("note", "").strip()[:500]
                if new_status == "parent_paid":
                    allocation.parent_paid_at = utcnow()
                    allocation.membership.status = "active"
                elif new_status == "settled":
                    allocation.organization_settled_at = utcnow()
                elif new_status in {"cancelled", "refunded"}:
                    allocation.membership.status = "cancelled"
                    allocation.membership.ended_at = utcnow()
                audit_project(
                    project,
                    "allocation_status_changed",
                    {"allocation_id": allocation.id, "from": old_status, "to": new_status},
                )
                db.session.commit()
                flash("وضعیت مالی ثبت شد.", "success")
            return redirect(url_for("admin.project_detail", project_id=project.id))
        elif action == "cancel_membership":
            membership = db.session.get(
                ProjectMembership, request.form.get("membership_id", type=int)
            )
            if not membership or membership.project_id != project.id:
                abort(404)
            membership.status = "cancelled"
            membership.ended_at = utcnow()
            for allocation in membership.allocations:
                if allocation.status in {"reserved", "parent_paid"}:
                    allocation.status = "cancelled"
                    allocation.updated_by = current_user.id
            audit_project(
                project,
                "membership_cancelled",
                {"membership_id": membership.id, "user_id": membership.user_id},
            )
            db.session.commit()
            flash("عضویت و تعهدهای باز آن لغو شد.", "success")
            return redirect(url_for("admin.project_detail", project_id=project.id))

    organizations = Organization.query.order_by(Organization.name).all()
    memberships = sorted(project.memberships, key=lambda item: item.joined_at, reverse=True)
    split = project.calculate_split()
    return render_template(
        "admin/project_detail.html",
        project=project,
        organizations=organizations,
        memberships=memberships,
        split=split,
    )


@bp.get("/projects/<int:project_id>/export.csv")
@login_required
@admin_required
def project_export(project_id):
    project = db.get_or_404(SponsoredProject, project_id)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "نام والد",
            "موبایل",
            "وضعیت عضویت",
            "مبلغ خدمت (تومان)",
            "سهم سازمان (تومان)",
            "سهم والد (تومان)",
            "وضعیت مالی",
            "تاریخ عضویت",
        ]
    )
    for membership in sorted(project.memberships, key=lambda item: item.joined_at):
        if not membership.allocations:
            writer.writerow(
                [membership.parent.full_name, membership.parent.mobile, membership.status, 0, 0, 0, "", membership.joined_at.isoformat()]
            )
        for allocation in membership.allocations:
            writer.writerow(
                [
                    membership.parent.full_name,
                    membership.parent.mobile,
                    membership.status,
                    allocation.gross_amount_toman,
                    allocation.organization_amount_toman,
                    allocation.parent_amount_toman,
                    allocation.status,
                    membership.joined_at.isoformat(),
                ]
            )
    audit_project(project, "report_exported", {"format": "csv"})
    db.session.commit()
    filename = f"project-{project.id}-financial-report.csv"
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.get("/users")
@login_required
@admin_required
def users():
    page = max(1, request.args.get("page", 1, type=int))
    pagination = User.query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/users.html", pagination=pagination)


@bp.route("/tree", methods=["GET", "POST"])
@login_required
@admin_required
def tree_builder():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_topic":
            title = request.form.get("title", "").strip()
            slug = make_slug(request.form.get("slug"))
            if not title or ScenarioTopic.query.filter_by(slug=slug).first():
                flash("عنوان را وارد کنید و نامک یکتا باشد.", "danger")
            else:
                topic = ScenarioTopic(
                    title=title,
                    slug=slug,
                    description=request.form.get("description", "").strip(),
                    icon=request.form.get("icon", "fa-comments"),
                )
                db.session.add(topic)
                db.session.flush()
                labels = ["خفیف", "قابل توجه", "جدی", "شدید", "بحرانی"]
                for index, label in enumerate(labels, 1):
                    db.session.add(ScenarioLevel(topic_id=topic.id, level=index, label=label))
                db.session.commit()
                flash("موضوع و پنج سطح شدت ساخته شد.", "success")
                return redirect(url_for("admin.tree_builder", topic_id=topic.id))
        elif action == "save_level":
            level = db.session.get(ScenarioLevel, request.form.get("level_id", type=int))
            if not level:
                abort(404)
            level.description = request.form.get("description", "").strip()
            level.recommended_action = request.form.get("recommended_action", "").strip()
            level.wrong_action = request.form.get("wrong_action", "").strip()
            level.consequence = request.form.get("consequence", "").strip()
            db.session.commit()
            flash("محتوای این سطح ذخیره شد.", "success")
            return redirect(url_for("admin.tree_builder", topic_id=level.topic_id, level=level.level))
        elif action == "add_node":
            level = db.session.get(ScenarioLevel, request.form.get("level_id", type=int))
            if not level:
                abort(404)
            node = DecisionNode(
                level_id=level.id,
                parent_id=request.form.get("parent_id", type=int),
                option_label=request.form.get("option_label", "").strip(),
                title=request.form.get("node_title", "").strip(),
                content=request.form.get("content", "").strip(),
                consequence=request.form.get("node_consequence", "").strip(),
                is_recommended=request.form.get("is_recommended") == "1",
                sort_order=len(level.nodes) + 1,
            )
            if node.option_label and node.title:
                db.session.add(node)
                db.session.commit()
                flash("شاخه جدید به درخت تصمیم اضافه شد.", "success")
            else:
                flash("عنوان گزینه و عنوان نتیجه الزامی است.", "danger")
            return redirect(url_for("admin.tree_builder", topic_id=level.topic_id, level=level.level))

    topics = ScenarioTopic.query.order_by(ScenarioTopic.id).all()
    topic_id = request.args.get("topic_id", type=int) or (topics[0].id if topics else None)
    level_number = min(5, max(1, request.args.get("level", 1, type=int)))
    selected_topic = db.session.get(ScenarioTopic, topic_id) if topic_id else None
    selected_level = None
    if selected_topic:
        selected_level = ScenarioLevel.query.filter_by(
            topic_id=selected_topic.id, level=level_number
        ).first()
    return render_template(
        "admin/tree_builder.html",
        topics=topics,
        selected_topic=selected_topic,
        selected_level=selected_level,
        level_number=level_number,
    )


@bp.route("/forms", methods=["GET", "POST"])
@login_required
@admin_required
def form_builder():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = make_slug(request.form.get("slug"))
        try:
            fields = json.loads(request.form.get("schema_json", "[]"))
        except ValueError:
            fields = []
        allowed = {"text", "textarea", "number", "radio", "select", "scale"}
        fields = [field for field in fields if field.get("type") in allowed and field.get("label")]
        form_id = request.form.get("form_id", type=int)
        form = db.session.get(DynamicForm, form_id) if form_id else None
        duplicate = DynamicForm.query.filter_by(slug=slug).first()
        if duplicate and duplicate.id != form_id:
            flash("این نامک قبلاً استفاده شده است.", "danger")
        elif not title or not fields:
            flash("عنوان و دست‌کم یک فیلد لازم است.", "danger")
        else:
            if not form:
                form = DynamicForm(created_by=current_user.id)
                db.session.add(form)
            form.title = title
            form.slug = slug
            form.description = request.form.get("description", "").strip()
            form.status = request.form.get("status", "draft")
            form.schema_json = json.dumps(fields, ensure_ascii=False)
            db.session.commit()
            flash("فرم و ساختار فیلدها ذخیره شد.", "success")
            return redirect(url_for("admin.form_builder", form_id=form.id))

    forms = DynamicForm.query.order_by(DynamicForm.created_at.desc()).all()
    form_id = request.args.get("form_id", type=int)
    selected = db.session.get(DynamicForm, form_id) if form_id else None
    return render_template("admin/form_builder.html", forms=forms, selected=selected)

