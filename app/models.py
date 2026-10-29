import json
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

