import csv
import io
import json
import os
import re
from datetime import date, datetime

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from .extensions import db
from .models import (
    AssessmentInstrument,
    AssessmentQuestion,
    AssistantConversation,
    AssistantFeedback,
    AssistantMessage,
    Child,
    ChildProfileSnapshot,
    ContractBeneficiary,
    ConsentRecord,
    Course,
    CourseAssessmentBinding,
    CourseChapter,
    CourseEnrollment,
    CourseInvoice,
    CourseOrder,
    CourseOrderItem,
    CourseSkillMembership,
    CourseTopicMembership,
    CourseUnit,
    CourseUnitProgress,
    CrisisLevelDefinition,
    DataDeletionRequest,
    DailyAction,
    DecisionNode,
    DynamicForm,
    FormAssignment,
    FormMediaAsset,
    FormResponse,
    FormVersion,
    GrowthReportSchedule,
    GuardianRelationship,
    Organization,
    OrganizationAuditLog,
    OrganizationContract,
    PaymentAllocation,
    PaymentTransaction,
    ParentingAssessment,
    ParentingStyleDefinition,
    ParentingStyleAssessment,
    PersonalizationRule,
    ProfileDefinition,
    ProfileFormBinding,
    ProfileRecord,
    ProjectAuditLog,
    ProjectMembership,
    ScenarioAttempt,
    ScenarioLevel,
    ScenarioNarrative,
    ScenarioNarrativeAttempt,
    ScenarioReaction,
    ScenarioTopic,
    ScenarioTopicProfile,
    ScenarioTopicSkillMembership,
    SafetyProtocol,
    ScientificReview,
    SkillModule,
    SkillProgress,
    SmsOutbox,
    SponsoredProject,
    User,
    HomeActionOutcome,
    MicroLesson,
    OperationalEvent,
    PlanReview,
    RecommendationRun,
    SkillDomain,
    WeeklyPlan,
    utcnow,
)
from .effectiveness import activation_funnel, outcome_summary, project_anonymous_report
from .governance import (
    RESOURCE_MODELS,
    approved_for_current_snapshot,
    resource_snapshot,
    resource_title,
    resource_version,
)
from .security import admin_required, scientific_staff_required
from .profiles import (
    PROFILE_TYPES,
    active_profile_definition,
    profile_record,
    profile_sections,
    save_profile_values,
    sync_role_form_to_profile,
)
from .form_engine import (
    AI_CONTRACT,
    FORM_STATUSES,
    FORM_TYPES,
    UPLOAD_TYPES,
    allowed_upload,
    malware_scan_sample,
    field_catalog_payload,
    form_to_ai_contract,
    normalize_schema,
    normalize_scoring,
    normalize_settings,
    score_answers,
    storage_filename,
    validate_ai_contract,
)
from .course_engine import (
    COURSE_LEVELS,
    COURSE_STATUSES,
    STYLE_TAGS,
    UNIT_TYPES,
    parse_course_structure,
    structure_payload,
    sync_course_structure,
)
from .commerce import (
    PAYMENT_MODES,
    SMS_EVENTS,
    CommerceError,
    GatewayError,
    SmsError,
    process_sms,
    queue_sms,
    reconciliation_issues,
    refund_order,
    save_setting,
    secret_setting,
    setting,
    setting_hint,
    test_zarinpal_connection,
)
from .scenario_engine import (
    narrative_publish_errors,
    narrative_to_contract,
    validate_contract as validate_scenario_contract,
)
from .pilot import pilot_summary, seed_stage15_pilot
from .growth_engine import (
    build_growth_timeline,
    contract_aggregate_report,
    growth_dashboard_state,
)


bp = Blueprint("admin", __name__, url_prefix="/admin")
PROJECT_STATUSES = {"draft", "active", "paused", "closed"}
ORGANIZATION_STATUSES = {"active", "inactive", "archived"}
CONTRACT_STATUSES = {"draft", "active", "ended", "archived"}
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


def audit_organization(organization, action, details=None, contract=None):
    db.session.add(
        OrganizationAuditLog(
            organization_id=organization.id,
            organization_name=organization.name,
            contract_id=contract.id if contract else None,
            actor_id=current_user.id,
            action=action,
            details_json=json.dumps(details or {}, ensure_ascii=False),
        )
    )


def organization_form_values():
    status = request.form.get("status", "active")
    return {
        "name": request.form.get("name", "").strip()[:160],
        "legal_name": request.form.get("legal_name", "").strip()[:200],
        "registration_no": normalize_digits(
            request.form.get("registration_no", "").strip()
        )[:80],
        "contact_name": request.form.get("contact_name", "").strip()[:120],
        "contact_mobile": normalize_digits(
            request.form.get("contact_mobile", "").strip()
        )[:20],
        "contact_email": request.form.get("contact_email", "").strip()[:160],
        "address": request.form.get("address", "").strip()[:700],
        "website": request.form.get("website", "").strip()[:300],
        "logo_url": request.form.get("logo_url", "").strip()[:500],
        "status": status if status in ORGANIZATION_STATUSES else "active",
    }


def contract_form_values(contract=None):
    contract_no = normalize_digits(request.form.get("contract_no", "").strip()).upper()
    status = request.form.get("status", "draft")
    values = {
        "title": request.form.get("title", "").strip()[:200],
        "contract_no": contract_no[:80],
        "body_text": request.form.get("body_text", "").strip(),
        "terms_text": request.form.get("terms_text", "").strip(),
        "commitments_text": request.form.get("commitments_text", "").strip(),
        "starts_on": parse_iso_date(request.form.get("starts_on")),
        "ends_on": parse_iso_date(request.form.get("ends_on")),
        "total_amount_toman": parse_int(request.form.get("total_amount_toman")),
        "amount_paid_toman": parse_int(request.form.get("amount_paid_toman")),
        "status": status if status in CONTRACT_STATUSES else "draft",
        "services_json": json.dumps(
            [
                item.strip()
                for item in request.form.get("services", "").splitlines()
                if item.strip()
            ],
            ensure_ascii=False,
        ),
        "document_name": request.form.get("document_name", "").strip()[:240],
        "document_url": request.form.get("document_url", "").strip()[:700],
    }
    errors = []
    duplicate = (
        OrganizationContract.query.filter_by(contract_no=contract_no).first()
        if contract_no
        else None
    )
    if len(values["title"]) < 3:
        errors.append("عنوان قرارداد باید حداقل سه نویسه باشد.")
    if len(contract_no) < 3:
        errors.append("شماره قرارداد را وارد کنید.")
    elif duplicate and (not contract or duplicate.id != contract.id):
        errors.append("شماره قرارداد قبلاً ثبت شده است.")
    if values["total_amount_toman"] < 0 or values["amount_paid_toman"] < 0:
        errors.append("مبالغ قرارداد نمی‌توانند منفی باشند.")
    if values["amount_paid_toman"] > values["total_amount_toman"] and values["total_amount_toman"]:
        errors.append("مبلغ پرداخت‌شده نمی‌تواند از مبلغ کل قرارداد بیشتر باشد.")
    if values["starts_on"] and values["ends_on"] and values["starts_on"] > values["ends_on"]:
        errors.append("تاریخ پایان قرارداد باید بعد از تاریخ شروع باشد.")
    return values, errors


def delete_child_records(child):
    """Delete the child and all directly linked educational records in a safe order."""
    child_id = child.id
    for item in AssistantConversation.query.filter_by(child_id=child_id).all():
        db.session.delete(item)
    for item in WeeklyPlan.query.filter_by(child_id=child_id).all():
        db.session.delete(item)
    for item in RecommendationRun.query.filter_by(child_id=child_id).all():
        db.session.delete(item)
    for model in (
        ParentingAssessment,
        SkillProgress,
        ScenarioAttempt,
        ScenarioNarrativeAttempt,
        FormResponse,
        ParentingStyleAssessment,
        ChildProfileSnapshot,
    ):
        model.query.filter_by(child_id=child_id).delete(synchronize_session=False)
    GuardianRelationship.query.filter_by(child_id=child_id).delete(synchronize_session=False)
    child_definition_ids = [
        item.id for item in ProfileDefinition.query.filter_by(profile_type="child").all()
    ]
    if child_definition_ids:
        ProfileRecord.query.filter(
            ProfileRecord.definition_id.in_(child_definition_ids),
            ProfileRecord.subject_id == child_id,
        ).delete(synchronize_session=False)
    db.session.delete(child)


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


@bp.route("/pilot", methods=["GET", "POST"])
@login_required
@admin_required
def pilot_center():
    if request.method == "POST":
        summary = seed_stage15_pilot(current_user.id)
        flash(
            f"داده پایلوت همگام شد: {summary['total_children']} فرزند، "
            f"{summary['shared_children']} مشترک و {summary['independent_children']} غیرسازمانی.",
            "success",
        )
        return redirect(url_for("admin.pilot_center"))
    summary = pilot_summary()
    contracts = OrganizationContract.query.filter(
        OrganizationContract.contract_no.in_(["PILOT-1405-A", "PILOT-1405-B"])
    ).order_by(OrganizationContract.contract_no).all()
    profile_forms = DynamicForm.query.filter(
        DynamicForm.slug.in_([
            "stage15-parent-profile", "stage15-child-profile", "stage15-organization-profile"
        ])
    ).order_by(DynamicForm.slug).all()
    return render_template(
        "admin/pilot.html", summary=summary, contracts=contracts, profile_forms=profile_forms
    )


@bp.get("/operations")
@login_required
@admin_required
def operations():
    funnel = activation_funnel()
    outcomes = outcome_summary()
    deletion_requests = DataDeletionRequest.query.order_by(
        DataDeletionRequest.requested_at.desc()
    ).limit(20).all()
    recent_events = OperationalEvent.query.order_by(
        OperationalEvent.created_at.desc()
    ).limit(20).all()
    approved_reviews = ScientificReview.query.filter_by(status="approved").count()
    pending_reviews = ScientificReview.query.filter_by(status="pending").count()
    operations_state = {
        "payment_provider": f"zarinpal/{setting('zarinpal.mode', current_app.config.get('PAYMENT_MODE', 'disabled'))}",
        "payment_ready": bool(secret_setting("zarinpal.merchant_id") or current_app.config["PAYMENT_MERCHANT_ID"]),
        "scientific_gate": current_app.config["REQUIRE_SCIENTIFIC_APPROVAL"],
        "policy_version": current_app.config["PRIVACY_POLICY_VERSION"],
        "consents": ConsentRecord.query.count(),
        "pending_deletions": DataDeletionRequest.query.filter_by(status="pending").count(),
        "pending_reviews": pending_reviews,
        "approved_reviews": approved_reviews,
    }
    return render_template(
        "admin/operations.html",
        funnel=funnel,
        outcomes=outcomes,
        deletion_requests=deletion_requests,
        recent_events=recent_events,
        operations_state=operations_state,
    )


@bp.post("/privacy/deletion/<int:request_id>")
@login_required
@admin_required
def process_deletion_request(request_id):
    deletion = db.get_or_404(DataDeletionRequest, request_id)
    if deletion.status != "pending":
        flash("این درخواست قبلاً بررسی شده است.", "warning")
        return redirect(url_for("admin.operations"))
    action = request.form.get("action")
    note = request.form.get("note", "").strip()[:700]
    if action == "complete":
        child = db.session.get(Child, deletion.child_id)
        if not child or child.user_id != deletion.user_id:
            deletion.status = "rejected"
            deletion.processing_note = "پرونده در زمان بررسی وجود نداشت یا مالکیت تطبیق نداشت."
        else:
            delete_child_records(child)
            deletion.status = "completed"
            deletion.processing_note = note or "پرونده و داده‌های آموزشی متصل حذف شد."
        event_status = "success"
    elif action == "reject":
        deletion.status = "rejected"
        deletion.processing_note = note or "درخواست پس از بررسی رد شد."
        event_status = "warning"
    else:
        abort(400)
    deletion.processed_by = current_user.id
    deletion.processed_at = utcnow()
    db.session.add(
        OperationalEvent(
            event_type="child_data_deletion",
            status=event_status,
            details_json=json.dumps(
                {"request_id": deletion.id, "result": deletion.status}, ensure_ascii=False
            ),
        )
    )
    db.session.commit()
    flash("نتیجه درخواست حذف ثبت شد.", "success")
    return redirect(url_for("admin.operations"))


@bp.route("/scientific-review", methods=["GET", "POST"])
@login_required
@scientific_staff_required
def scientific_review():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "request":
            if not current_user.is_admin:
                abort(403)
            resource_type = request.form.get("resource_type", "")
            model = RESOURCE_MODELS.get(resource_type)
            resource = db.session.get(model, request.form.get("resource_id", type=int)) if model else None
            if not resource:
                abort(404)
            fingerprint = ScientificReview.fingerprint(
                resource_snapshot(resource_type, resource)
            )
            review = ScientificReview.query.filter_by(
                resource_type=resource_type,
                resource_id=resource.id,
                resource_version=resource_version(resource_type, resource),
                snapshot_hash=fingerprint,
            ).first()
            if review and review.status == "approved":
                flash("همین نسخه و محتوا قبلاً تأیید شده است.", "info")
            else:
                if not review:
                    review = ScientificReview(
                        resource_type=resource_type,
                        resource_id=resource.id,
                        resource_title=resource_title(resource_type, resource),
                        resource_version=resource_version(resource_type, resource),
                        snapshot_hash=fingerprint,
                        requested_by=current_user.id,
                    )
                    db.session.add(review)
                else:
                    review.status = "pending"
                    review.reviewer_note = ""
                    review.reviewed_by = None
                    review.reviewed_at = None
                db.session.commit()
                flash("نسخه فعلی برای ناظر علمی ارسال شد.", "success")
        elif action in {"approve", "reject"}:
            if not current_user.is_reviewer:
                abort(403)
            review = db.get_or_404(ScientificReview, request.form.get("review_id", type=int))
            if review.status != "pending":
                flash("این مورد قبلاً بررسی شده است.", "warning")
            else:
                review.status = "approved" if action == "approve" else "rejected"
                review.reviewed_by = current_user.id
                review.reviewed_at = utcnow()
                review.reviewer_note = request.form.get("reviewer_note", "").strip()[:1000]
                db.session.commit()
                flash("رأی ناظر علمی ثبت شد.", "success")
        return redirect(url_for("admin.scientific_review"))

    reviews = ScientificReview.query.order_by(ScientificReview.requested_at.desc()).all()
    resources = {
        "instrument": AssessmentInstrument.query.all(),
        "lesson": MicroLesson.query.order_by(MicroLesson.id.desc()).all(),
        "rule": PersonalizationRule.query.order_by(PersonalizationRule.id.desc()).all(),
        "protocol": SafetyProtocol.query.order_by(SafetyProtocol.id.desc()).all(),
        "form": DynamicForm.query.filter_by(status="review").order_by(DynamicForm.id.desc()).all(),
        "scenario_narrative": ScenarioNarrative.query.filter_by(status="review").order_by(ScenarioNarrative.id.desc()).all(),
    }
    return render_template("admin/scientific_review.html", reviews=reviews, resources=resources)


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
    abort(404)
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
            if (
                current_app.config["REQUIRE_SCIENTIFIC_APPROVAL"]
                and not approved_for_current_snapshot("instrument", instrument)
            ):
                errors.append("انتشار production فقط پس از تأیید مستقل همین نسخه توسط ناظر علمی ممکن است.")
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                instrument.status = "published"
                approval = approved_for_current_snapshot("instrument", instrument)
                instrument.approved_by = approval.reviewed_by if approval else current_user.id
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
    abort(404)
    topics = (
        ScenarioTopic.query.outerjoin(ScenarioTopicProfile)
        .order_by(ScenarioTopicProfile.sort_order, ScenarioTopic.id)
        .all()
    )
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


@bp.route("/skills", methods=["GET", "POST"])
@login_required
@admin_required
def skill_catalog():
    if request.method == "POST":
        action = request.form.get("action", "save")
        skill_id = request.form.get("skill_id", type=int)
        skill = db.session.get(SkillModule, skill_id) if skill_id else None
        if action == "toggle" and skill:
            skill.is_published = not skill.is_published
            db.session.commit()
            flash("وضعیت انتشار مهارت تغییر کرد.", "info")
            return redirect(url_for("admin.skill_catalog"))
        if action != "save":
            abort(400)
        title = request.form.get("title", "").strip()[:120]
        slug = make_slug(request.form.get("slug", ""))[:80]
        code = request.form.get("code", "").strip().upper()[:30]
        level = request.form.get("level", "foundation")
        if level not in COURSE_LEVELS:
            level = "foundation"
        duplicate = SkillModule.query.filter(
            SkillModule.slug == slug,
            SkillModule.id != (skill.id if skill else -1),
        ).first()
        errors = []
        if len(title) < 3:
            errors.append("عنوان مهارت باید حداقل سه نویسه باشد.")
        if duplicate:
            errors.append("نامک مهارت تکراری است.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not skill:
                skill = SkillModule(slug=slug, title=title, description="")
                db.session.add(skill)
            skill.title = title
            skill.slug = slug
            skill.code = code
            skill.description = request.form.get("description", "").strip()[:500]
            skill.icon = request.form.get("icon", "fa-seedling").strip()[:60] or "fa-seedling"
            skill.duration = max(1, min(240, request.form.get("duration", 10, type=int)))
            skill.level = level
            skill.sort_order = max(0, request.form.get("sort_order", 0, type=int))
            skill.is_published = request.form.get("is_published") == "1"
            skill.style_tags_json = json.dumps(
                [item for item in request.form.getlist("style_tags") if item in STYLE_TAGS],
                ensure_ascii=False,
            )
            skill.scenario_ids_json = json.dumps(
                [item for item in request.form.getlist("scenario_ids", type=int) if db.session.get(ScenarioTopic, item)],
                ensure_ascii=False,
            )
            skill.prerequisite_ids_json = json.dumps(
                [item for item in request.form.getlist("prerequisite_ids", type=int) if db.session.get(SkillModule, item) and item != skill.id],
                ensure_ascii=False,
            )
            db.session.commit()
            flash("مهارت و ارتباط‌های آموزشی آن ذخیره شد.", "success")
            return redirect(url_for("admin.skill_catalog"))
    edit_id = request.args.get("edit", type=int)
    return render_template(
        "admin/skills.html",
        skills=SkillModule.query.order_by(SkillModule.sort_order, SkillModule.id).all(),
        topics=ScenarioTopic.query.order_by(ScenarioTopic.title).all(),
        selected=db.session.get(SkillModule, edit_id) if edit_id else None,
        levels=COURSE_LEVELS,
        style_tags=STYLE_TAGS,
    )


def sync_course_links(course, skill_ids, topic_ids):
    CourseSkillMembership.query.filter_by(course_id=course.id).delete(
        synchronize_session=False
    )
    CourseTopicMembership.query.filter_by(course_id=course.id).delete(
        synchronize_session=False
    )
    for index, skill_id in enumerate(skill_ids):
        if db.session.get(SkillModule, skill_id):
            db.session.add(
                CourseSkillMembership(
                    course_id=course.id,
                    skill_id=skill_id,
                    is_primary=index == 0,
                    sort_order=index,
                )
            )
    for topic_id in topic_ids:
        if db.session.get(ScenarioTopic, topic_id):
            db.session.add(CourseTopicMembership(course_id=course.id, topic_id=topic_id))


def sync_course_assessments(course, pre_form_id=None, post_form_id=None):
    """Replace course-level pre/post bindings without changing historic responses."""
    CourseAssessmentBinding.query.filter_by(course_id=course.id).delete(
        synchronize_session=False
    )
    primary_skill_id = course.skill_links[0].skill_id if course.skill_links else None
    for assessment_type, form_id in (("pre", pre_form_id), ("post", post_form_id)):
        form = db.session.get(DynamicForm, form_id) if form_id else None
        if form and form.status == "published":
            db.session.add(
                CourseAssessmentBinding(
                    course_id=course.id,
                    form_id=form.id,
                    assessment_type=assessment_type,
                    skill_id=primary_skill_id,
                )
            )
            assignment = FormAssignment.query.filter_by(
                target_type="course", target_ref=str(course.id), form_id=form.id
            ).first()
            if not assignment:
                assignment = FormAssignment(
                    form_id=form.id,
                    target_type="course",
                    target_ref=str(course.id),
                    title=f"سنجش {'قبل' if assessment_type == 'pre' else 'بعد'} دوره: {course.title}",
                    created_by=current_user.id,
                )
                db.session.add(assignment)
            else:
                assignment.status = "active"


def sync_course_quiz_assignments(course):
    active_form_ids = {
        unit.form_id
        for unit in CourseUnit.query.join(CourseChapter).filter(
            CourseChapter.course_id == course.id,
            CourseChapter.status == "active",
            CourseUnit.status == "active",
            CourseUnit.unit_type == "quiz",
            CourseUnit.form_id.isnot(None),
        ).all()
    }
    active_form_ids.update(
        item.form_id for item in CourseAssessmentBinding.query.filter_by(course_id=course.id).all()
    )
    assignments = FormAssignment.query.filter_by(
        target_type="course", target_ref=str(course.id)
    ).all()
    existing = {item.form_id: item for item in assignments}
    for form_id in active_form_ids:
        assignment = existing.get(form_id)
        form = db.session.get(DynamicForm, form_id)
        if not assignment and form:
            assignment = FormAssignment(
                form_id=form_id,
                target_type="course",
                target_ref=str(course.id),
                title=f"آزمون دوره: {form.title}",
                created_by=current_user.id,
            )
            db.session.add(assignment)
        elif assignment:
            assignment.status = "active"
    for form_id, assignment in existing.items():
        if form_id not in active_form_ids:
            assignment.status = "archived"


@bp.route("/courses", methods=["GET", "POST"])
@login_required
@admin_required
def courses():
    if request.method == "POST":
        course = db.get_or_404(Course, request.form.get("course_id", type=int))
        action = request.form.get("action")
        if action == "archive":
            course.status = "archived"
            course.archived_at = utcnow()
            db.session.commit()
            flash("دوره بایگانی شد؛ ثبت‌نام‌ها و پیشرفت‌های قبلی محفوظ ماند.", "info")
        elif action == "duplicate":
            base_slug = f"{course.slug}-copy"[:120]
            clone_slug = base_slug
            counter = 2
            while Course.query.filter_by(slug=clone_slug).first():
                suffix = f"-{counter}"
                clone_slug = f"{base_slug[:120-len(suffix)]}{suffix}"
                counter += 1
            clone = Course(
                slug=clone_slug,
                title=f"کپی {course.title}",
                subtitle=course.subtitle,
                description=course.description,
                instructor_name=course.instructor_name,
                cover_url=course.cover_url,
                intro_video_url=course.intro_video_url,
                level=course.level,
                duration_minutes=course.duration_minutes,
                price_toman=course.price_toman,
                style_tags_json=course.style_tags_json,
                status="draft",
                version=1,
                created_by=current_user.id,
            )
            db.session.add(clone)
            db.session.flush()
            sync_course_links(clone, [item.id for item in course.skills], [item.id for item in course.topics])
            copied_structure = structure_payload(course)
            for chapter in copied_structure:
                chapter["id"] = None
                for unit in chapter["units"]:
                    unit["id"] = None
            sync_course_structure(clone, copied_structure)
            db.session.commit()
            flash("یک کپی Draft از دوره ساخته شد.", "success")
            return redirect(url_for("admin.course_editor", course_id=clone.id))
        else:
            abort(400)
        return redirect(url_for("admin.courses"))
    query = Course.query
    status = request.args.get("status", "")
    search = request.args.get("q", "").strip()
    if status in COURSE_STATUSES:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(or_(Course.title.contains(search), Course.slug.contains(search)))
    rows = query.order_by(Course.updated_at.desc()).all()
    stats = {
        "all": Course.query.count(),
        "published": Course.query.filter_by(status="published").count(),
        "free": Course.query.filter(Course.price_toman <= 0, Course.status == "published").count(),
        "enrollments": CourseEnrollment.query.count(),
    }
    return render_template("admin/courses.html", courses=rows, stats=stats, selected_status=status, search=search)


@bp.route("/courses/new", methods=["GET", "POST"])
@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def course_editor(course_id=None):
    course = db.get_or_404(Course, course_id) if course_id else None
    if request.method == "POST":
        action = request.form.get("action", "save_draft")
        if action not in {"save_draft", "publish"}:
            abort(400)
        title = request.form.get("title", "").strip()[:180]
        slug = make_slug(request.form.get("slug", ""))[:120]
        structure, errors = parse_course_structure(request.form.get("structure_json", "[]"))
        duplicate = Course.query.filter(
            Course.slug == slug, Course.id != (course.id if course else -1)
        ).first()
        if len(title) < 3:
            errors.append("عنوان دوره باید حداقل سه نویسه باشد.")
        if duplicate:
            errors.append("نامک دوره تکراری است.")
        price = max(0, request.form.get("price_toman", 0, type=int))
        level = request.form.get("level", "foundation")
        if level not in COURSE_LEVELS:
            errors.append("سطح دوره معتبر نیست.")
            level = "foundation"
        if action == "publish":
            if not structure or not any(item["units"] for item in structure):
                errors.append("برای انتشار، دوره باید دست‌کم یک فصل و یک درس داشته باشد.")
            for chapter in structure:
                for unit in chapter["units"]:
                    if unit["type"] == "quiz":
                        form = db.session.get(DynamicForm, unit["form_id"])
                        if not form or form.status != "published":
                            errors.append(f"آزمون درس «{unit['title']}» باید یک فرم منتشرشده باشد.")
        if errors:
            for error in dict.fromkeys(errors):
                flash(error, "danger")
        else:
            if not course:
                course = Course(slug=slug, title=title, created_by=current_user.id)
                db.session.add(course)
                db.session.flush()
            elif course.status == "published":
                course.version += 1
                if action == "save_draft":
                    course.published_at = None
            course.slug = slug
            course.title = title
            course.subtitle = request.form.get("subtitle", "").strip()[:240]
            course.description = request.form.get("description", "").strip()[:10000]
            course.instructor_name = request.form.get("instructor_name", "").strip()[:140] or "تیم علمی والدیار"
            course.cover_url = request.form.get("cover_url", "").strip()[:700]
            course.intro_video_url = request.form.get("intro_video_url", "").strip()[:700]
            course.level = level
            course.duration_minutes = max(1, min(100000, request.form.get("duration_minutes", 60, type=int)))
            course.price_toman = price
            course.style_tags_json = json.dumps(
                [item for item in request.form.getlist("style_tags") if item in STYLE_TAGS], ensure_ascii=False
            )
            course.is_featured = request.form.get("is_featured") == "1"
            course.sort_order = max(0, request.form.get("sort_order", 0, type=int))
            course.status = "published" if action == "publish" else "draft"
            course.published_at = utcnow() if action == "publish" else None
            course.archived_at = None
            sync_course_links(
                course,
                request.form.getlist("skill_ids", type=int),
                request.form.getlist("topic_ids", type=int),
            )
            db.session.flush()
            sync_course_assessments(
                course,
                request.form.get("pre_form_id", type=int),
                request.form.get("post_form_id", type=int),
            )
            sync_course_structure(course, structure)
            db.session.flush()
            sync_course_quiz_assignments(course)
            db.session.commit()
            flash(
                f"دوره نسخه {course.version} {'منتشر' if action == 'publish' else 'ذخیره'} شد.",
                "success",
            )
            return redirect(url_for("admin.course_editor", course_id=course.id))
    return render_template(
        "admin/course_builder.html",
        selected=course,
        structure=structure_payload(course) if course else [],
        skills=SkillModule.query.order_by(SkillModule.sort_order).all(),
        topics=ScenarioTopic.query.order_by(ScenarioTopic.title).all(),
        forms=DynamicForm.query.filter(
            DynamicForm.status == "published",
            DynamicForm.form_type.in_(["assessment", "quiz"]),
        ).order_by(DynamicForm.title).all(),
        levels=COURSE_LEVELS,
        style_tags=STYLE_TAGS,
        unit_types=UNIT_TYPES,
        assessment_bindings={item.assessment_type: item for item in course.assessment_bindings}
        if course else {},
    )


@bp.get("/courses/<int:course_id>/students")
@login_required
@admin_required
def course_students(course_id):
    course = db.get_or_404(Course, course_id)
    enrollments = CourseEnrollment.query.filter_by(course_id=course.id).order_by(
        CourseEnrollment.enrolled_at.desc()
    ).all()
    return render_template(
        "admin/course_students.html", course=course, enrollments=enrollments
    )


@bp.route("/commerce", methods=["GET", "POST"])
@login_required
@admin_required
def commerce_dashboard():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "refund":
            order = db.get_or_404(CourseOrder, request.form.get("order_id", type=int))
            try:
                refund_order(order, current_user.id, request.form.get("note", "بازپرداخت ثبت‌شده توسط مدیر"))
                db.session.commit()
                flash("بازپرداخت در دفتر مالی ثبت و دسترسی دوره به‌روزرسانی شد.", "success")
            except CommerceError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
        elif action == "retry_sms":
            job = db.get_or_404(SmsOutbox, request.form.get("sms_id", type=int))
            try:
                job.status = "queued"
                process_sms(job)
                db.session.commit()
                flash("پیامک با موفقیت ارسال شد.", "success")
            except SmsError as exc:
                db.session.commit()
                flash(str(exc), "danger")
        elif action == "course_reminder":
            enrollment = db.get_or_404(CourseEnrollment, request.form.get("enrollment_id", type=int))
            job = queue_sms(
                "course_reminder",
                enrollment.user.mobile,
                {"name": enrollment.user.full_name, "course": enrollment.course.title, "progress": enrollment.progress_percent},
                f"course-reminder:{enrollment.id}:{datetime.utcnow():%Y%m%d}",
                message=f"یادآوری والدیار: ادامه دوره «{enrollment.course.title}» منتظر شماست.",
            )
            db.session.commit()
            flash(f"یادآوری در صف پیامک شماره {job.id} قرار گرفت.", "info")
        else:
            abort(400)
        return redirect(url_for("admin.commerce_dashboard"))

    query = CourseOrder.query
    selected_status = request.args.get("status", "")
    search = request.args.get("q", "").strip()
    if selected_status in {"draft", "awaiting_payment", "paid", "failed", "cancelled", "refunded"}:
        query = query.filter_by(status=selected_status)
    if search:
        query = query.join(User, CourseOrder.user_id == User.id).filter(
            or_(CourseOrder.order_no.contains(search), User.full_name.contains(search), User.mobile.contains(search))
        )
    orders = query.order_by(CourseOrder.created_at.desc()).all()
    all_orders = CourseOrder.query.all()
    stats = {
        "orders": len(all_orders),
        "paid": sum(item.status == "paid" for item in all_orders),
        "revenue": sum(item.payable_amount_toman for item in all_orders if item.status == "paid"),
        "organization": sum(item.organization_amount_toman for item in all_orders if item.status in {"paid", "refunded"}),
        "failed": sum(item.status == "failed" for item in all_orders),
    }
    sms_jobs = SmsOutbox.query.order_by(SmsOutbox.created_at.desc()).limit(30).all()
    return render_template(
        "admin/commerce.html",
        orders=orders,
        stats=stats,
        sms_jobs=sms_jobs,
        issues=reconciliation_issues(),
        selected_status=selected_status,
        search=search,
    )


@bp.get("/commerce/export.csv")
@login_required
@admin_required
def commerce_export():
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "order_no", "created_at", "parent", "mobile", "child", "course", "status",
        "gross_toman", "organization_toman", "parent_toman", "invoice_no", "authority", "ref_id",
    ])
    for order in CourseOrder.query.order_by(CourseOrder.created_at.desc()).all():
        transaction = next((item for item in order.transactions if item.status in {"verified", "refunded"}), None)
        writer.writerow([
            order.order_no,
            order.created_at.isoformat(),
            order.user.full_name,
            order.user.mobile,
            order.child.name if order.child else "",
            order.items[0].title_snapshot if order.items else "",
            order.status,
            order.gross_amount_toman,
            order.organization_amount_toman,
            order.payable_amount_toman,
            order.invoice.invoice_no if order.invoice else "",
            transaction.authority if transaction else "",
            transaction.reference_id if transaction else "",
        ])
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=valedgari-sales.csv"},
    )


@bp.route("/integrations", methods=["GET", "POST"])
@login_required
@admin_required
def integrations():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_zarinpal":
            mode = request.form.get("mode", "disabled")
            callback_url = request.form.get("callback_url", "").strip()[:700]
            if mode not in PAYMENT_MODES:
                mode = "disabled"
            if callback_url and not (
                callback_url.startswith("https://")
                or current_app.testing and callback_url.startswith("http://")
            ):
                flash("Callback در محیط واقعی باید با HTTPS آغاز شود.", "danger")
            else:
                save_setting("zarinpal.mode", mode, current_user.id)
                save_setting("zarinpal.callback_url", callback_url, current_user.id)
                merchant_id = request.form.get("merchant_id", "").strip()
                if merchant_id:
                    save_setting("zarinpal.merchant_id", merchant_id, current_user.id, secret=True)
                db.session.commit()
                flash("تنظیمات زرین‌پال ذخیره شد؛ مقدار محرمانه دوباره نمایش داده نمی‌شود.", "success")
        elif action == "test_zarinpal":
            callback_url = setting("zarinpal.callback_url") or url_for("parent.zarinpal_callback", _external=True)
            try:
                result = test_zarinpal_connection(callback_url)
                flash(f"اتصال زرین‌پال تأیید شد؛ Authority آزمایشی: {result['authority']}", "success")
            except GatewayError as exc:
                flash(str(exc), "danger")
        elif action == "save_ippanel":
            save_setting("ippanel.enabled", "1" if request.form.get("enabled") == "1" else "0", current_user.id)
            save_setting("ippanel.from_number", request.form.get("from_number", "").strip()[:40], current_user.id)
            token = request.form.get("api_token", "").strip()
            if token:
                save_setting("ippanel.api_token", token, current_user.id, secret=True)
            for event in SMS_EVENTS:
                save_setting(f"ippanel.pattern.{event}", request.form.get(f"pattern_{event}", "").strip()[:100], current_user.id)
            db.session.commit()
            flash("تنظیمات و الگوهای IPPanel ذخیره شد.", "success")
        elif action == "test_ippanel":
            mobile = normalize_digits(request.form.get("test_mobile", "")).strip()
            if not re.fullmatch(r"09\d{9}", mobile):
                flash("شماره آزمایش پیامک معتبر نیست.", "danger")
            else:
                job = queue_sms(
                    "course_reminder",
                    mobile,
                    {"name": "کاربر آزمایشی", "course": "آزمون اتصال والدیار", "progress": 0},
                    f"ippanel-test:{utcnow().timestamp()}",
                    message="پیام آزمایشی اتصال IPPanel والدیار",
                )
                try:
                    process_sms(job)
                    db.session.commit()
                    flash("پیام آزمایشی ارسال و شناسه Outbox ثبت شد.", "success")
                except SmsError as exc:
                    db.session.commit()
                    flash(str(exc), "danger")
        else:
            abort(400)
        return redirect(url_for("admin.integrations"))
    return render_template(
        "admin/integrations.html",
        zarinpal={
            "mode": setting("zarinpal.mode", current_app.config.get("PAYMENT_MODE", "disabled")),
            "callback_url": setting("zarinpal.callback_url"),
            "hint": setting_hint("zarinpal.merchant_id"),
        },
        ippanel={
            "enabled": setting("ippanel.enabled", "0") == "1",
            "from_number": setting("ippanel.from_number"),
            "hint": setting_hint("ippanel.api_token"),
            "patterns": {event: setting(f"ippanel.pattern.{event}") for event in SMS_EVENTS},
        },
        sms_events=SMS_EVENTS,
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


@bp.route("/organizations", methods=["GET", "POST"])
@login_required
@admin_required
def organizations():
    if request.method == "POST":
        values = organization_form_values()
        errors = []
        if len(values["name"]) < 3:
            errors.append("نام سازمان باید حداقل سه نویسه باشد.")
        if values["registration_no"] and Organization.query.filter_by(
            registration_no=values["registration_no"]
        ).first():
            errors.append("شناسه ثبت این سازمان قبلاً استفاده شده است.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            organization = Organization(**values)
            db.session.add(organization)
            db.session.flush()
            audit_organization(organization, "organization_created")
            db.session.commit()
            flash("سازمان ساخته شد؛ اکنون می‌توانید پروفایل یا قرارداد آن را تکمیل کنید.", "success")
            return redirect(
                url_for("admin.organization_detail", organization_id=organization.id)
            )

    query = Organization.query
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    if search:
        query = query.filter(
            or_(
                Organization.name.contains(search),
                Organization.legal_name.contains(search),
                Organization.registration_no.contains(normalize_digits(search)),
                Organization.contact_name.contains(search),
            )
        )
    if status in ORGANIZATION_STATUSES:
        query = query.filter_by(status=status)
    rows = query.order_by(Organization.created_at.desc()).all()
    totals = {
        "all": Organization.query.count(),
        "active": Organization.query.filter_by(status="active").count(),
        "contracts": OrganizationContract.query.count(),
        "archived_contracts": OrganizationContract.query.filter_by(status="archived").count(),
    }
    return render_template(
        "admin/organizations.html",
        organizations=rows,
        totals=totals,
        search=search,
        selected_status=status,
    )


@bp.route("/organizations/<int:organization_id>", methods=["GET", "POST"])
@login_required
@admin_required
def organization_detail(organization_id):
    organization = db.get_or_404(Organization, organization_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_organization":
            values = organization_form_values()
            duplicate = None
            if values["registration_no"]:
                duplicate = Organization.query.filter_by(
                    registration_no=values["registration_no"]
                ).first()
            if len(values["name"]) < 3:
                flash("نام سازمان باید حداقل سه نویسه باشد.", "danger")
            elif duplicate and duplicate.id != organization.id:
                flash("شناسه ثبت این سازمان قبلاً استفاده شده است.", "danger")
            else:
                before = {"name": organization.name, "status": organization.status}
                for key, value in values.items():
                    setattr(organization, key, value)
                form_id = request.form.get("profile_form_id", type=int)
                organization.profile_form = db.session.get(DynamicForm, form_id) if form_id else None
                audit_organization(
                    organization,
                    "organization_updated",
                    {"before": before, "after": {"name": organization.name, "status": organization.status}},
                )
                db.session.commit()
                flash("پروفایل سازمان به‌روزرسانی شد.", "success")
                return redirect(url_for("admin.organization_detail", organization_id=organization.id))
        elif action == "save_dynamic_profile":
            if not organization.profile_form:
                flash("ابتدا یک فرم پروفایل برای سازمان انتخاب کنید.", "danger")
            else:
                data = {}
                for field in organization.profile_form.fields:
                    field_id = str(field.get("id", "")).strip()
                    if field_id:
                        data[field_id] = request.form.get(f"profile_{field_id}", "").strip()
                organization.profile_data_json = json.dumps(data, ensure_ascii=False)
                audit_organization(
                    organization,
                    "organization_dynamic_profile_updated",
                    {"form_id": organization.profile_form_id, "field_count": len(data)},
                )
                db.session.commit()
                flash("فیلدهای پویا در پروفایل سازمان ذخیره شد.", "success")
                return redirect(url_for("admin.organization_detail", organization_id=organization.id))
        elif action == "save_unified_profile":
            definition = active_profile_definition("organization")
            if not definition:
                flash("تعریف فعال پروفایل سازمان پیدا نشد.", "danger")
            else:
                _record, errors = save_profile_values(
                    definition, organization.id, request.form, current_user.id
                )
                if errors:
                    for error in errors:
                        flash(error, "danger")
                else:
                    audit_organization(
                        organization,
                        "organization_unified_profile_updated",
                        {"definition_version": definition.version},
                    )
                    db.session.commit()
                    flash("پروفایل یکپارچه سازمان ذخیره شد.", "success")
                    return redirect(url_for("admin.organization_detail", organization_id=organization.id))
        elif action == "create_contract":
            values, errors = contract_form_values()
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                contract = OrganizationContract(
                    organization_id=organization.id,
                    created_by=current_user.id,
                    **values,
                )
                db.session.add(contract)
                db.session.flush()
                audit_organization(
                    organization,
                    "contract_created",
                    {"contract_no": contract.contract_no, "status": contract.status},
                    contract,
                )
                db.session.commit()
                flash("قرارداد مستقل سازمان ساخته شد.", "success")
                return redirect(url_for("admin.contract_detail", contract_id=contract.id))
        elif action == "delete_organization":
            has_beneficiaries = any(contract.beneficiaries for contract in organization.contracts)
            has_consumption = any(
                project.memberships
                or any(membership.allocations for membership in project.memberships)
                or project.committed_subsidy_toman
                for project in organization.projects
            )
            if has_beneficiaries or has_consumption:
                flash("سازمان دارای عضو، ذی‌نفع یا سابقه مصرف است و قابل حذف نیست؛ آن را بایگانی کنید.", "danger")
            elif request.form.get("confirmation", "").strip() != organization.name:
                flash("برای حذف، نام دقیق سازمان را وارد کنید.", "danger")
            else:
                name = organization.name
                audit_organization(organization, "organization_deleted", {"name": name})
                db.session.flush()
                db.session.delete(organization)
                db.session.commit()
                flash(f"سازمان خالی «{name}» حذف شد.", "info")
                return redirect(url_for("admin.organizations"))

    forms = DynamicForm.query.filter(DynamicForm.status.in_(["draft", "published"])).order_by(
        DynamicForm.title
    ).all()
    contracts = sorted(organization.contracts, key=lambda item: item.created_at, reverse=True)
    children = {
        child.id: child
        for contract in contracts
        for child in contract.covered_children
    }.values()
    totals = {
        "contracts": len(contracts),
        "active_contracts": organization.active_contract_count,
        "parents": len({parent.id for contract in contracts for parent in contract.covered_parents}),
        "children": len(children),
        "committed": sum(contract.committed_amount_toman for contract in contracts),
        "paid": sum(contract.amount_paid_toman for contract in contracts),
    }
    unified_definition = active_profile_definition("organization")
    unified_record = profile_record(unified_definition, organization.id)
    return render_template(
        "admin/organization_detail.html",
        organization=organization,
        contracts=contracts,
        forms=forms,
        covered_children=sorted(children, key=lambda item: item.name),
        totals=totals,
        unified_definition=unified_definition,
        unified_record=unified_record,
        unified_profile_sections=profile_sections(unified_definition, unified_record),
    )


@bp.route("/contracts/<int:contract_id>", methods=["GET", "POST"])
@login_required
@admin_required
def contract_detail(contract_id):
    contract = db.get_or_404(OrganizationContract, contract_id)
    organization = contract.organization
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_contract":
            values, errors = contract_form_values(contract)
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                before = {"status": contract.status, "contract_no": contract.contract_no}
                for key, value in values.items():
                    setattr(contract, key, value)
                contract.version += 1
                if contract.status == "archived" and not contract.archived_at:
                    contract.archived_at = utcnow()
                elif contract.status != "archived":
                    contract.archived_at = None
                audit_organization(
                    organization,
                    "contract_updated",
                    {"before": before, "after": {"status": contract.status, "contract_no": contract.contract_no, "version": contract.version}},
                    contract,
                )
                db.session.commit()
                flash("قرارداد به‌روزرسانی شد.", "success")
                return redirect(url_for("admin.contract_detail", contract_id=contract.id))
        elif action == "archive_contract":
            contract.status = "archived"
            contract.archived_at = utcnow()
            for project in contract.support_plans:
                if project.status in {"active", "paused"}:
                    project.status = "closed"
                    audit_project(project, "project_archived_with_contract", {"contract_id": contract.id})
            audit_organization(organization, "contract_archived", {}, contract)
            db.session.commit()
            flash("قرارداد و طرح‌های فعال آن بایگانی شدند؛ سوابق قابل مشاهده باقی ماندند.", "info")
            return redirect(url_for("admin.contract_detail", contract_id=contract.id))
        elif action == "create_support_plan":
            if contract.status == "archived":
                flash("برای قرارداد بایگانی‌شده نمی‌توان طرح جدید ساخت.", "danger")
            else:
                values, errors = project_form_values()
                if errors:
                    for error in errors:
                        flash(error, "danger")
                else:
                    project = SponsoredProject(
                        organization_id=organization.id,
                        contract_id=contract.id,
                        created_by=current_user.id,
                        **values,
                    )
                    db.session.add(project)
                    db.session.flush()
                    audit_project(project, "project_created", {"contract_id": contract.id})
                    audit_organization(
                        organization,
                        "support_plan_created",
                        {"project_id": project.id, "code": project.code},
                        contract,
                    )
                    db.session.commit()
                    flash("طرح حمایت و کد استفاده زیر قرارداد ساخته شد.", "success")
                    return redirect(url_for("admin.project_detail", project_id=project.id))
        elif action == "add_beneficiary":
            mobile = normalize_digits(request.form.get("mobile", "").strip())
            user_id = request.form.get("user_id", type=int)
            parent = db.session.get(User, user_id) if user_id else None
            if parent and parent.role != "parent":
                parent = None
            if not parent and mobile:
                parent = User.query.filter_by(mobile=mobile, role="parent").first()
            child_id = request.form.get("child_id", type=int)
            child = db.session.get(Child, child_id) if child_id else None
            beneficiary_type = request.form.get("beneficiary_type", "family")
            if not parent:
                flash("والدی با این شماره موبایل پیدا نشد.", "danger")
            elif child and child.user_id != parent.id:
                flash("فرزند انتخاب‌شده متعلق به این والد نیست.", "danger")
            else:
                duplicate = ContractBeneficiary.query.filter_by(
                    contract_id=contract.id,
                    user_id=parent.id,
                    child_id=child.id if child else None,
                    status="active",
                ).first()
                if duplicate:
                    flash("این ذی‌نفع قبلاً در قرارداد فعال است.", "warning")
                else:
                    beneficiary = ContractBeneficiary(
                        contract_id=contract.id,
                        user_id=parent.id,
                        child_id=child.id if child else None,
                        beneficiary_type=beneficiary_type if beneficiary_type in {"family", "guardian", "child"} else "family",
                        starts_on=parse_iso_date(request.form.get("starts_on")),
                        ends_on=parse_iso_date(request.form.get("ends_on")),
                        note=request.form.get("note", "").strip()[:700],
                    )
                    db.session.add(beneficiary)
                    audit_organization(
                        organization,
                        "beneficiary_added",
                        {"user_id": parent.id, "child_id": child.id if child else None},
                        contract,
                    )
                    db.session.commit()
                    flash("ذی‌نفع به قرارداد اضافه شد.", "success")
            return redirect(url_for("admin.contract_detail", contract_id=contract.id))
        elif action == "end_beneficiary":
            beneficiary = db.session.get(
                ContractBeneficiary, request.form.get("beneficiary_id", type=int)
            )
            if not beneficiary or beneficiary.contract_id != contract.id:
                abort(404)
            beneficiary.status = "ended"
            beneficiary.ended_at = utcnow()
            audit_organization(
                organization,
                "beneficiary_ended",
                {"beneficiary_id": beneficiary.id},
                contract,
            )
            db.session.commit()
            flash("پوشش ذی‌نفع پایان یافت و سابقه آن حفظ شد.", "info")
            return redirect(url_for("admin.contract_detail", contract_id=contract.id))

    return render_template(
        "admin/contract_detail.html",
        contract=contract,
        organization=organization,
        beneficiaries=contract.beneficiaries,
        projects=sorted(contract.support_plans, key=lambda item: item.created_at, reverse=True),
        parents=User.query.filter_by(role="parent").order_by(User.full_name).all(),
        children=Child.query.order_by(Child.name).all(),
        aggregate_report=contract_aggregate_report(contract),
    )


@bp.get("/organizations/<int:organization_id>/export.csv")
@login_required
@admin_required
def organization_export(organization_id):
    organization = db.get_or_404(Organization, organization_id)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["سازمان", "قرارداد", "والد", "موبایل والد", "فرزند", "وضعیت قرارداد", "تعهد", "پرداخت‌شده"])
    for contract in organization.contracts:
        parents = contract.covered_parents or [None]
        for parent in parents:
            children = parent.children if parent else contract.covered_children
            if not children:
                children = [None]
            for child in children:
                writer.writerow([
                    organization.name,
                    contract.title,
                    parent.full_name if parent else "",
                    parent.mobile if parent else "",
                    child.name if child else "",
                    contract.status,
                    contract.committed_amount_toman,
                    contract.amount_paid_toman,
                ])
    audit_organization(organization, "organization_report_exported", {"format": "csv"})
    db.session.commit()
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="organization-{organization.id}-report.csv"'},
    )


@bp.route("/projects", methods=["GET", "POST"])
@login_required
@admin_required
def projects():
    organizations = Organization.query.order_by(Organization.name).all()
    contracts = OrganizationContract.query.filter(
        OrganizationContract.status.in_(["draft", "active"])
    ).order_by(OrganizationContract.created_at.desc()).all()
    if request.method == "POST":
        values, errors = project_form_values()
        contract_id = request.form.get("contract_id", type=int)
        contract = db.session.get(OrganizationContract, contract_id) if contract_id else None
        organization_id = request.form.get("organization_id", type=int)
        organization = contract.organization if contract else (
            db.session.get(Organization, organization_id) if organization_id else None
        )
        new_organization_name = request.form.get("new_organization_name", "").strip()
        if not organization and len(new_organization_name) < 3:
            errors.append("یک قرارداد معتبر را انتخاب کنید.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            # Compatibility path for earlier clients; the new UI creates organization and contract separately.
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
                audit_organization(organization, "organization_created", {"source": "legacy_project_form"})
            if not contract:
                contract_no = f"LEGACY-{values['code']}"
                contract = OrganizationContract.query.filter_by(contract_no=contract_no).first()
                if not contract:
                    contract = OrganizationContract(
                        organization_id=organization.id,
                        title=values["name"],
                        contract_no=contract_no,
                        status="active" if values["status"] == "active" else "draft",
                        starts_on=values["starts_on"],
                        ends_on=values["ends_on"],
                        total_amount_toman=values["total_budget_toman"],
                        services_json=values["eligible_services_json"],
                        created_by=current_user.id,
                    )
                    db.session.add(contract)
                    db.session.flush()
                    audit_organization(
                        organization,
                        "contract_created",
                        {"source": "legacy_project_form", "contract_no": contract.contract_no},
                        contract,
                    )
            project = SponsoredProject(
                organization_id=organization.id,
                contract_id=contract.id,
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
        contracts=contracts,
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
            contract = db.session.get(
                OrganizationContract, request.form.get("contract_id", type=int)
            )
            organization = contract.organization if contract else project.organization
            if contract and contract.status == "archived":
                errors.append("قرارداد بایگانی‌شده قابل انتخاب نیست.")
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                before = {"status": project.status, "code": project.code}
                project.organization_id = organization.id
                project.contract_id = contract.id if contract else project.contract_id
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
    contracts = OrganizationContract.query.filter(
        OrganizationContract.status != "archived"
    ).order_by(OrganizationContract.created_at.desc()).all()
    memberships = sorted(project.memberships, key=lambda item: item.joined_at, reverse=True)
    split = project.calculate_split()
    return render_template(
        "admin/project_detail.html",
        project=project,
        organizations=organizations,
        contracts=contracts,
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


@bp.get("/projects/<int:project_id>/impact.csv")
@login_required
@admin_required
def project_impact_export(project_id):
    project = db.get_or_404(SponsoredProject, project_id)
    report = project_anonymous_report(
        project, current_app.config["ANONYMOUS_REPORT_MIN_GROUP"]
    )
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["شاخص", "مقدار"])
    writer.writerow(["پروژه", report["project"]])
    writer.writerow(["سازمان", report["organization"]])
    writer.writerow(["تعداد اعضا", report["member_count"]])
    if report["suppressed"]:
        writer.writerow(
            [
                "حفاظت حریم خصوصی",
                f"شاخص‌های اثربخشی تا رسیدن گروه به {report['minimum_group_size']} عضو نمایش داده نمی‌شوند.",
            ]
        )
    else:
        writer.writerow(["تعداد فرزندان", report["child_count"]])
        writer.writerow(["برنامه شروع‌شده", report["plans_started"]])
        writer.writerow(["برنامه تکمیل‌شده", report["plans_completed"]])
        writer.writerow(["اقدام تکمیل‌شده", report["actions_completed"]])
        writer.writerow(["نتیجه ثبت‌شده", report["outcomes"]["recorded_outcomes"]])
        writer.writerow(["نرخ کمک‌کنندگی (%)", report["outcomes"]["helped_rate"]])
        writer.writerow(["میانگین اطمینان والد", report["outcomes"]["average_confidence"]])
    audit_project(
        project,
        "anonymous_impact_exported",
        {"suppressed": report["suppressed"], "minimum_group_size": report["minimum_group_size"]},
    )
    db.session.commit()
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="project-{project.id}-anonymous-impact.csv"'
        },
    )


def guardian_organizations(user):
    values = {
        membership.project.organization.id: membership.project.organization
        for membership in user.project_memberships
    }
    for beneficiary in ContractBeneficiary.query.filter_by(user_id=user.id).all():
        values[beneficiary.contract.organization_id] = beneficiary.contract.organization
    return sorted(values.values(), key=lambda item: item.name)


def child_contracts(child):
    values = {
        beneficiary.contract_id: beneficiary.contract
        for beneficiary in ContractBeneficiary.query.filter_by(child_id=child.id).all()
    }
    guardian_ids = {child.user_id}
    guardian_ids.update(
        link.guardian_id for link in child.guardian_links if link.status == "active"
    )
    for membership in ProjectMembership.query.filter(
        ProjectMembership.user_id.in_(guardian_ids)
    ).all():
        if membership.project.contract:
            values[membership.project.contract_id] = membership.project.contract
    return sorted(values.values(), key=lambda item: item.created_at, reverse=True)


@bp.route("/profile-schemas", methods=["GET", "POST"])
@login_required
@admin_required
def profile_schemas():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "bind_form":
            definition = db.session.get(
                ProfileDefinition, request.form.get("definition_id", type=int)
            )
            form = db.session.get(DynamicForm, request.form.get("form_id", type=int))
            if not definition or not form:
                flash("تعریف پروفایل یا فرم معتبر نیست.", "danger")
            elif form.status != "published":
                flash("فقط فرم منتشرشده را می‌توان به پروفایل متصل کرد.", "danger")
            elif ProfileFormBinding.query.filter_by(
                definition_id=definition.id, form_id=form.id
            ).first():
                flash("این فرم قبلاً به نسخه پروفایل متصل شده است.", "warning")
            else:
                binding = ProfileFormBinding(
                    definition_id=definition.id,
                    form_id=form.id,
                    section_key=request.form.get("section_key", "general").strip()[:80] or "general",
                    section_title=request.form.get("section_title", "").strip()[:160]
                    or form.title,
                    sort_order=max(0, request.form.get("sort_order", 0, type=int)),
                )
                db.session.add(binding)
                db.session.commit()
                flash("فرم منتشرشده به پروفایل متصل شد.", "success")
                return redirect(url_for("admin.profile_schemas"))
        elif action == "toggle_binding":
            binding = db.session.get(
                ProfileFormBinding, request.form.get("binding_id", type=int)
            )
            if not binding:
                abort(404)
            binding.is_active = not binding.is_active
            db.session.commit()
            flash("وضعیت اتصال فرم تغییر کرد.", "info")
            return redirect(url_for("admin.profile_schemas"))
        elif action == "new_version":
            profile_type = request.form.get("profile_type", "")
            current = active_profile_definition(profile_type)
            if profile_type not in PROFILE_TYPES or not current:
                flash("نوع پروفایل معتبر نیست.", "danger")
            else:
                current.status = "archived"
                new_definition = ProfileDefinition(
                    profile_type=profile_type,
                    title=current.title,
                    version=current.version + 1,
                    status="active",
                    created_by=current_user.id,
                )
                db.session.add(new_definition)
                db.session.flush()
                binding_map = {}
                for item in current.bindings:
                    cloned_binding = ProfileFormBinding(
                        definition_id=new_definition.id,
                        form_id=item.form_id,
                        section_key=item.section_key,
                        section_title=item.section_title,
                        sort_order=item.sort_order,
                        is_active=item.is_active,
                    )
                    db.session.add(cloned_binding)
                    db.session.flush()
                    binding_map[str(item.id)] = str(cloned_binding.id)
                for old_record in current.records:
                    migrated_values = {}
                    for key, value in old_record.values.items():
                        binding_id, separator, field_id = key.partition(":")
                        if separator and binding_id in binding_map:
                            migrated_values[f"{binding_map[binding_id]}:{field_id}"] = value
                    db.session.add(
                        ProfileRecord(
                            definition_id=new_definition.id,
                            subject_id=old_record.subject_id,
                            values_json=json.dumps(migrated_values, ensure_ascii=False),
                            record_version=old_record.record_version + 1,
                            updated_by=current_user.id,
                        )
                    )
                db.session.commit()
                flash(
                    f"نسخه {new_definition.version} پروفایل با حفظ داده‌های قبلی ساخته شد.",
                    "success",
                )
                return redirect(url_for("admin.profile_schemas"))

    definitions = {
        profile_type: active_profile_definition(profile_type)
        for profile_type in PROFILE_TYPES
    }
    forms = DynamicForm.query.filter_by(status="published").order_by(DynamicForm.title).all()
    return render_template(
        "admin/profile_schemas.html",
        definitions=definitions,
        forms=forms,
        profile_types=PROFILE_TYPES,
    )


@bp.get("/users")
@login_required
@admin_required
def users():
    search = request.args.get("q", "").strip()
    organization_id = request.args.get("organization_id", type=int)
    user_query = User.query
    child_query = Child.query
    if search:
        normalized = normalize_digits(search)
        user_query = user_query.filter(
            or_(
                User.full_name.contains(search),
                User.mobile.contains(normalized),
                User.national_id.contains(normalized),
            )
        )
        child_query = child_query.filter(
            or_(Child.name.contains(search), Child.national_id.contains(normalized))
        )
    if organization_id:
        user_ids = {
            item.user_id
            for item in ProjectMembership.query.join(SponsoredProject).filter(
                SponsoredProject.organization_id == organization_id
            )
        }
        user_ids.update(
            item.user_id
            for item in ContractBeneficiary.query.join(OrganizationContract).filter(
                OrganizationContract.organization_id == organization_id,
                ContractBeneficiary.user_id.isnot(None),
            )
        )
        child_ids = {
            item.child_id
            for item in ContractBeneficiary.query.join(OrganizationContract).filter(
                OrganizationContract.organization_id == organization_id,
                ContractBeneficiary.child_id.isnot(None),
            )
        }
        child_ids.update(
            child.id for user_id in user_ids for child in db.session.get(User, user_id).children
        )
        user_query = user_query.filter(User.id.in_(user_ids or {-1}))
        child_query = child_query.filter(Child.id.in_(child_ids or {-1}))
    page_size = current_app.config["ADMIN_PAGE_SIZE"]
    user_pagination = user_query.order_by(User.created_at.desc()).paginate(
        page=max(1, request.args.get("parent_page", 1, type=int)), per_page=page_size,
        error_out=False,
    )
    child_pagination = child_query.order_by(Child.created_at.desc()).paginate(
        page=max(1, request.args.get("child_page", 1, type=int)), per_page=page_size,
        error_out=False,
    )
    return render_template(
        "admin/users.html",
        users=user_pagination.items,
        children=child_pagination.items,
        user_pagination=user_pagination,
        child_pagination=child_pagination,
        organizations=Organization.query.order_by(Organization.name).all(),
        search=search,
        selected_organization_id=organization_id,
    )


@bp.route("/guardians/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def guardian_profile(user_id):
    guardian = db.get_or_404(User, user_id)
    if guardian.role != "parent":
        abort(404)
    definition = active_profile_definition("guardian")
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_basic":
            full_name = request.form.get("full_name", "").strip()
            national_id = normalize_digits(request.form.get("national_id", ""))[:10]
            if len(full_name) < 3:
                flash("نام و نام خانوادگی را کامل وارد کنید.", "danger")
            elif national_id and User.query.filter(
                User.national_id == national_id, User.id != guardian.id
            ).first():
                flash("کد ملی قبلاً برای کاربر دیگری ثبت شده است.", "danger")
            else:
                guardian.full_name = full_name
                guardian.national_id = national_id
                guardian.email = request.form.get("email", "").strip()[:160]
                guardian.is_active_account = request.form.get("is_active") == "1"
                db.session.commit()
                flash("اطلاعات پایه والد ذخیره شد.", "success")
                return redirect(url_for("admin.guardian_profile", user_id=guardian.id))
        elif action == "save_profile" and definition:
            _record, errors = save_profile_values(
                definition, guardian.id, request.form, current_user.id
            )
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db.session.commit()
                flash("فیلدهای پویای پروفایل والد ذخیره شد.", "success")
                return redirect(url_for("admin.guardian_profile", user_id=guardian.id))

    record = profile_record(definition, guardian.id)
    style_results = ParentingStyleAssessment.query.filter_by(user_id=guardian.id).order_by(
        ParentingStyleAssessment.created_at.desc()
    ).all()
    form_responses = FormResponse.query.filter_by(user_id=guardian.id).order_by(
        FormResponse.created_at.desc()
    ).all()
    reports = RecommendationRun.query.filter_by(user_id=guardian.id).order_by(
        RecommendationRun.created_at.desc()
    ).all()
    plans = WeeklyPlan.query.filter_by(user_id=guardian.id).order_by(
        WeeklyPlan.created_at.desc()
    ).all()
    return render_template(
        "admin/guardian_profile.html",
        guardian=guardian,
        family_children=sorted(
            {item.id: item for item in guardian.children + [link.child for link in guardian.guardian_links if link.status == 'active']}.values(),
            key=lambda item: item.name,
        ),
        organizations=guardian_organizations(guardian),
        definition=definition,
        record=record,
        profile_sections=profile_sections(definition, record),
        style_results=style_results,
        form_responses=form_responses,
        reports=reports,
        plans=plans,
        allocations=[allocation for membership in guardian.project_memberships for allocation in membership.allocations],
    )


@bp.route("/children/<int:child_id>/profile", methods=["GET", "POST"])
@login_required
@admin_required
def admin_child_profile(child_id):
    child = db.get_or_404(Child, child_id)
    if not GuardianRelationship.query.filter_by(
        child_id=child.id, guardian_id=child.user_id
    ).first():
        db.session.add(
            GuardianRelationship(
                child_id=child.id,
                guardian_id=child.user_id,
                relationship_type="guardian",
                access_level="full",
                status="active",
                accepted_at=child.created_at,
            )
        )
        db.session.commit()
    definition = active_profile_definition("child")
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_basic":
            child.name = request.form.get("name", "").strip()[:80]
            child.national_id = normalize_digits(request.form.get("national_id", ""))[:10]
            child.birth_year = request.form.get("birth_year", child.birth_year, type=int)
            child.gender = request.form.get("gender", "unspecified")
            child.notes = request.form.get("notes", "").strip()[:400]
            if len(child.name) < 2:
                flash("نام فرزند معتبر نیست.", "danger")
            else:
                db.session.commit()
                flash("اطلاعات پایه فرزند ذخیره شد.", "success")
                return redirect(url_for("admin.admin_child_profile", child_id=child.id))
        elif action == "save_profile" and definition:
            _record, errors = save_profile_values(
                definition, child.id, request.form, current_user.id
            )
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db.session.commit()
                flash("فیلدهای پویای پروفایل فرزند ذخیره شد.", "success")
                return redirect(url_for("admin.admin_child_profile", child_id=child.id))
        elif action == "add_guardian":
            mobile = normalize_digits(request.form.get("mobile", ""))
            guardian = User.query.filter_by(mobile=mobile, role="parent").first()
            relationship_type = request.form.get("relationship_type", "guardian")
            access_level = request.form.get("access_level", "full")
            status = request.form.get("status", "pending")
            if not guardian:
                flash("والدی با این شماره موبایل پیدا نشد.", "danger")
            elif relationship_type not in {"mother", "father", "guardian"} or access_level not in {"full", "view", "limited"}:
                flash("نوع رابطه یا سطح دسترسی معتبر نیست.", "danger")
            else:
                link = GuardianRelationship.query.filter_by(
                    child_id=child.id, guardian_id=guardian.id
                ).first()
                if not link:
                    link = GuardianRelationship(
                        child_id=child.id,
                        guardian_id=guardian.id,
                        invited_by=current_user.id,
                    )
                    db.session.add(link)
                link.relationship_type = relationship_type
                link.access_level = access_level
                link.status = status if status in {"pending", "active"} else "pending"
                link.accepted_at = utcnow() if link.status == "active" else None
                link.ended_at = None
                db.session.commit()
                flash("رابطه سرپرستی ثبت شد.", "success")
                return redirect(url_for("admin.admin_child_profile", child_id=child.id))
        elif action == "revoke_guardian":
            link = db.session.get(
                GuardianRelationship, request.form.get("relationship_id", type=int)
            )
            if not link or link.child_id != child.id:
                abort(404)
            if link.guardian_id == child.user_id:
                flash("رابطه مالک اصلی پرونده قابل لغو نیست.", "danger")
            else:
                link.status = "revoked"
                link.ended_at = utcnow()
                db.session.commit()
                flash("دسترسی سرپرست لغو شد؛ سابقه رابطه حفظ گردید.", "info")
            return redirect(url_for("admin.admin_child_profile", child_id=child.id))
        elif action == "schedule_growth_report":
            form = db.session.get(DynamicForm, request.form.get("form_id", type=int))
            plan_id = request.form.get("weekly_plan_id", type=int)
            action_id = request.form.get("daily_action_id", type=int)
            plan = db.session.get(WeeklyPlan, plan_id) if plan_id else None
            action_item = db.session.get(DailyAction, action_id) if action_id else None
            cadence = request.form.get("cadence", "weekly")
            due_raw = request.form.get("due_at", "").strip()
            due_at = None
            try:
                due_at = datetime.fromisoformat(due_raw) if due_raw else None
            except ValueError:
                pass
            if not form or form.status != "published" or cadence not in {"daily", "weekly"}:
                flash("فرم منتشرشده و تناوب معتبر را انتخاب کنید.", "danger")
            elif ((plan and plan.child_id != child.id)
                  or (action_item and action_item.plan.child_id != child.id)):
                abort(400)
            else:
                assignment = FormAssignment.query.filter_by(
                    form_id=form.id, target_type="child", target_id=child.id, status="active"
                ).first()
                if not assignment:
                    assignment = FormAssignment(
                        form_id=form.id, target_type="child", target_id=child.id,
                        target_ref=f"growth:{child.id}", title=f"گزارش رشد {child.name}",
                        due_at=due_at, created_by=current_user.id,
                    )
                    db.session.add(assignment)
                db.session.add(GrowthReportSchedule(
                    user_id=child.user_id, child_id=child.id, form_id=form.id,
                    weekly_plan_id=plan.id if plan else None,
                    daily_action_id=action_item.id if action_item else None,
                    cadence=cadence, due_at=due_at,
                ))
                db.session.commit()
                flash("گزارش رشد به مسیر فرزند متصل شد.", "success")
                return redirect(url_for("admin.admin_child_profile", child_id=child.id))

    record = profile_record(definition, child.id)
    return render_template(
        "admin/child_profile.html",
        child=child,
        definition=definition,
        record=record,
        profile_sections=profile_sections(definition, record),
        relationships=child.guardian_links,
        contracts=child_contracts(child),
        assessments=ParentingAssessment.query.filter_by(child_id=child.id).order_by(ParentingAssessment.created_at.desc()).all(),
        style_results=ParentingStyleAssessment.query.filter_by(child_id=child.id).order_by(ParentingStyleAssessment.created_at.desc()).all(),
        form_responses=FormResponse.query.filter_by(child_id=child.id).order_by(FormResponse.created_at.desc()).all(),
        snapshots=ChildProfileSnapshot.query.filter_by(child_id=child.id).order_by(ChildProfileSnapshot.created_at.desc()).all(),
        recommendations=RecommendationRun.query.filter_by(child_id=child.id).order_by(RecommendationRun.created_at.desc()).all(),
        plans=WeeklyPlan.query.filter_by(child_id=child.id).order_by(WeeklyPlan.created_at.desc()).all(),
        growth_state=growth_dashboard_state(child.user_id, child.id),
        growth_timeline=build_growth_timeline(child.user_id, child.id),
        growth_forms=DynamicForm.query.filter_by(status="published").order_by(DynamicForm.title).all(),
        growth_schedules=GrowthReportSchedule.query.filter_by(child_id=child.id).order_by(
            GrowthReportSchedule.created_at.desc()).all(),
    )


def save_narrative_from_form(narrative=None):
    topic = db.session.get(ScenarioTopic, request.form.get("topic_id", type=int))
    level = request.form.get("level", type=int)
    if not topic or level not in range(1, 6):
        return None, ["موضوع و سطح روایت معتبر نیست."]
    title = request.form.get("title", "").strip()[:180]
    context_text = request.form.get("context_text", "").strip()
    age_min_value = request.form.get("child_age_min", type=int)
    age_max_value = request.form.get("child_age_max", type=int)
    age_min = min(25, max(0, age_min_value if age_min_value is not None else 6))
    age_max = min(25, max(age_min, age_max_value if age_max_value is not None else 18))
    if not narrative:
        narrative = ScenarioNarrative(
            topic_id=topic.id,
            level=level,
            title=title,
            context_text=context_text,
            created_by=current_user.id,
        )
        db.session.add(narrative)
        db.session.flush()
    elif narrative.status == "published":
        narrative.version += 1
        narrative.status = "review"
        narrative.published_at = None
    narrative.topic_id = topic.id
    narrative.level = level
    narrative.title = title
    narrative.context_text = context_text
    narrative.child_age_min = age_min
    narrative.child_age_max = age_max
    narrative.child_quote = request.form.get("child_quote", "").strip()[:700]
    narrative.source_note = request.form.get("source_note", "").strip()[:700]
    for field_name in (
        "previous_narrative_id",
        "growth_next_narrative_id",
        "fall_next_narrative_id",
    ):
        related_id = request.form.get(field_name, type=int)
        related = db.session.get(ScenarioNarrative, related_id) if related_id else None
        if related and related.id != narrative.id and related.topic_id == topic.id:
            setattr(narrative, field_name, related.id)
        else:
            setattr(narrative, field_name, None)
    styles = ParentingStyleDefinition.query.filter_by(is_active=True).order_by(
        ParentingStyleDefinition.sort_order
    ).all()
    existing = {item.style_id: item for item in narrative.reactions}
    for style in styles:
        reaction = existing.get(style.id)
        if not reaction:
            reaction = ScenarioReaction(narrative_id=narrative.id, style_id=style.id, reaction_text="")
            db.session.add(reaction)
        reaction.reaction_text = request.form.get(f"reaction_{style.code}", "").strip()
        reaction.present_skill_ids_json = json.dumps(
            request.form.getlist(f"present_skills_{style.code}", type=int), ensure_ascii=False
        )
        reaction.missing_skill_ids_json = json.dumps(
            request.form.getlist(f"missing_skills_{style.code}", type=int), ensure_ascii=False
        )
        reaction.short_term_consequence = request.form.get(
            f"short_term_{style.code}", ""
        ).strip()
        reaction.long_term_consequence = request.form.get(
            f"long_term_{style.code}", ""
        ).strip()
        reaction.retry_guidance = request.form.get(f"retry_{style.code}", "").strip()
        score_value = request.form.get(f"score_{style.code}", type=int)
        reaction.scientific_score = min(100, max(0, score_value or 0))
    errors = narrative_publish_errors(narrative)
    if not title:
        errors.insert(0, "عنوان روایت الزامی است.")
    return narrative, errors


def copy_narrative(source):
    copy = ScenarioNarrative(
        topic_id=source.topic_id,
        level=source.level,
        title=f"کپی {source.title}"[:180],
        context_text=source.context_text,
        child_age_min=source.child_age_min,
        child_age_max=source.child_age_max,
        child_quote=source.child_quote,
        source_note=source.source_note,
        status="draft",
        copied_from_id=source.id,
        previous_narrative_id=source.previous_narrative_id,
        growth_next_narrative_id=source.growth_next_narrative_id,
        fall_next_narrative_id=source.fall_next_narrative_id,
        created_by=current_user.id,
    )
    db.session.add(copy)
    db.session.flush()
    for item in source.reactions:
        db.session.add(
            ScenarioReaction(
                narrative_id=copy.id,
                style_id=item.style_id,
                reaction_text=item.reaction_text,
                present_skill_ids_json=item.present_skill_ids_json,
                missing_skill_ids_json=item.missing_skill_ids_json,
                short_term_consequence=item.short_term_consequence,
                long_term_consequence=item.long_term_consequence,
                retry_guidance=item.retry_guidance,
                scientific_score=item.scientific_score,
            )
        )
    return copy


def sync_topic_skills(topic, skill_ids):
    valid_ids = {
        item.id for item in SkillModule.query.filter(SkillModule.id.in_(skill_ids)).all()
    } if skill_ids else set()
    existing = {item.skill_id: item for item in topic.skill_links}
    for skill_id, link in existing.items():
        if skill_id not in valid_ids:
            db.session.delete(link)
    for sort_order, skill_id in enumerate(skill_ids):
        if skill_id in valid_ids and skill_id not in existing:
            db.session.add(
                ScenarioTopicSkillMembership(
                    topic_id=topic.id, skill_id=skill_id, sort_order=sort_order
                )
            )
        elif skill_id in existing:
            existing[skill_id].sort_order = sort_order


@bp.route("/tree/topics/new", methods=["GET", "POST"])
@bp.route("/tree/topics/<int:topic_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def scenario_topic_editor(topic_id=None):
    topic = db.get_or_404(ScenarioTopic, topic_id) if topic_id else None
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:120]
        slug = make_slug(request.form.get("slug", ""))[:80]
        duplicate = ScenarioTopic.query.filter(
            ScenarioTopic.slug == slug,
            ScenarioTopic.id != (topic.id if topic else -1),
        ).first()
        if not title or not slug or duplicate:
            flash("عنوان و نامک یکتای موقعیت الزامی است.", "danger")
        else:
            if not topic:
                topic = ScenarioTopic(slug=slug, title=title, description="")
                db.session.add(topic)
                db.session.flush()
                for definition in CrisisLevelDefinition.query.order_by(
                    CrisisLevelDefinition.level
                ).all():
                    db.session.add(
                        ScenarioLevel(
                            topic_id=topic.id,
                            level=definition.level,
                            label=definition.title,
                            description=definition.description,
                        )
                    )
            topic.slug = slug
            topic.title = title
            topic.description = request.form.get("description", "").strip()[:500]
            topic.icon = request.form.get("icon", "fa-comments").strip()[:60]
            status = request.form.get("status", "active")
            topic.is_published = status == "active"
            profile = topic.catalog_profile
            if not profile:
                profile = ScenarioTopicProfile(topic_id=topic.id)
                db.session.add(profile)
            profile.domain = request.form.get("domain", "ارتباط خانوادگی").strip()[:100]
            profile.status = status if status in {"active", "inactive", "archived"} else "active"
            profile.sort_order = max(0, request.form.get("sort_order", 0, type=int))
            skill_ids = list(dict.fromkeys(request.form.getlist("skill_ids", type=int)))
            profile.target_skill_id = skill_ids[0] if skill_ids else None
            sync_topic_skills(topic, skill_ids)
            db.session.commit()
            flash("موقعیت و مهارت‌های مرتبط ذخیره شد.", "success")
            return redirect(url_for("admin.tree_builder", topic=topic.id))
    return render_template(
        "admin/scenario_topic_editor.html",
        topic=topic,
        skills=SkillModule.query.order_by(SkillModule.sort_order).all(),
    )


@bp.route(
    "/tree/topics/<int:topic_id>/narratives/new",
    defaults={"narrative_id": None},
    methods=["GET", "POST"],
)
@bp.route(
    "/tree/narratives/<int:narrative_id>/edit",
    defaults={"topic_id": None},
    methods=["GET", "POST"],
)
@login_required
@admin_required
def scenario_narrative_editor(topic_id=None, narrative_id=None):
    narrative = db.get_or_404(ScenarioNarrative, narrative_id) if narrative_id else None
    topic = narrative.topic if narrative else db.get_or_404(ScenarioTopic, topic_id)
    if request.method == "POST":
        narrative, errors = save_narrative_from_form(narrative)
        if not narrative:
            abort(400)
        db.session.commit()
        if errors:
            flash("روایت ذخیره شد؛ موارد باقی‌مانده انتشار پایین صفحه مشخص شده‌اند.", "warning")
        else:
            flash("روایت و هر چهار واکنش بامریند ذخیره شد.", "success")
        return redirect(
            url_for("admin.scenario_narrative_editor", narrative_id=narrative.id)
        )
    related_narratives = ScenarioNarrative.query.filter(
        ScenarioNarrative.topic_id == topic.id,
        ScenarioNarrative.id != (narrative.id if narrative else -1),
    ).order_by(ScenarioNarrative.level, ScenarioNarrative.title).all()
    return render_template(
        "admin/scenario_narrative_editor.html",
        topic=topic,
        narrative=narrative,
        styles=ParentingStyleDefinition.query.filter_by(is_active=True).order_by(
            ParentingStyleDefinition.sort_order
        ).all(),
        skills=SkillModule.query.order_by(SkillModule.sort_order).all(),
        crisis_levels=CrisisLevelDefinition.query.order_by(
            CrisisLevelDefinition.level
        ).all(),
        related_narratives=related_narratives,
        narrative_errors=narrative_publish_errors(narrative) if narrative else [],
    )


@bp.route("/tree", methods=["GET", "POST"])
@login_required
@admin_required
def tree_builder():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_topic_meta":
            topic = db.session.get(ScenarioTopic, request.form.get("topic_id", type=int))
            if not topic:
                abort(404)
            profile = ScenarioTopicProfile.query.filter_by(topic_id=topic.id).first()
            if not profile:
                profile = ScenarioTopicProfile(topic_id=topic.id)
                db.session.add(profile)
            topic.title = request.form.get("title", "").strip()[:120]
            topic.description = request.form.get("description", "").strip()[:500]
            topic.icon = request.form.get("icon", "fa-comments").strip()[:60]
            topic.is_published = request.form.get("status") == "active"
            profile.domain = request.form.get("domain", "ارتباط خانوادگی").strip()[:100]
            profile.target_skill_id = request.form.get("target_skill_id", type=int)
            profile.status = request.form.get("status", "active") if request.form.get("status") in {"active", "inactive", "archived"} else "active"
            profile.sort_order = request.form.get("sort_order", 0, type=int)
            db.session.commit()
            flash("مشخصات کاتالوگ موقعیت ذخیره شد.", "success")
            return redirect(url_for("admin.tree_builder", topic_id=topic.id))
        elif action == "save_narrative":
            narrative_id = request.form.get("narrative_id", type=int)
            narrative = db.session.get(ScenarioNarrative, narrative_id) if narrative_id else None
            narrative, errors = save_narrative_from_form(narrative)
            db.session.commit()
            if errors:
                flash("روایت ذخیره شد؛ برای انتشار هنوز مواردی باید کامل شود.", "warning")
            else:
                flash("روایت و چهار واکنش آن ذخیره شد.", "success")
            return redirect(
                url_for("admin.scenario_narrative_editor", narrative_id=narrative.id)
            )
        elif action == "copy_narrative":
            source = db.get_or_404(ScenarioNarrative, request.form.get("narrative_id", type=int))
            narrative = copy_narrative(source)
            db.session.commit()
            flash("یک نسخه پیش‌نویس مستقل از روایت ساخته شد.", "success")
            return redirect(url_for("admin.scenario_narrative_editor", narrative_id=narrative.id))
        elif action == "request_narrative_review":
            narrative = db.get_or_404(ScenarioNarrative, request.form.get("narrative_id", type=int))
            errors = narrative_publish_errors(narrative)
            if errors:
                for error in errors[:8]:
                    flash(error, "danger")
            else:
                narrative.status = "review"
                fingerprint = ScientificReview.fingerprint(resource_snapshot("scenario_narrative", narrative))
                review = ScientificReview.query.filter_by(
                    resource_type="scenario_narrative",
                    resource_id=narrative.id,
                    resource_version=str(narrative.version),
                    snapshot_hash=fingerprint,
                ).first()
                if not review:
                    db.session.add(
                        ScientificReview(
                            resource_type="scenario_narrative",
                            resource_id=narrative.id,
                            resource_title=narrative.title,
                            resource_version=str(narrative.version),
                            snapshot_hash=fingerprint,
                            requested_by=current_user.id,
                        )
                    )
                db.session.commit()
                flash("روایت برای ناظر علمی ارسال شد.", "success")
            return redirect(url_for("admin.scenario_narrative_editor", narrative_id=narrative.id))
        elif action == "publish_narrative":
            narrative = db.get_or_404(ScenarioNarrative, request.form.get("narrative_id", type=int))
            errors = narrative_publish_errors(narrative)
            if current_app.config["REQUIRE_SCIENTIFIC_APPROVAL"] and not approved_for_current_snapshot("scenario_narrative", narrative):
                errors.append("انتشار production فقط پس از تأیید علمی همین نسخه مجاز است.")
            if errors:
                for error in errors[:10]:
                    flash(error, "danger")
            else:
                narrative.status = "published"
                narrative.published_at = utcnow()
                db.session.commit()
                flash("روایت منتشر شد و در تمرین والد قابل انتخاب است.", "success")
            return redirect(url_for("admin.scenario_narrative_editor", narrative_id=narrative.id))
        elif action == "archive_narrative":
            narrative = db.get_or_404(ScenarioNarrative, request.form.get("narrative_id", type=int))
            narrative.status = "archived"
            db.session.commit()
            flash("روایت بایگانی شد؛ تاریخچه تلاش‌ها حفظ می‌شود.", "info")
            return redirect(url_for("admin.tree_builder", topic=narrative.topic_id))
        elif action == "import_narratives":
            try:
                payload = json.loads(request.form.get("scenario_json", ""))
            except ValueError:
                payload = None
            topics = {item.slug: item for item in ScenarioTopic.query.all()}
            rows, errors = validate_scenario_contract(payload, topics)
            if errors:
                for error in errors[:12]:
                    flash(error, "danger")
            else:
                created = []
                for row in rows:
                    reactions = row.pop("reactions")
                    topic = row.pop("topic")
                    narrative = ScenarioNarrative(
                        topic_id=topic.id,
                        status="draft",
                        created_by=current_user.id,
                        **row,
                    )
                    db.session.add(narrative)
                    db.session.flush()
                    for reaction_row in reactions:
                        style = reaction_row.pop("style")
                        present = reaction_row.pop("present_skill_ids")
                        missing = reaction_row.pop("missing_skill_ids")
                        db.session.add(
                            ScenarioReaction(
                                narrative_id=narrative.id,
                                style_id=style.id,
                                present_skill_ids_json=json.dumps(present),
                                missing_skill_ids_json=json.dumps(missing),
                                **reaction_row,
                            )
                        )
                    created.append(narrative)
                db.session.commit()
                flash(f"{len(created)} روایت به‌صورت پیش‌نویس وارد شد.", "success")
                first = created[0]
                return redirect(url_for("admin.scenario_narrative_editor", narrative_id=first.id))
        elif action == "add_topic":
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
                db.session.add(
                    ScenarioTopicProfile(
                        topic_id=topic.id,
                        domain=request.form.get("domain", "ارتباط خانوادگی").strip()[:100],
                        target_skill_id=request.form.get("target_skill_id", type=int),
                        status="active",
                        sort_order=ScenarioTopic.query.count(),
                    )
                )
                labels = ["سطحی", "آشکار", "پیش‌رونده", "قوی / خطرناک", "عمیق"]
                for index, label in enumerate(labels, 1):
                    db.session.add(ScenarioLevel(topic_id=topic.id, level=index, label=label))
                db.session.commit()
                flash("موضوع و پنج سطح شدت ساخته شد.", "success")
                return redirect(url_for("admin.scenario_topic_editor", topic_id=topic.id))
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

    if request.args.get("narrative_id", type=int):
        return redirect(
            url_for(
                "admin.scenario_narrative_editor",
                narrative_id=request.args.get("narrative_id", type=int),
            )
        )
    if request.args.get("new", type=int) and request.args.get("topic_id", type=int):
        return redirect(
            url_for(
                "admin.scenario_narrative_editor",
                topic_id=request.args.get("topic_id", type=int),
            )
        )

    topics = (
        ScenarioTopic.query.outerjoin(ScenarioTopicProfile)
        .order_by(ScenarioTopicProfile.sort_order, ScenarioTopic.id)
        .all()
    )
    narratives = ScenarioNarrative.query.order_by(
        ScenarioNarrative.topic_id,
        ScenarioNarrative.level,
        ScenarioNarrative.updated_at.desc(),
    ).all()
    narratives_by_topic = {topic.id: [] for topic in topics}
    for narrative in narratives:
        narratives_by_topic.setdefault(narrative.topic_id, []).append(narrative)
    return render_template(
        "admin/tree_builder.html",
        topics=topics,
        crisis_levels=CrisisLevelDefinition.query.order_by(CrisisLevelDefinition.level).all(),
        styles=ParentingStyleDefinition.query.filter_by(is_active=True).order_by(ParentingStyleDefinition.sort_order).all(),
        skills=SkillModule.query.order_by(SkillModule.sort_order).all(),
        narratives=narratives,
        narratives_by_topic=narratives_by_topic,
        selected_topic_id=request.args.get("topic", type=int),
    )


@bp.route("/tree/narratives/<int:narrative_id>/export")
@login_required
@admin_required
def export_scenario_narrative(narrative_id):
    narrative = db.get_or_404(ScenarioNarrative, narrative_id)
    body = json.dumps(narrative_to_contract(narrative), ensure_ascii=False, indent=2)
    return Response(
        body,
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="scenario-{narrative.id}-v{narrative.version}.json"'
        },
    )


def form_snapshot_hash(form):
    return ScientificReview.fingerprint(resource_snapshot("form", form))


def save_form_snapshot(form):
    snapshot_hash = form_snapshot_hash(form)
    snapshot = FormVersion.query.filter_by(form_id=form.id, version=form.version).first()
    if not snapshot:
        snapshot = FormVersion(
            form_id=form.id,
            version=form.version,
            created_by=current_user.id,
            title=form.title,
            snapshot_hash=snapshot_hash,
        )
        db.session.add(snapshot)
    snapshot.title = form.title
    snapshot.schema_json = form.schema_json
    snapshot.settings_json = form.settings_json
    snapshot.scoring_json = form.scoring_json
    snapshot.snapshot_hash = snapshot_hash
    return snapshot


def parse_datetime_local(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def unique_form_slug(value, exclude_id=None):
    base = make_slug(value)[:100]
    candidate = base
    counter = 2
    while DynamicForm.query.filter(
        DynamicForm.slug == candidate,
        DynamicForm.id != (exclude_id or -1),
    ).first():
        suffix = f"-{counter}"
        candidate = f"{base[:100-len(suffix)]}{suffix}"
        counter += 1
    return candidate


def create_scientific_form_review(form):
    fingerprint = form_snapshot_hash(form)
    review = ScientificReview.query.filter_by(
        resource_type="form",
        resource_id=form.id,
        resource_version=str(form.version),
        snapshot_hash=fingerprint,
    ).first()
    if not review:
        review = ScientificReview(
            resource_type="form",
            resource_id=form.id,
            resource_title=form.title,
            resource_version=str(form.version),
            snapshot_hash=fingerprint,
            requested_by=current_user.id,
        )
        db.session.add(review)
    else:
        review.status = "pending"
        review.requested_by = current_user.id
        review.requested_at = utcnow()
        review.reviewed_by = None
        review.reviewed_at = None
        review.reviewer_note = ""
    return review


@bp.route("/forms", methods=["GET", "POST"])
@login_required
@admin_required
def form_builder():
    if request.method == "POST":
        action = request.form.get("action")
        form = db.session.get(DynamicForm, request.form.get("form_id", type=int))
        if not form:
            abort(404)
        if action == "archive":
            form.status = "archived"
            form.archived_at = utcnow()
            save_form_snapshot(form)
            db.session.commit()
            flash("فرم بایگانی شد و پاسخ‌های قبلی محفوظ ماندند.", "info")
        elif action == "duplicate":
            clone = DynamicForm(
                title=f"کپی {form.title}",
                slug=unique_form_slug(f"{form.slug}-copy"),
                description=form.description,
                form_type=form.form_type,
                use_case=form.use_case,
                version=1,
                status="draft",
                schema_json=form.schema_json,
                settings_json=form.settings_json,
                scoring_json=form.scoring_json,
                created_by=current_user.id,
            )
            db.session.add(clone)
            db.session.flush()
            save_form_snapshot(clone)
            db.session.commit()
            flash("یک کپی Draft از فرم ساخته شد.", "success")
            return redirect(url_for("admin.form_editor", form_id=clone.id))
        return redirect(url_for("admin.form_builder"))

    query = DynamicForm.query
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    form_type = request.args.get("type", "").strip()
    if search:
        query = query.filter(
            or_(DynamicForm.title.contains(search), DynamicForm.slug.contains(search))
        )
    if status in FORM_STATUSES:
        query = query.filter_by(status=status)
    if form_type in FORM_TYPES:
        query = query.filter_by(form_type=form_type)
    forms = query.order_by(DynamicForm.updated_at.desc(), DynamicForm.id.desc()).all()
    stats = {
        "all": DynamicForm.query.count(),
        "published": DynamicForm.query.filter_by(status="published").count(),
        "review": DynamicForm.query.filter_by(status="review").count(),
        "responses": FormResponse.query.filter_by(status="submitted").count(),
    }
    return render_template(
        "admin/forms.html",
        forms=forms,
        stats=stats,
        search=search,
        selected_status=status,
        selected_type=form_type,
        form_types=FORM_TYPES,
        ai_contract=AI_CONTRACT,
    )


@bp.route("/forms/new", methods=["GET", "POST"])
@bp.route("/forms/<int:form_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def form_editor(form_id=None):
    form = db.get_or_404(DynamicForm, form_id) if form_id else None
    if request.method == "POST":
        action = request.form.get("action", "save_draft")
        title = request.form.get("title", "").strip()[:160]
        slug = make_slug(request.form.get("slug"))[:100]
        try:
            raw_fields = json.loads(request.form.get("schema_json", "[]"))
        except ValueError:
            raw_fields = []
        fields, errors = normalize_schema(raw_fields)
        try:
            raw_settings = json.loads(request.form.get("settings_json", "{}"))
        except ValueError:
            raw_settings = {}
            errors.append("settings: JSON تنظیمات معتبر نیست.")
        try:
            raw_scoring = json.loads(request.form.get("scoring_json", "{}"))
        except ValueError:
            raw_scoring = {}
            errors.append("scoring: JSON امتیازدهی معتبر نیست.")
        settings = normalize_settings(raw_settings)
        scoring, scoring_errors = normalize_scoring(raw_scoring)
        errors.extend(scoring_errors)
        form_type = request.form.get("form_type", "assessment")
        if form_type not in FORM_TYPES:
            errors.append("نوع فرم معتبر نیست.")
        duplicate = DynamicForm.query.filter(
            DynamicForm.slug == slug,
            DynamicForm.id != (form.id if form else -1),
        ).first()
        if len(title) < 3:
            errors.append("عنوان فرم باید حداقل سه نویسه باشد.")
        if duplicate:
            errors.append("نامک فرم قبلاً استفاده شده است.")
        if action not in {"save_draft", "request_review", "publish"}:
            abort(400)
        if action == "publish":
            if not form:
                errors.append("ابتدا فرم را ذخیره و برای تأیید علمی ارسال کنید.")
            else:
                candidate_matches_approved_snapshot = (
                    title == form.title
                    and slug == form.slug
                    and request.form.get("description", "").strip()[:500] == form.description
                    and form_type == form.form_type
                    and (request.form.get("use_case", "general").strip()[:80] or "general") == form.use_case
                    and fields == form.fields
                    and settings == form.settings
                    and scoring == form.scoring
                )
                if not candidate_matches_approved_snapshot:
                    errors.append(
                        "محتوا پس از تأیید تغییر کرده است؛ ابتدا نسخه جدید را ذخیره و دوباره برای تأیید علمی ارسال کنید."
                    )
                elif not approved_for_current_snapshot("form", form):
                    errors.append("انتشار فقط پس از تأیید علمی مستقل همین نسخه و اثرانگشت ممکن است.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not form:
                form = DynamicForm(created_by=current_user.id, version=1)
                db.session.add(form)
            elif form.status in {"published", "archived"} and action != "publish":
                form.version += 1
                form.published_at = None
                form.archived_at = None
            form.title = title
            form.slug = slug
            form.description = request.form.get("description", "").strip()[:500]
            form.form_type = form_type
            form.use_case = request.form.get("use_case", "general").strip()[:80] or "general"
            form.schema_json = json.dumps(fields, ensure_ascii=False)
            form.settings_json = json.dumps(settings, ensure_ascii=False)
            form.scoring_json = json.dumps(scoring, ensure_ascii=False)
            if action == "request_review":
                form.status = "review"
            elif action == "publish":
                form.status = "published"
                form.published_at = utcnow()
            else:
                form.status = "draft"
            db.session.flush()
            save_form_snapshot(form)
            if action == "request_review":
                create_scientific_form_review(form)
            db.session.commit()
            message = {
                "save_draft": f"پیش‌نویس نسخه {form.version} ذخیره شد.",
                "request_review": f"نسخه {form.version} برای تأیید علمی ارسال شد.",
                "publish": f"نسخه {form.version} فرم منتشر شد.",
            }[action]
            flash(message, "success")
            return redirect(url_for("admin.form_editor", form_id=form.id))

    return render_template(
        "admin/form_builder.html",
        selected=form,
        catalog=field_catalog_payload(),
        form_types=FORM_TYPES,
        ai_contract=AI_CONTRACT,
        approved=approved_for_current_snapshot("form", form) if form else None,
    )


@bp.post("/forms/import")
@login_required
@admin_required
def form_import_json():
    try:
        payload = json.loads(request.form.get("json_payload", ""))
    except ValueError as exc:
        flash(f"$: JSON معتبر نیست؛ {exc.msg} در خط {exc.lineno}.", "danger")
        return redirect(url_for("admin.form_builder"))
    normalized, errors = validate_ai_contract(payload)
    if errors:
        for error in errors[:30]:
            flash(error, "danger")
        if len(errors) > 30:
            flash(f"{len(errors) - 30} خطای دیگر نیز وجود دارد.", "danger")
        return redirect(url_for("admin.form_builder"))
    form = DynamicForm(
        title=normalized["title"],
        slug=unique_form_slug(normalized["slug"]),
        description=normalized["description"],
        form_type=normalized["form_type"],
        use_case=normalized["use_case"],
        version=1,
        status="draft",
        schema_json=json.dumps(normalized["fields"], ensure_ascii=False),
        settings_json=json.dumps(normalized["settings"], ensure_ascii=False),
        scoring_json=json.dumps(normalized["scoring"], ensure_ascii=False),
        created_by=current_user.id,
    )
    db.session.add(form)
    db.session.flush()
    save_form_snapshot(form)
    db.session.commit()
    flash("JSON معتبر بود و فقط به‌صورت Draft ساخته شد؛ برای انتشار باید بازبینی شود.", "success")
    return redirect(url_for("admin.form_editor", form_id=form.id))


@bp.get("/forms/<int:form_id>/export.json")
@login_required
@admin_required
def form_export_json(form_id):
    form = db.get_or_404(DynamicForm, form_id)
    body = json.dumps(form_to_ai_contract(form), ensure_ascii=False, indent=2)
    return Response(
        body,
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{form.slug}-v{form.version}.json"'},
    )


@bp.post("/forms/<int:form_id>/assignments")
@login_required
@admin_required
def form_assignment(form_id):
    form = db.get_or_404(DynamicForm, form_id)
    if form.status != "published":
        flash("فقط فرم منتشرشده قابل تخصیص است.", "danger")
        return redirect(url_for("admin.form_responses", form_id=form.id))
    target_type = request.form.get("target_type", "role")
    if target_type not in {"role", "user", "child", "course", "journey"}:
        abort(400)
    target_id = request.form.get("target_id", type=int) if target_type in {"user", "child"} else None
    target_ref = request.form.get("target_ref", "").strip()[:120]
    if target_type == "role":
        target_ref = target_ref if target_ref in {
            "parent", "child", "organization", "admin", "reviewer"
        } else "parent"
    if target_type == "user" and not db.session.get(User, target_id):
        flash("کاربر هدف پیدا نشد.", "danger")
    elif target_type == "child" and not db.session.get(Child, target_id):
        flash("فرزند هدف پیدا نشد.", "danger")
    elif target_type in {"course", "journey"} and not target_ref:
        flash("شناسه دوره یا مرحله مسیر را وارد کنید.", "danger")
    elif target_type == "course" and (
        not target_ref.isdigit()
        or not Course.query.filter_by(id=int(target_ref), status="published").first()
    ):
        flash("دوره منتشرشده معتبر پیدا نشد.", "danger")
    else:
        assignment = FormAssignment(
            form_id=form.id,
            target_type=target_type,
            target_id=target_id,
            target_ref=target_ref,
            title=request.form.get("title", "").strip()[:180] or form.title,
            status="active",
            is_required=request.form.get("is_required") == "1",
            opens_at=parse_datetime_local(request.form.get("opens_at")),
            due_at=parse_datetime_local(request.form.get("due_at")),
            created_by=current_user.id,
        )
        db.session.add(assignment)
        if target_type == "role":
            sync_role_form_to_profile(
                form,
                target_ref,
                current_user.id,
                request.form.get("title", "").strip() or form.title,
            )
        db.session.commit()
        flash("فرم به مخاطب انتخاب‌شده تخصیص یافت.", "success")
    return redirect(url_for("admin.form_responses", form_id=form.id))


@bp.post("/forms/<int:form_id>/media")
@login_required
@admin_required
def form_media_upload(form_id):
    form = db.get_or_404(DynamicForm, form_id)
    upload = request.files.get("media")
    field_key = request.form.get("field_key", "").strip()[:80]
    kind = request.form.get("kind", "file")
    field = next((item for item in form.fields if item.get("key") == field_key), None)
    if not upload or not upload.filename:
        flash("فایل انتخاب نشده است.", "danger")
    else:
        if not field:
            field = {"type": {"image": "image_answer", "video": "video_answer", "audio": "audio_answer"}.get(kind, "file"), "validation": {"max_size_mb": 8}}
        upload.stream.seek(0, os.SEEK_END)
        size_bytes = upload.stream.tell()
        upload.stream.seek(0)
        header_bytes = upload.stream.read(1024 * 1024)
        upload.stream.seek(0)
        allowed, result = allowed_upload(
            field, upload.filename, upload.mimetype, size_bytes, header_bytes
        )
        if not allowed:
            flash(result, "danger")
        else:
            clean, scan_result = malware_scan_sample(header_bytes)
            if not clean:
                flash(scan_result, "danger")
                return redirect(url_for("admin.form_editor", form_id=form.id))
            storage_name = storage_filename(result)
            folder = os.path.join(current_app.instance_path, "form_uploads")
            os.makedirs(folder, mode=0o700, exist_ok=True)
            upload.save(os.path.join(folder, storage_name))
            asset = FormMediaAsset(
                form_id=form.id,
                owner_id=current_user.id,
                field_key=field_key,
                kind=kind,
                original_name=upload.filename[:240],
                storage_name=storage_name,
                mime_type=upload.mimetype[:120],
                size_bytes=size_bytes,
            )
            db.session.add(asset)
            db.session.commit()
            flash(f"رسانه خصوصی ذخیره شد؛ شناسه دارایی {asset.id}.", "success")
    return redirect(url_for("admin.form_editor", form_id=form.id))


@bp.get("/forms/media/<int:asset_id>")
@login_required
def form_media(asset_id):
    asset = db.get_or_404(FormMediaAsset, asset_id)
    allowed = current_user.is_staff or asset.owner_id == current_user.id
    if not allowed and current_user.role == "parent":
        child_ids = {child.id for child in current_user.children}
        child_ids.update(
            link.child_id
            for link in GuardianRelationship.query.filter_by(
                guardian_id=current_user.id, status="active", access_level="full"
            ).all()
        )
        allowed = any(
            assignment.status == "active" and (
                assignment.target_type == "role" and assignment.target_ref == "parent"
                or assignment.target_type == "user" and assignment.target_id == current_user.id
                or assignment.target_type == "child" and assignment.target_id in child_ids
            )
            for assignment in asset.form.assignments
        )
    if not allowed:
        abort(404)
    folder = os.path.join(current_app.instance_path, "form_uploads")
    return send_from_directory(
        folder,
        asset.storage_name,
        mimetype=asset.mime_type,
        as_attachment=request.args.get("download") == "1",
        download_name=asset.original_name,
        max_age=0,
    )


@bp.get("/forms/<int:form_id>/responses")
@login_required
@admin_required
def form_responses(form_id):
    form = db.get_or_404(DynamicForm, form_id)
    response_pagination = FormResponse.query.filter_by(form_id=form.id).order_by(
        FormResponse.updated_at.desc()
    ).paginate(
        page=max(1, request.args.get("page", 1, type=int)),
        per_page=current_app.config["ADMIN_PAGE_SIZE"], error_out=False,
    )
    return render_template(
        "admin/form_responses.html",
        form=form,
        responses=response_pagination.items,
        response_pagination=response_pagination,
        assignments=FormAssignment.query.filter_by(form_id=form.id).order_by(FormAssignment.created_at.desc()).all(),
        parents=User.query.filter_by(role="parent").order_by(User.full_name).all(),
        children=Child.query.order_by(Child.name).all(),
    )


@bp.get("/contracts/<int:contract_id>/growth-report.csv")
@login_required
@admin_required
def contract_growth_report(contract_id):
    contract = db.get_or_404(OrganizationContract, contract_id)
    report = contract_aggregate_report(contract)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["گزارش تجمیعی قرارداد", contract.contract_no])
    writer.writerow(["شاخص", "مقدار"])
    for key, label in (
        ("parents", "خانواده/والد"), ("children", "فرزند"),
        ("enrollments", "ثبت‌نام دوره"), ("completed", "دوره تکمیل‌شده"),
        ("completion_percent", "درصد تکمیل"), ("average_progress", "میانگین پیشرفت"),
        ("service_usage", "مصرف خدمت"),
    ):
        writer.writerow([label, report[key]])
    writer.writerow(["حریم خصوصی", report["impact"]["message"]])
    if report["impact"]["available"]:
        writer.writerow(["تعداد پاسخ تجمیعی", report["impact"]["response_count"]])
        writer.writerow(["میانگین امتیاز تجمیعی", report["impact"]["average_score"]])
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=contract-{contract.id}-growth.csv"},
    )


@bp.get("/forms/<int:form_id>/responses.csv")
@login_required
@admin_required
def form_responses_export(form_id):
    form = db.get_or_404(DynamicForm, form_id)
    fields = [field for field in form.fields if field.get("type") not in {"content", "section", "page"}]
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["response_id", "status", "user", "mobile", "child", "version", "score", *[field.get("label") for field in fields]])
    export_limit = current_app.config["EXPORT_ROW_LIMIT"]
    for response in FormResponse.query.filter_by(form_id=form.id).order_by(FormResponse.id).limit(export_limit).all():
        writer.writerow([
            response.id,
            response.status,
            response.user.full_name,
            response.user.mobile,
            response.child.name if response.child else "",
            response.form_version,
            response.score_total if response.score_total is not None else "",
            *[
                " | ".join(map(str, response.answers.get(field.get("key"), [])))
                if isinstance(response.answers.get(field.get("key")), list)
                else response.answers.get(field.get("key"), "")
                for field in fields
            ],
        ])
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{form.slug}-responses.csv"',
            "X-Export-Row-Limit": str(export_limit),
        },
    )

