import csv
import io
import json
import re
from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    Child,
    DecisionNode,
    DynamicForm,
    Organization,
    PaymentAllocation,
    ParentingAssessment,
    ProjectAuditLog,
    ProjectMembership,
    ScenarioLevel,
    ScenarioTopic,
    SponsoredProject,
    User,
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
    }
    recent_users = User.query.order_by(User.created_at.desc()).limit(6).all()
    return render_template("admin/dashboard.html", stats=stats, recent_users=recent_users)


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

