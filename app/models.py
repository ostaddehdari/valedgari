import json
import hashlib
from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(11), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="parent", index=True)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    children = db.relationship(
        "Child", backref="parent", lazy=True, cascade="all, delete-orphan"
    )
    project_memberships = db.relationship(
        "ProjectMembership", backref="parent", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def is_active(self):
        return self.is_active_account

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_reviewer(self):
        return self.role == "reviewer"

    @property
    def is_staff(self):
        return self.role in {"admin", "reviewer"}

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Child(db.Model):
    __tablename__ = "children"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    birth_year = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False, default="unspecified")
    notes = db.Column(db.String(400), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ParentingAssessment(db.Model):
    __tablename__ = "parenting_assessments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    level = db.Column(db.String(60), nullable=False)
    answers_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    child = db.relationship("Child")


class SkillModule(db.Model):
    __tablename__ = "skill_modules"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(60), nullable=False, default="fa-seedling")
    duration = db.Column(db.Integer, nullable=False, default=10)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_published = db.Column(db.Boolean, nullable=False, default=True)


class SkillProgress(db.Model):
    __tablename__ = "skill_progress"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey("skill_modules.id"), nullable=False)
    percent = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    module = db.relationship("SkillModule")
    __table_args__ = (db.UniqueConstraint("user_id", "child_id", "module_id"),)


class SkillDomain(db.Model):
    __tablename__ = "skill_domains"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.String(700), nullable=False, default="")
    icon = db.Column(db.String(60), nullable=False, default="fa-seedling")
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    memberships = db.relationship(
        "SkillDomainMembership",
        backref="domain",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="SkillDomainMembership.sort_order",
    )


class SkillDomainMembership(db.Model):
    __tablename__ = "skill_domain_memberships"
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(
        db.Integer, db.ForeignKey("skill_domains.id"), nullable=False, index=True
    )
    module_id = db.Column(
        db.Integer, db.ForeignKey("skill_modules.id"), nullable=False, index=True
    )
    learning_level = db.Column(db.String(30), nullable=False, default="foundation")
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    module = db.relationship("SkillModule")
    __table_args__ = (db.UniqueConstraint("domain_id", "module_id"),)


class MicroLesson(db.Model):
    __tablename__ = "micro_lessons"
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(
        db.Integer, db.ForeignKey("skill_domains.id"), nullable=False, index=True
    )
    module_id = db.Column(
        db.Integer, db.ForeignKey("skill_modules.id"), nullable=False, index=True
    )
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    objective = db.Column(db.String(500), nullable=False, default="")
    body = db.Column(db.Text, nullable=False)
    practice = db.Column(db.String(700), nullable=False, default="")
    common_pitfall = db.Column(db.String(700), nullable=False, default="")
    duration = db.Column(db.Integer, nullable=False, default=7)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    domain = db.relationship("SkillDomain")
    module = db.relationship("SkillModule")


class WeeklyPlan(db.Model):
    __tablename__ = "weekly_plans"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, index=True
    )
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    goal_title = db.Column(db.String(220), nullable=False)
    rationale = db.Column(db.String(1000), nullable=False, default="")
    starts_on = db.Column(db.Date, nullable=False, default=date.today)
    ends_on = db.Column(db.Date, nullable=False)
    source_context_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    child = db.relationship("Child")
    topic = db.relationship("ScenarioTopic")
    actions = db.relationship(
        "DailyAction",
        backref="plan",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="DailyAction.day_index",
    )
    review = db.relationship(
        "PlanReview", backref="plan", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def source_context(self):
        try:
            value = json.loads(self.source_context_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def completed_count(self):
        return sum(item.status == "completed" for item in self.actions)

    @property
    def progress_percent(self):
        return round(self.completed_count / len(self.actions) * 100) if self.actions else 0

    @property
    def current_action(self):
        return next((item for item in self.actions if item.status != "completed"), None)


class DailyAction(db.Model):
    __tablename__ = "daily_actions"
    id = db.Column(db.Integer, primary_key=True)
    weekly_plan_id = db.Column(
        db.Integer, db.ForeignKey("weekly_plans.id"), nullable=False, index=True
    )
    day_index = db.Column(db.Integer, nullable=False)
    action_type = db.Column(db.String(30), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    why_text = db.Column(db.String(700), nullable=False, default="")
    duration = db.Column(db.Integer, nullable=False, default=5)
    lesson_id = db.Column(db.Integer, db.ForeignKey("micro_lessons.id"), nullable=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("scenario_topics.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    parent_note = db.Column(db.String(1200), nullable=False, default="")
    confidence = db.Column(db.Integer, nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    lesson = db.relationship("MicroLesson")
    topic = db.relationship("ScenarioTopic")
    __table_args__ = (db.UniqueConstraint("weekly_plan_id", "day_index"),)


class PlanReview(db.Model):
    __tablename__ = "plan_reviews"
    id = db.Column(db.Integer, primary_key=True)
    weekly_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("weekly_plans.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    rating = db.Column(db.Integer, nullable=False)
    relationship_change = db.Column(db.String(30), nullable=False)
    confidence = db.Column(db.Integer, nullable=False)
    what_worked = db.Column(db.String(1200), nullable=False, default="")
    next_focus = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class SafetyProtocol(db.Model):
    __tablename__ = "safety_protocols"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    trigger_keywords_json = db.Column(db.Text, nullable=False, default="[]")
    response_title = db.Column(db.String(220), nullable=False)
    response_text = db.Column(db.Text, nullable=False)
    immediate_steps_json = db.Column(db.Text, nullable=False, default="[]")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    priority = db.Column(db.Integer, nullable=False, default=100)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def trigger_keywords(self):
        try:
            value = json.loads(self.trigger_keywords_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def immediate_steps(self):
        try:
            value = json.loads(self.immediate_steps_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []


class AssistantConversation(db.Model):
    __tablename__ = "assistant_conversations"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False, default="گفت‌وگوی تازه")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    child = db.relationship("Child")
    messages = db.relationship(
        "AssistantMessage",
        backref="conversation",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="AssistantMessage.created_at",
    )


class AssistantMessage(db.Model):
    __tablename__ = "assistant_messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("assistant_conversations.id"), nullable=False, index=True
    )
    role = db.Column(db.String(20), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    decision_type = db.Column(db.String(30), nullable=False, default="user", index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("scenario_topics.id"), nullable=True)
    sources_json = db.Column(db.Text, nullable=False, default="[]")
    context_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    topic = db.relationship("ScenarioTopic")
    feedback = db.relationship(
        "AssistantFeedback", backref="message", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def sources(self):
        try:
            value = json.loads(self.sources_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def context(self):
        try:
            value = json.loads(self.context_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class AssistantFeedback(db.Model):
    __tablename__ = "assistant_feedback"
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer,
        db.ForeignKey("assistant_messages.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    helpful = db.Column(db.Boolean, nullable=False)
    note = db.Column(db.String(700), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ScenarioTopic(db.Model):
    __tablename__ = "scenario_topics"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(60), nullable=False, default="fa-comments")
    is_published = db.Column(db.Boolean, nullable=False, default=True)

    levels = db.relationship(
        "ScenarioLevel", backref="topic", lazy=True, cascade="all, delete-orphan"
    )


class ScenarioLevel(db.Model):
    __tablename__ = "scenario_levels"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False)
    level = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(60), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    recommended_action = db.Column(db.Text, nullable=False, default="")
    wrong_action = db.Column(db.Text, nullable=False, default="")
    consequence = db.Column(db.Text, nullable=False, default="")

    nodes = db.relationship(
        "DecisionNode", backref="scenario_level", lazy=True, cascade="all, delete-orphan"
    )
    __table_args__ = (db.UniqueConstraint("topic_id", "level"),)


class DecisionNode(db.Model):
    __tablename__ = "decision_nodes"
    id = db.Column(db.Integer, primary_key=True)
    level_id = db.Column(db.Integer, db.ForeignKey("scenario_levels.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("decision_nodes.id"), nullable=True)
    option_label = db.Column(db.String(160), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_recommended = db.Column(db.Boolean, nullable=False, default=False)
    consequence = db.Column(db.Text, nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class ScenarioAttempt(db.Model):
    __tablename__ = "scenario_attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False)
    level_id = db.Column(db.Integer, db.ForeignKey("scenario_levels.id"), nullable=False)
    selected_node_id = db.Column(db.Integer, db.ForeignKey("decision_nodes.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class DynamicForm(db.Model):
    __tablename__ = "dynamic_forms"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft")
    schema_json = db.Column(db.Text, nullable=False, default="[]")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def fields(self):
        try:
            return json.loads(self.schema_json)
        except (TypeError, ValueError):
            return []


class FormResponse(db.Model):
    __tablename__ = "form_responses"
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=True)
    answers_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    legal_name = db.Column(db.String(200), nullable=False, default="")
    registration_no = db.Column(db.String(80), nullable=False, default="")
    contact_name = db.Column(db.String(120), nullable=False, default="")
    contact_mobile = db.Column(db.String(20), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    projects = db.relationship(
        "SponsoredProject", backref="organization", lazy=True, cascade="all, delete-orphan"
    )


class SponsoredProject(db.Model):
    __tablename__ = "sponsored_projects"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    name = db.Column(db.String(180), nullable=False)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    description = db.Column(db.String(700), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    pricing_model = db.Column(db.String(20), nullable=False, default="percent")
    service_price_toman = db.Column(db.Integer, nullable=False, default=0)
    organization_share_percent = db.Column(db.Integer, nullable=False, default=70)
    organization_fixed_toman = db.Column(db.Integer, nullable=False, default=0)
    subsidy_cap_per_parent_toman = db.Column(db.Integer, nullable=False, default=0)
    total_budget_toman = db.Column(db.Integer, nullable=False, default=0)
    capacity = db.Column(db.Integer, nullable=False, default=0)
    starts_on = db.Column(db.Date, nullable=True)
    ends_on = db.Column(db.Date, nullable=True)
    eligible_services_json = db.Column(db.Text, nullable=False, default="[]")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    memberships = db.relationship(
        "ProjectMembership", backref="project", lazy=True, cascade="all, delete-orphan"
    )
    audit_logs = db.relationship(
        "ProjectAuditLog", backref="project", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def eligible_services(self):
        try:
            value = json.loads(self.eligible_services_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def active_member_count(self):
        return sum(item.status in {"active", "pending"} for item in self.memberships)

    @property
    def committed_subsidy_toman(self):
        return sum(
            allocation.organization_amount_toman
            for membership in self.memberships
            for allocation in membership.allocations
            if allocation.status not in {"cancelled", "refunded"}
        )

    @property
    def remaining_budget_toman(self):
        if not self.total_budget_toman:
            return None
        return max(0, self.total_budget_toman - self.committed_subsidy_toman)

    def calculate_split(self, amount_toman=None):
        gross = max(0, int(amount_toman or self.service_price_toman or 0))
        if self.pricing_model == "fixed":
            organization_amount = self.organization_fixed_toman
        else:
            organization_amount = round(gross * self.organization_share_percent / 100)
        if self.subsidy_cap_per_parent_toman:
            organization_amount = min(organization_amount, self.subsidy_cap_per_parent_toman)
        organization_amount = min(gross, max(0, organization_amount))
        return gross, organization_amount, gross - organization_amount

    def acceptance_problem(self, today=None):
        today = today or date.today()
        if self.status != "active":
            return "این پروژه در حال حاضر فعال نیست."
        if self.organization.status != "active":
            return "حمایت این سازمان در حال حاضر فعال نیست."
        if self.starts_on and today < self.starts_on:
            return "زمان استفاده از این پروژه هنوز شروع نشده است."
        if self.ends_on and today > self.ends_on:
            return "اعتبار این پروژه به پایان رسیده است."
        if self.capacity and self.active_member_count >= self.capacity:
            return "ظرفیت این پروژه تکمیل شده است."
        _gross, subsidy, _parent = self.calculate_split()
        if self.remaining_budget_toman is not None and self.remaining_budget_toman < subsidy:
            return "بودجه باقی‌مانده پروژه برای عضویت جدید کافی نیست."
        return None


class ProjectMembership(db.Model):
    __tablename__ = "project_memberships"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("sponsored_projects.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    source = db.Column(db.String(40), nullable=False, default="support_code")
    joined_code = db.Column(db.String(32), nullable=False)
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)

    allocations = db.relationship(
        "PaymentAllocation", backref="membership", lazy=True, cascade="all, delete-orphan"
    )
    __table_args__ = (db.UniqueConstraint("project_id", "user_id"),)


class PaymentAllocation(db.Model):
    __tablename__ = "payment_allocations"
    id = db.Column(db.Integer, primary_key=True)
    membership_id = db.Column(
        db.Integer, db.ForeignKey("project_memberships.id"), nullable=False, index=True
    )
    service_name = db.Column(db.String(180), nullable=False, default="دسترسی والدیار")
    gross_amount_toman = db.Column(db.Integer, nullable=False)
    organization_amount_toman = db.Column(db.Integer, nullable=False)
    parent_amount_toman = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="reserved", index=True)
    note = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    parent_paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    organization_settled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)


class ProjectAuditLog(db.Model):
    __tablename__ = "project_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("sponsored_projects.id"), nullable=False, index=True
    )
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False, index=True)
    details_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def details(self):
        try:
            return json.loads(self.details_json or "{}")
        except (TypeError, ValueError):
            return {}


class AssessmentInstrument(db.Model):
    __tablename__ = "assessment_instruments"
    id = db.Column(db.Integer, primary_key=True)
    framework_slug = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    version = db.Column(db.String(40), nullable=False, default="draft-1")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    source_reference = db.Column(db.String(500), nullable=False, default="")
    license_note = db.Column(db.String(500), nullable=False, default="")
    scoring_schema_json = db.Column(db.Text, nullable=False, default="{}")
    disclaimer = db.Column(db.String(700), nullable=False, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    questions = db.relationship(
        "AssessmentQuestion",
        backref="instrument",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="AssessmentQuestion.sort_order",
    )
    results = db.relationship(
        "ParentingStyleAssessment",
        backref="instrument",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def scoring_schema(self):
        try:
            value = json.loads(self.scoring_schema_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def is_published(self):
        return self.status == "published"


class AssessmentQuestion(db.Model):
    __tablename__ = "assessment_questions"
    id = db.Column(db.Integer, primary_key=True)
    instrument_id = db.Column(
        db.Integer, db.ForeignKey("assessment_instruments.id"), nullable=False, index=True
    )
    code = db.Column(db.String(60), nullable=False)
    text = db.Column(db.String(700), nullable=False)
    dimension = db.Column(db.String(80), nullable=False, index=True)
    weight = db.Column(db.Float, nullable=False, default=1.0)
    reverse_score = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (db.UniqueConstraint("instrument_id", "code"),)


class ParentingStyleAssessment(db.Model):
    __tablename__ = "parenting_style_assessments"
    id = db.Column(db.Integer, primary_key=True)
    instrument_id = db.Column(
        db.Integer, db.ForeignKey("assessment_instruments.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    answers_json = db.Column(db.Text, nullable=False)
    scores_json = db.Column(db.Text, nullable=False)
    dominant_style = db.Column(db.String(80), nullable=False)
    interpretation = db.Column(db.String(700), nullable=False, default="")
    instrument_version = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    child = db.relationship("Child")

    @property
    def scores(self):
        try:
            return json.loads(self.scores_json or "{}")
        except (TypeError, ValueError):
            return {}


class ChildProfileSnapshot(db.Model):
    __tablename__ = "child_profile_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    profile_type = db.Column(db.String(30), nullable=False, index=True)
    version_no = db.Column(db.Integer, nullable=False, default=1)
    answers_json = db.Column(db.Text, nullable=False)
    summary_json = db.Column(db.Text, nullable=False, default="{}")
    source_version = db.Column(db.String(40), nullable=False, default="internal-1")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    child = db.relationship("Child")
    __table_args__ = (
        db.UniqueConstraint("child_id", "profile_type", "version_no"),
    )

    @property
    def answers(self):
        try:
            return json.loads(self.answers_json or "{}")
        except (TypeError, ValueError):
            return {}

    @property
    def summary(self):
        try:
            return json.loads(self.summary_json or "{}")
        except (TypeError, ValueError):
            return {}


class PersonalizationRule(db.Model):
    __tablename__ = "personalization_rules"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, index=True
    )
    name = db.Column(db.String(180), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    priority = db.Column(db.Integer, nullable=False, default=50, index=True)
    min_severity = db.Column(db.Integer, nullable=False, default=1)
    max_severity = db.Column(db.Integer, nullable=False, default=5)
    conditions_json = db.Column(db.Text, nullable=False, default="{}")
    recommendation_title = db.Column(db.String(220), nullable=False)
    recommendation_text = db.Column(db.Text, nullable=False)
    reason_template = db.Column(db.String(700), nullable=False, default="")
    avoid_text = db.Column(db.Text, nullable=False, default="")
    home_action = db.Column(db.String(700), nullable=False, default="")
    next_step_text = db.Column(db.String(700), nullable=False, default="")
    skill_module_id = db.Column(
        db.Integer, db.ForeignKey("skill_modules.id"), nullable=True, index=True
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    topic = db.relationship("ScenarioTopic")
    skill = db.relationship("SkillModule")

    @property
    def conditions(self):
        try:
            value = json.loads(self.conditions_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def is_published(self):
        return self.status == "published"


class RecommendationRun(db.Model):
    __tablename__ = "recommendation_runs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, index=True
    )
    level_id = db.Column(
        db.Integer, db.ForeignKey("scenario_levels.id"), nullable=False, index=True
    )
    rule_id = db.Column(
        db.Integer, db.ForeignKey("personalization_rules.id"), nullable=True, index=True
    )
    rule_version = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="planned", index=True)
    context_json = db.Column(db.Text, nullable=False, default="{}")
    title = db.Column(db.String(220), nullable=False)
    action_text = db.Column(db.Text, nullable=False)
    reasons_json = db.Column(db.Text, nullable=False, default="[]")
    avoid_text = db.Column(db.Text, nullable=False, default="")
    home_action = db.Column(db.String(700), nullable=False, default="")
    next_step_text = db.Column(db.String(700), nullable=False, default="")
    skill_module_id = db.Column(db.Integer, db.ForeignKey("skill_modules.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    child = db.relationship("Child")
    topic = db.relationship("ScenarioTopic")
    level = db.relationship("ScenarioLevel")
    rule = db.relationship("PersonalizationRule")
    skill = db.relationship("SkillModule")
    outcome = db.relationship(
        "HomeActionOutcome",
        backref="recommendation",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def context(self):
        try:
            return json.loads(self.context_json or "{}")
        except (TypeError, ValueError):
            return {}

    @property
    def reasons(self):
        try:
            value = json.loads(self.reasons_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []


class HomeActionOutcome(db.Model):
    __tablename__ = "home_action_outcomes"
    id = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(
        db.Integer,
        db.ForeignKey("recommendation_runs.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    outcome = db.Column(db.String(20), nullable=False, index=True)
    child_response = db.Column(db.String(30), nullable=False, default="not_recorded")
    helpfulness = db.Column(db.Integer, nullable=False, default=3)
    parent_note = db.Column(db.String(1200), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ConsentRecord(db.Model):
    """Versioned evidence of the parent's privacy/child-data consent."""

    __tablename__ = "consent_records"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    policy_version = db.Column(db.String(30), nullable=False, index=True)
    purpose = db.Column(db.String(80), nullable=False, default="parenting_guidance")
    accepted = db.Column(db.Boolean, nullable=False, default=True)
    source = db.Column(db.String(40), nullable=False, default="registration")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User")


class DataDeletionRequest(db.Model):
    """Auditable parent request for deleting one child's records."""

    __tablename__ = "data_deletion_requests"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, nullable=False, index=True)
    child_name_snapshot = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    reason = db.Column(db.String(700), nullable=False, default="")
    requested_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    processing_note = db.Column(db.String(700), nullable=False, default="")

    parent = db.relationship("User", foreign_keys=[user_id])
    processor = db.relationship("User", foreign_keys=[processed_by])


class ScientificReview(db.Model):
    """Independent, version-bound approval for publishable scientific content."""

    __tablename__ = "scientific_reviews"
    id = db.Column(db.Integer, primary_key=True)
    resource_type = db.Column(db.String(40), nullable=False, index=True)
    resource_id = db.Column(db.Integer, nullable=False, index=True)
    resource_title = db.Column(db.String(220), nullable=False)
    resource_version = db.Column(db.String(40), nullable=False)
    snapshot_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requested_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewer_note = db.Column(db.String(1000), nullable=False, default="")

    requester = db.relationship("User", foreign_keys=[requested_by])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    __table_args__ = (
        db.UniqueConstraint(
            "resource_type", "resource_id", "resource_version", "snapshot_hash"
        ),
    )

    @staticmethod
    def fingerprint(payload):
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OperationalEvent(db.Model):
    """Small internal audit stream for backup/restore/retention operations."""

    __tablename__ = "operational_events"
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    details_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def details(self):
        try:
            value = json.loads(self.details_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

