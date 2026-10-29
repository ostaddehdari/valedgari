import json
import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    Child,
    DecisionNode,
    DynamicForm,
    ParentingAssessment,
    ScenarioLevel,
    ScenarioTopic,
    User,
)
from .security import admin_required


bp = Blueprint("admin", __name__, url_prefix="/admin")


def make_slug(value):
    value = (value or "form").strip().lower()
    value = re.sub(r"[^a-z0-9\-]+", "-", value).strip("-")
    return value or f"form-{DynamicForm.query.count() + 1}"


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
    }
    recent_users = User.query.order_by(User.created_at.desc()).limit(6).all()
    return render_template("admin/dashboard.html", stats=stats, recent_users=recent_users)


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

