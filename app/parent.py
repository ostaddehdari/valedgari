import json
import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    AssistantConversation,
    AssistantFeedback,
    AssistantMessage,
    AssessmentInstrument,
    Child,
    ChildProfileSnapshot,
    DailyAction,
    HomeActionOutcome,
    PlanReview,
    PaymentAllocation,
    ParentingAssessment,
    ParentingStyleAssessment,
    ProjectAuditLog,
    ProjectMembership,
    RecommendationRun,
    ScenarioAttempt,
    ScenarioLevel,
    ScenarioTopic,
    SkillModule,
    SkillProgress,
    SponsoredProject,
    WeeklyPlan,
    utcnow,
)
from .assistant_engine import build_assistant_response
from .learning_path import build_weekly_plan, suggested_topic_for_child
from .recommendation_engine import build_personalized_recommendation


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

PROFILE_SCALE_FIELDS = {
    "emotional_intensity": "شدت واکنش هیجانی",
    "adaptability": "سازگاری با تغییر",
    "sensory_sensitivity": "حساسیت به محرک‌های محیطی",
    "communication_openness": "آمادگی برای گفت‌وگو",
    "persistence": "پشتکار در کارها",
    "social_comfort": "راحتی در جمع",
}
PROFILE_OPTIONS = {
    "strengths": {
        "empathy": "همدلی",
        "creativity": "خلاقیت",
        "responsibility": "مسئولیت‌پذیری",
        "persistence": "پشتکار",
        "humor": "شوخ‌طبعی",
        "learning": "علاقه به یادگیری",
    },
    "triggers": {
        "direct_pressure": "فشار و دستور مستقیم",
        "sudden_change": "تغییر ناگهانی برنامه",
        "fatigue": "خستگی یا گرسنگی",
        "screen_limit": "محدودشدن موبایل و بازی",
        "criticism": "انتقاد یا مقایسه",
        "sibling_conflict": "تعارض با خواهر یا برادر",
    },
    "calming": {
        "quiet_space": "فضای آرام و خلوت",
        "conversation": "گفت‌وگوی آرام",
        "movement": "حرکت و فعالیت بدنی",
        "time": "زمان کوتاه برای فروکش هیجان",
        "connection": "تماس عاطفی و اطمینان‌بخشی",
        "structured_choice": "دادن دو انتخاب محدود",
    },
    "priorities": {
        "anger": "خشم و تعارض",
        "screen": "موبایل و فضای مجازی",
        "school": "درس و مدرسه",
        "motivation": "انگیزه و مسئولیت",
        "honesty": "صداقت و اعتماد",
        "friends": "دوستان و ارتباط اجتماعی",
    },
}
ANGER_PATTERNS = {
    "explosion": "واکنش سریع و پرصدا",
    "withdrawal": "کناره‌گیری و سکوت",
    "crying": "گریه و درماندگی",
    "arguing": "بحث طولانی و چانه‌زنی",
    "mixed": "الگوی متغیر بر اساس موقعیت",
}
RELATIONSHIP_QUESTIONS = [
    "نشانه‌های اولیه ناراحتی این فرزند را قبل از اوج تنش تشخیص می‌دهم.",
    "می‌دانم چه زمان و فضایی برای گفت‌وگو با او مناسب‌تر است.",
    "قوانین خانه برای این فرزند روشن و قابل پیش‌بینی است.",
    "در زمان تعارض می‌توانم پیش از واکنش کمی مکث کنم.",
    "این فرزند معمولاً احساس می‌کند حرفش شنیده شده است.",
    "بعد از تعارض برای ترمیم رابطه قدم مشخصی برمی‌داریم.",
    "می‌دانم چه چیزهایی او را آرام‌تر یا برانگیخته‌تر می‌کند.",
    "برای حل مسئله می‌توانیم به یک توافق کوچک و قابل اجرا برسیم.",
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


def latest_profile_snapshot(child_id, profile_type):
    return (
        ChildProfileSnapshot.query.filter_by(
            user_id=current_user.id,
            child_id=child_id,
            profile_type=profile_type,
        )
        .order_by(ChildProfileSnapshot.version_no.desc())
        .first()
    )


def allowed_multi_values(field_name):
    allowed = PROFILE_OPTIONS[field_name]
    return [item for item in request.form.getlist(field_name) if item in allowed]


def style_interpretation(style_key, label):
    notes = {
        "authoritative": "این الگو معمولاً بر گرمی رابطه همراه با مرز روشن تأکید دارد.",
        "authoritarian": "این نتیجه نشان می‌دهد بررسی میزان کنترل، گفت‌وگو و انعطاف می‌تواند مفید باشد.",
        "permissive": "این نتیجه نشان می‌دهد روشن‌ترکردن مرزها و پیگیری پیامدها می‌تواند مفید باشد.",
    }
    return (
        f"بالاترین امتیاز این اجرا در بُعد «{label}» است. "
        f"{notes.get(style_key, 'نتیجه باید همراه با شرایط رابطه و پاسخ‌های همان فرزند تفسیر شود')} "
        "این خروجی تشخیص یا برچسب ثابت نیست."
    )


def calculate_style_scores(instrument, form_data):
    schema = instrument.scoring_schema
    scale_min = int(schema.get("scale_min", 1))
    scale_max = int(schema.get("scale_max", 5))
    dimensions = schema.get("dimensions", {})
    totals = {key: {"sum": 0.0, "weight": 0.0} for key in dimensions}
    answers = {}
    for question in instrument.questions:
        try:
            value = int(form_data.get(f"q_{question.id}", "0"))
        except (TypeError, ValueError):
            value = 0
        if question.is_required and not scale_min <= value <= scale_max:
            return None, None, "لطفاً به همه گزاره‌های الزامی پاسخ دهید."
        if not value:
            continue
        answers[str(question.id)] = value
        scored_value = scale_max + scale_min - value if question.reverse_score else value
        if question.dimension not in totals:
            totals[question.dimension] = {"sum": 0.0, "weight": 0.0}
        totals[question.dimension]["sum"] += scored_value * question.weight
        totals[question.dimension]["weight"] += question.weight
    scores = {}
    for key, item in totals.items():
        if not item["weight"]:
            scores[key] = 0
            continue
        mean = item["sum"] / item["weight"]
        scores[key] = round((mean - scale_min) / (scale_max - scale_min) * 100)
    return answers, scores, None


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
    child_profile = latest_profile_snapshot(child.id, "initial") if child else None
    relationship_profile = latest_profile_snapshot(child.id, "relationship") if child else None
    style_result = None
    latest_recommendation = None
    active_plan = None
    today_action = None
    if child:
        style_result = (
            ParentingStyleAssessment.query.filter_by(
                user_id=current_user.id, child_id=child.id
            )
            .order_by(ParentingStyleAssessment.created_at.desc())
            .first()
        )
        latest_recommendation = (
            RecommendationRun.query.filter_by(user_id=current_user.id, child_id=child.id)
            .order_by(RecommendationRun.created_at.desc())
            .first()
        )
        active_plan = (
            WeeklyPlan.query.filter(
                WeeklyPlan.user_id == current_user.id,
                WeeklyPlan.child_id == child.id,
                WeeklyPlan.status.in_(["active", "awaiting_review"]),
            )
            .order_by(WeeklyPlan.created_at.desc())
            .first()
        )
        today_action = active_plan.current_action if active_plan else None
    return render_template(
        "parent/dashboard.html",
        child=child,
        assessment=assessment,
        completed=completed,
        sponsored_memberships=sponsored_memberships,
        child_profile=child_profile,
        relationship_profile=relationship_profile,
        style_result=style_result,
        latest_recommendation=latest_recommendation,
        active_plan=active_plan,
        today_action=today_action,
    )


@bp.route("/child-profile", methods=["GET", "POST"])
@login_required
def child_profile():
    child = owned_child()
    if not child:
        flash("ابتدا پرونده یک فرزند را بسازید.", "warning")
        return redirect(url_for("parent.children"))
    if request.method == "POST":
        profile_type = request.form.get("profile_type")
        previous = latest_profile_snapshot(child.id, profile_type)
        version_no = (previous.version_no + 1) if previous else 1
        if profile_type == "initial":
            scales = {}
            for key in PROFILE_SCALE_FIELDS:
                value = request.form.get(key, type=int)
                if value not in range(1, 6):
                    flash("لطفاً به همه مقیاس‌های شناخت فرزند پاسخ دهید.", "danger")
                    return redirect(url_for("parent.child_profile", tab="initial"))
                scales[key] = value
            anger_pattern = request.form.get("anger_pattern", "")
            strengths = allowed_multi_values("strengths")
            triggers = allowed_multi_values("triggers")
            calming = allowed_multi_values("calming")
            priorities = allowed_multi_values("priorities")
            if anger_pattern not in ANGER_PATTERNS or not strengths or not triggers or not calming or not priorities:
                flash("در هر بخش دست‌کم یک گزینه و الگوی واکنش را مشخص کنید.", "danger")
                return redirect(url_for("parent.child_profile", tab="initial"))
            answers = {
                "scales": scales,
                "strengths": strengths,
                "triggers": triggers,
                "calming": calming,
                "priorities": priorities,
                "anger_pattern": anger_pattern,
                "parent_notes": request.form.get("parent_notes", "").strip()[:1200],
            }
            first_calming = PROFILE_OPTIONS["calming"][calming[0]]
            first_trigger = PROFILE_OPTIONS["triggers"][triggers[0]]
            summary = {
                "strengths": [PROFILE_OPTIONS["strengths"][key] for key in strengths],
                "triggers": [PROFILE_OPTIONS["triggers"][key] for key in triggers],
                "calming": [PROFILE_OPTIONS["calming"][key] for key in calming],
                "priorities": [PROFILE_OPTIONS["priorities"][key] for key in priorities],
                "anger_pattern": ANGER_PATTERNS[anger_pattern],
                "action_hint": (
                    f"در شروع تنش، محرک «{first_trigger}» را بررسی کنید و پیش از حل مسئله "
                    f"از «{first_calming}» کمک بگیرید."
                ),
            }
            source_version = "child-profile-internal-1"
        elif profile_type == "relationship":
            answers_list = []
            for index in range(len(RELATIONSHIP_QUESTIONS)):
                value = request.form.get(f"r{index}", type=int)
                if value not in range(1, 6):
                    flash("لطفاً به همه گزاره‌های رابطه پاسخ دهید.", "danger")
                    return redirect(url_for("parent.child_profile", tab="relationship"))
                answers_list.append(value)
            score = round(sum(answers_list) / (len(answers_list) * 5) * 100)
            if score >= 80:
                level = "پیوند و همکاری پایدار"
                hint = "همین الگوی گفت‌وگو و ترمیم را در موقعیت‌های دشوار نیز پیوسته نگه دارید."
            elif score >= 60:
                level = "پایه مناسب با چند نقطه قابل تقویت"
                hint = "یک نشانه اولیه تنش و یک زمان مناسب گفت‌وگو را این هفته ثبت کنید."
            elif score >= 40:
                level = "نیازمند تمرین هدفمند"
                hint = "از مکث والد و شنیدن احساس فرزند به‌عنوان دو قدم نخست شروع کنید."
            else:
                level = "شروع بازسازی ارتباط"
                hint = "فعلاً هدف را کوچک کنید: کاهش تنش و ساخت یک گفت‌وگوی کوتاه و امن."
            answers = {"items": answers_list}
            summary = {"score": score, "level": level, "action_hint": hint}
            source_version = "relationship-internal-1"
        else:
            abort(400)
        snapshot = ChildProfileSnapshot(
            user_id=current_user.id,
            child_id=child.id,
            profile_type=profile_type,
            version_no=version_no,
            answers_json=json.dumps(answers, ensure_ascii=False),
            summary_json=json.dumps(summary, ensure_ascii=False),
            source_version=source_version,
        )
        db.session.add(snapshot)
        db.session.commit()
        flash(f"نمای {child.name} با نسخه {version_no} ذخیره شد.", "success")
        return redirect(url_for("parent.child_profile", tab="summary"))

    initial = latest_profile_snapshot(child.id, "initial")
    relationship = latest_profile_snapshot(child.id, "relationship")
    history = ChildProfileSnapshot.query.filter_by(
        user_id=current_user.id, child_id=child.id
    ).order_by(ChildProfileSnapshot.created_at.desc()).all()
    return render_template(
        "parent/child_profile.html",
        child=child,
        initial=initial,
        relationship=relationship,
        history=history,
        scale_fields=PROFILE_SCALE_FIELDS,
        profile_options=PROFILE_OPTIONS,
        anger_patterns=ANGER_PATTERNS,
        relationship_questions=RELATIONSHIP_QUESTIONS,
        active_tab=request.args.get("tab", "summary"),
    )


@bp.route("/parenting-style", methods=["GET", "POST"])
@login_required
def parenting_style():
    child = owned_child()
    if not child:
        flash("ابتدا پرونده یک فرزند را بسازید.", "warning")
        return redirect(url_for("parent.children"))
    instrument = AssessmentInstrument.query.filter_by(
        framework_slug="baumrind", status="published"
    ).order_by(AssessmentInstrument.approved_at.desc()).first()
    if request.method == "POST":
        if not instrument:
            flash("نسخه علمی پرسش‌نامه هنوز منتشر نشده است.", "warning")
            return redirect(url_for("parent.parenting_style"))
        answers, scores, error = calculate_style_scores(instrument, request.form)
        if error:
            flash(error, "danger")
        else:
            dominant_key = max(scores, key=scores.get)
            dimensions = instrument.scoring_schema.get("dimensions", {})
            dominant_label = dimensions.get(dominant_key, dominant_key)
            result = ParentingStyleAssessment(
                instrument_id=instrument.id,
                user_id=current_user.id,
                child_id=child.id,
                answers_json=json.dumps(answers, ensure_ascii=False),
                scores_json=json.dumps(scores, ensure_ascii=False),
                dominant_style=dominant_label,
                interpretation=style_interpretation(dominant_key, dominant_label),
                instrument_version=instrument.version,
            )
            db.session.add(result)
            db.session.commit()
            flash(f"سنجش سبک در رابطه با {child.name} ذخیره شد.", "success")
            return redirect(url_for("parent.parenting_style"))
    latest = (
        ParentingStyleAssessment.query.filter_by(
            user_id=current_user.id, child_id=child.id
        )
        .order_by(ParentingStyleAssessment.created_at.desc())
        .first()
    )
    history = ParentingStyleAssessment.query.filter_by(
        user_id=current_user.id, child_id=child.id
    ).order_by(ParentingStyleAssessment.created_at.desc()).all()
    return render_template(
        "parent/parenting_style.html",
        child=child,
        instrument=instrument,
        latest=latest,
        history=history,
        dimensions=instrument.scoring_schema.get("dimensions", {}) if instrument else {},
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
    recommendation = build_personalized_recommendation(current_user.id, child, level) if level else None
    if request.method == "POST" and level:
        action = request.form.get("action", "decision")
        if action == "plan_recommendation" and recommendation:
            rule = recommendation["rule"]
            run = RecommendationRun(
                user_id=current_user.id,
                child_id=child.id,
                topic_id=level.topic_id,
                level_id=level.id,
                rule_id=rule.id if rule else None,
                rule_version=rule.version if rule else 0,
                status="planned",
                context_json=json.dumps(recommendation["context"], ensure_ascii=False),
                title=recommendation["title"],
                action_text=recommendation["action_text"],
                reasons_json=json.dumps(recommendation["reasons"], ensure_ascii=False),
                avoid_text=recommendation["avoid_text"],
                home_action=recommendation["home_action"],
                next_step_text=recommendation["next_step_text"],
                skill_module_id=(recommendation["skill"].id if recommendation["skill"] else None),
            )
            db.session.add(run)
            db.session.commit()
            flash(f"برنامه موقعیت برای {child.name} ذخیره شد؛ بعد از اجرا نتیجه را ثبت کنید.", "success")
            return redirect(url_for("parent.recommendation_detail", recommendation_id=run.id))
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
        recommendation=recommendation,
    )


@bp.route("/assistant", methods=["GET", "POST"])
@login_required
def assistant():
    child = owned_child()
    if not child:
        flash("ابتدا پرونده یک فرزند را بسازید.", "warning")
        return redirect(url_for("parent.children"))
    conversation = None
    conversation_id = request.values.get("conversation_id", type=int)
    if conversation_id:
        conversation = db.session.get(AssistantConversation, conversation_id)
        if (
            not conversation
            or conversation.user_id != current_user.id
            or conversation.child_id != child.id
        ):
            abort(404)
    elif not request.args.get("new"):
        conversation = (
            AssistantConversation.query.filter_by(
                user_id=current_user.id, child_id=child.id, status="active"
            )
            .order_by(AssistantConversation.updated_at.desc())
            .first()
        )
    if request.method == "POST":
        message_text = request.form.get("message", "").strip()
        if not 3 <= len(message_text) <= 2000:
            flash("پیام باید بین ۳ تا ۲۰۰۰ نویسه باشد.", "danger")
            return redirect(
                url_for(
                    "parent.assistant",
                    conversation_id=conversation.id if conversation else None,
                )
            )
        if not conversation:
            conversation = AssistantConversation(
                user_id=current_user.id,
                child_id=child.id,
                title=message_text[:70],
            )
            db.session.add(conversation)
            db.session.flush()
        db.session.add(
            AssistantMessage(
                conversation_id=conversation.id,
                role="user",
                body=message_text,
                decision_type="user",
                context_json=json.dumps(
                    {"child_id": child.id, "child_name": child.name}, ensure_ascii=False
                ),
            )
        )
        result = build_assistant_response(current_user.id, child, message_text)
        db.session.add(
            AssistantMessage(
                conversation_id=conversation.id,
                role="assistant",
                body=result["body"],
                decision_type=result["decision_type"],
                topic_id=result["topic"].id if result["topic"] else None,
                sources_json=json.dumps(result["sources"], ensure_ascii=False),
                context_json=json.dumps(result["context"], ensure_ascii=False),
            )
        )
        conversation.updated_at = utcnow()
        db.session.commit()
        return redirect(
            url_for("parent.assistant", conversation_id=conversation.id, _anchor="latest")
        )
    conversations = (
        AssistantConversation.query.filter_by(user_id=current_user.id, child_id=child.id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "parent/assistant.html",
        child=child,
        conversation=conversation,
        conversations=conversations,
    )


@bp.post("/assistant/messages/<int:message_id>/feedback")
@login_required
def assistant_feedback(message_id):
    message = db.session.get(AssistantMessage, message_id)
    if (
        not message
        or message.role != "assistant"
        or message.conversation.user_id != current_user.id
    ):
        abort(404)
    owned_child(message.conversation.child_id)
    value = request.form.get("helpful")
    if value not in {"yes", "no"}:
        abort(400)
    feedback = message.feedback or AssistantFeedback(
        message_id=message.id, user_id=current_user.id
    )
    feedback.helpful = value == "yes"
    feedback.note = request.form.get("note", "").strip()[:700]
    if not message.feedback:
        db.session.add(feedback)
    db.session.commit()
    flash("بازخورد شما برای بازبینی کیفیت ثبت شد.", "success")
    return redirect(
        url_for(
            "parent.assistant",
            conversation_id=message.conversation_id,
            _anchor=f"message-{message.id}",
        )
    )


@bp.route("/journey", methods=["GET", "POST"])
@login_required
def journey():
    child = owned_child()
    if not child:
        flash("ابتدا پرونده یک فرزند را بسازید.", "warning")
        return redirect(url_for("parent.children"))
    active_plan = (
        WeeklyPlan.query.filter(
            WeeklyPlan.user_id == current_user.id,
            WeeklyPlan.child_id == child.id,
            WeeklyPlan.status.in_(["active", "awaiting_review"]),
        )
        .order_by(WeeklyPlan.created_at.desc())
        .first()
    )
    topics = ScenarioTopic.query.filter_by(is_published=True).order_by(ScenarioTopic.id).all()
    suggested_topic = suggested_topic_for_child(current_user.id, child)
    if request.method == "POST":
        if active_plan:
            flash("برای این فرزند یک برنامه هفتگی فعال وجود دارد؛ ابتدا آن را مرور کنید.", "warning")
            return redirect(url_for("parent.plan_detail", plan_id=active_plan.id))
        topic = db.session.get(ScenarioTopic, request.form.get("topic_id", type=int))
        if not topic or not topic.is_published:
            abort(404)
        plan = build_weekly_plan(
            current_user.id,
            child,
            topic,
            request.form.get("goal_title", ""),
        )
        db.session.commit()
        flash(f"برنامه هفت‌روزه {child.name} ساخته شد؛ امروز فقط قدم اول را انجام دهید.", "success")
        return redirect(url_for("parent.plan_detail", plan_id=plan.id))
    history = (
        WeeklyPlan.query.filter_by(user_id=current_user.id, child_id=child.id)
        .order_by(WeeklyPlan.created_at.desc())
        .all()
    )
    return render_template(
        "parent/journey.html",
        child=child,
        active_plan=active_plan,
        topics=topics,
        suggested_topic=suggested_topic,
        history=history,
    )


@bp.get("/journey/<int:plan_id>")
@login_required
def plan_detail(plan_id):
    plan = db.session.get(WeeklyPlan, plan_id)
    if not plan or plan.user_id != current_user.id:
        abort(404)
    child = owned_child(plan.child_id)
    return render_template("parent/plan_detail.html", child=child, plan=plan)


@bp.post("/journey/actions/<int:action_id>")
@login_required
def complete_daily_action(action_id):
    action = db.session.get(DailyAction, action_id)
    if not action or action.plan.user_id != current_user.id:
        abort(404)
    owned_child(action.plan.child_id)
    if action.plan.status not in {"active", "awaiting_review"}:
        flash("این برنامه بسته شده است.", "warning")
        return redirect(url_for("parent.plan_detail", plan_id=action.plan.id))
    if action.status == "completed":
        flash("این قدم قبلاً تکمیل شده است.", "info")
        return redirect(url_for("parent.plan_detail", plan_id=action.plan.id))
    current_action = action.plan.current_action
    if not current_action or current_action.id != action.id:
        flash("قدم‌ها را به‌ترتیب انجام دهید تا مسیر قابل پیگیری بماند.", "warning")
        return redirect(url_for("parent.plan_detail", plan_id=action.plan.id))
    confidence = request.form.get("confidence", type=int)
    if confidence not in range(1, 6):
        flash("میزان اطمینان را از ۱ تا ۵ مشخص کنید.", "danger")
        return redirect(url_for("parent.plan_detail", plan_id=action.plan.id))
    action.status = "completed"
    action.parent_note = request.form.get("parent_note", "").strip()[:1200]
    action.confidence = confidence
    action.completed_at = utcnow()
    if action.lesson:
        progress = SkillProgress.query.filter_by(
            user_id=current_user.id,
            child_id=action.plan.child_id,
            module_id=action.lesson.module_id,
        ).first()
        if not progress:
            progress = SkillProgress(
                user_id=current_user.id,
                child_id=action.plan.child_id,
                module_id=action.lesson.module_id,
                percent=0,
            )
            db.session.add(progress)
        progress.percent = min(100, (progress.percent or 0) + 20)
        progress.updated_at = utcnow()
    db.session.flush()
    if not action.plan.current_action:
        action.plan.status = "awaiting_review"
    db.session.commit()
    flash("قدم امروز ثبت شد؛ حالا فقط قدم بعدی را ببینید.", "success")
    return redirect(url_for("parent.plan_detail", plan_id=action.plan.id))


@bp.post("/journey/<int:plan_id>/review")
@login_required
def review_plan(plan_id):
    plan = db.session.get(WeeklyPlan, plan_id)
    if not plan or plan.user_id != current_user.id:
        abort(404)
    owned_child(plan.child_id)
    if plan.current_action:
        flash("پیش از مرور نهایی، قدم‌های باقی‌مانده را کامل کنید.", "warning")
        return redirect(url_for("parent.plan_detail", plan_id=plan.id))
    rating = request.form.get("rating", type=int)
    confidence = request.form.get("confidence", type=int)
    relationship_change = request.form.get("relationship_change", "")
    if rating not in range(1, 6) or confidence not in range(1, 6):
        flash("امتیاز هفته و اطمینان را از ۱ تا ۵ مشخص کنید.", "danger")
    elif relationship_change not in {"improved", "same", "worsened"}:
        flash("تغییر رابطه را مشخص کنید.", "danger")
    else:
        review = plan.review or PlanReview(weekly_plan_id=plan.id)
        review.rating = rating
        review.confidence = confidence
        review.relationship_change = relationship_change
        review.what_worked = request.form.get("what_worked", "").strip()[:1200]
        review.next_focus = request.form.get("next_focus", "").strip()[:500]
        if not plan.review:
            db.session.add(review)
        plan.status = "completed"
        plan.completed_at = utcnow()
        db.session.commit()
        flash("هفته بسته شد؛ اکنون می‌توانید هدف بعدی را با تجربه واقعی انتخاب کنید.", "success")
        return redirect(url_for("parent.journey"))
    return redirect(url_for("parent.plan_detail", plan_id=plan.id))


@bp.get("/recommendations")
@login_required
def recommendations():
    child = owned_child()
    if not child:
        return redirect(url_for("parent.children"))
    items = RecommendationRun.query.filter_by(
        user_id=current_user.id, child_id=child.id
    ).order_by(RecommendationRun.created_at.desc()).all()
    return render_template("parent/recommendations.html", child=child, recommendations=items)


@bp.route("/recommendations/<int:recommendation_id>", methods=["GET", "POST"])
@login_required
def recommendation_detail(recommendation_id):
    recommendation = db.session.get(RecommendationRun, recommendation_id)
    if not recommendation or recommendation.user_id != current_user.id:
        abort(404)
    child = owned_child(recommendation.child_id)
    if request.method == "POST":
        outcome_value = request.form.get("outcome", "")
        child_response = request.form.get("child_response", "")
        helpfulness = request.form.get("helpfulness", type=int)
        if outcome_value not in {"helped", "neutral", "worsened", "not_done"}:
            flash("نتیجه اقدام را انتخاب کنید.", "danger")
        elif child_response not in {
            "calmer",
            "cooperative",
            "no_change",
            "withdrawn",
            "escalated",
            "not_recorded",
        }:
            flash("واکنش فرزند معتبر نیست.", "danger")
        elif helpfulness not in range(1, 6):
            flash("میزان کمک‌کنندگی را از ۱ تا ۵ مشخص کنید.", "danger")
        else:
            outcome = recommendation.outcome or HomeActionOutcome(
                recommendation_id=recommendation.id
            )
            outcome.outcome = outcome_value
            outcome.child_response = child_response
            outcome.helpfulness = helpfulness
            outcome.parent_note = request.form.get("parent_note", "").strip()[:1200]
            if not recommendation.outcome:
                db.session.add(outcome)
            recommendation.status = "completed" if outcome_value != "not_done" else "skipped"
            recommendation.completed_at = utcnow()
            db.session.commit()
            flash("نتیجه اقدام ثبت شد و در پیشنهاد بعدی اثر می‌گذارد.", "success")
            return redirect(
                url_for("parent.recommendation_detail", recommendation_id=recommendation.id)
            )
    outcome_guidance = None
    if recommendation.outcome:
        outcome_guidance = {
            "helped": "این مسیر کمک‌کننده بوده است؛ در نوبت بعد همان اصل را با ثبات ادامه دهید.",
            "neutral": "اثر روشن نبوده است؛ اقدام بعدی را کوچک‌تر و زمان اجرای آن را مناسب‌تر کنید.",
            "worsened": "این مداخله را عیناً تکرار نکنید؛ پیشنهاد بعدی با شدت کمتر و تمرکز بر کاهش تنش ساخته می‌شود.",
            "not_done": "مانع اجرا را بررسی و یک اقدام کوچک‌تر انتخاب کنید.",
        }.get(recommendation.outcome.outcome)
    return render_template(
        "parent/recommendation_detail.html",
        child=child,
        recommendation=recommendation,
        outcome_guidance=outcome_guidance,
    )

