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
    national_id = db.Column(db.String(10), nullable=False, default="", index=True)
    email = db.Column(db.String(160), nullable=False, default="")
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
    guardian_links = db.relationship(
        "GuardianRelationship",
        foreign_keys="GuardianRelationship.guardian_id",
        backref="guardian",
        lazy=True,
        cascade="all, delete-orphan",
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
    national_id = db.Column(db.String(10), nullable=False, default="", index=True)
    birth_year = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False, default="unspecified")
    notes = db.Column(db.String(400), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    guardian_links = db.relationship(
        "GuardianRelationship",
        foreign_keys="GuardianRelationship.child_id",
        backref="child",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="GuardianRelationship.created_at",
    )


class GuardianRelationship(db.Model):
    __tablename__ = "guardian_relationships"
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    guardian_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    relationship_type = db.Column(db.String(20), nullable=False, default="guardian", index=True)
    access_level = db.Column(db.String(20), nullable=False, default="full", index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    invited_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (db.UniqueConstraint("child_id", "guardian_id"),)


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
    code = db.Column(db.String(30), nullable=False, default="", index=True)
    level = db.Column(db.String(30), nullable=False, default="foundation", index=True)
    style_tags_json = db.Column(db.Text, nullable=False, default="[]")
    scenario_ids_json = db.Column(db.Text, nullable=False, default="[]")
    prerequisite_ids_json = db.Column(db.Text, nullable=False, default="[]")

    @property
    def style_tags(self):
        try:
            value = json.loads(self.style_tags_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def scenario_ids(self):
        try:
            return [int(value) for value in json.loads(self.scenario_ids_json or "[]")]
        except (TypeError, ValueError):
            return []

    @property
    def prerequisite_ids(self):
        try:
            return [int(value) for value in json.loads(self.prerequisite_ids_json or "[]")]
        except (TypeError, ValueError):
            return []


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


class Course(db.Model):
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    subtitle = db.Column(db.String(240), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    instructor_name = db.Column(db.String(140), nullable=False, default="تیم علمی والدیار")
    cover_url = db.Column(db.String(700), nullable=False, default="")
    intro_video_url = db.Column(db.String(700), nullable=False, default="")
    level = db.Column(db.String(30), nullable=False, default="foundation", index=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    price_toman = db.Column(db.Integer, nullable=False, default=0)
    style_tags_json = db.Column(db.Text, nullable=False, default="[]")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True)

    chapters = db.relationship(
        "CourseChapter", backref="course", lazy=True, cascade="all, delete-orphan",
        order_by="CourseChapter.sort_order",
    )
    skill_links = db.relationship(
        "CourseSkillMembership", backref="course", lazy=True, cascade="all, delete-orphan"
    )
    topic_links = db.relationship(
        "CourseTopicMembership", backref="course", lazy=True, cascade="all, delete-orphan"
    )
    enrollments = db.relationship(
        "CourseEnrollment", backref="course", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def is_free(self):
        return self.price_toman <= 0

    @property
    def style_tags(self):
        try:
            value = json.loads(self.style_tags_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def skills(self):
        return [link.skill for link in self.skill_links]

    @property
    def topics(self):
        return [link.topic for link in self.topic_links]

    @property
    def active_units(self):
        return [
            unit for chapter in self.chapters if chapter.status == "active"
            for unit in chapter.units if unit.status == "active"
        ]


class CourseSkillMembership(db.Model):
    __tablename__ = "course_skill_memberships"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill_modules.id"), nullable=False, index=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    skill = db.relationship("SkillModule")
    __table_args__ = (db.UniqueConstraint("course_id", "skill_id"),)


class CourseTopicMembership(db.Model):
    __tablename__ = "course_topic_memberships"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, index=True)
    topic = db.relationship("ScenarioTopic")
    __table_args__ = (db.UniqueConstraint("course_id", "topic_id"),)


class CourseAssessmentBinding(db.Model):
    """Connects a published form to a course's non-diagnostic pre/post measurement."""

    __tablename__ = "course_assessment_bindings"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False, index=True)
    assessment_type = db.Column(db.String(10), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill_modules.id"), nullable=True, index=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    course = db.relationship("Course", backref="assessment_bindings")
    form = db.relationship("DynamicForm")
    skill = db.relationship("SkillModule")
    __table_args__ = (
        db.UniqueConstraint("course_id", "assessment_type"),
        db.CheckConstraint(
            "assessment_type IN ('pre', 'post')", name="ck_course_assessment_type"
        ),
    )


class CourseChapter(db.Model):
    __tablename__ = "course_chapters"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.String(700), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    units = db.relationship(
        "CourseUnit", backref="chapter", lazy=True, cascade="all, delete-orphan",
        order_by="CourseUnit.sort_order",
    )


class CourseUnit(db.Model):
    __tablename__ = "course_units"
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("course_chapters.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    unit_type = db.Column(db.String(30), nullable=False, default="text", index=True)
    body = db.Column(db.Text, nullable=False, default="")
    source_url = db.Column(db.String(700), nullable=False, default="")
    duration_minutes = db.Column(db.Integer, nullable=False, default=5)
    is_preview = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=True, index=True)
    form = db.relationship("DynamicForm")


class CourseEnrollment(db.Model):
    __tablename__ = "course_enrollments"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=True, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("course_orders.id"), nullable=True, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    source = db.Column(db.String(30), nullable=False, default="free")
    price_snapshot_toman = db.Column(db.Integer, nullable=False, default=0)
    enrolled_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    user = db.relationship("User")
    child = db.relationship("Child")
    order = db.relationship("CourseOrder", foreign_keys=[order_id])
    progresses = db.relationship(
        "CourseUnitProgress", backref="enrollment", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def progress_percent(self):
        unit_ids = {unit.id for unit in self.course.active_units}
        if not unit_ids:
            return 0
        completed = {
            item.unit_id for item in self.progresses
            if item.status == "completed" and item.unit_id in unit_ids
        }
        return round(len(completed) / len(unit_ids) * 100)

    __table_args__ = (db.UniqueConstraint("course_id", "user_id", "child_id"),)


class CourseUnitProgress(db.Model):
    __tablename__ = "course_unit_progress"
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(
        db.Integer, db.ForeignKey("course_enrollments.id"), nullable=False, index=True
    )
    unit_id = db.Column(db.Integer, db.ForeignKey("course_units.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="started", index=True)
    percent = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.String(700), nullable=False, default="")
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    unit = db.relationship("CourseUnit")
    __table_args__ = (db.UniqueConstraint("enrollment_id", "unit_id"),)


class CourseOrder(db.Model):
    __tablename__ = "course_orders"
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="draft", index=True)
    currency = db.Column(db.String(10), nullable=False, default="IRT")
    gross_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    discount_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    organization_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    payable_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    support_project_id = db.Column(
        db.Integer, db.ForeignKey("sponsored_projects.id"), nullable=True, index=True
    )
    allocation_id = db.Column(
        db.Integer, db.ForeignKey("payment_allocations.id"), nullable=True, unique=True, index=True
    )
    pricing_snapshot_json = db.Column(db.Text, nullable=False, default="{}")
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    refunded_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User")
    child = db.relationship("Child")
    support_project = db.relationship("SponsoredProject")
    allocation = db.relationship("PaymentAllocation")
    items = db.relationship(
        "CourseOrderItem", backref="order", lazy=True, cascade="all, delete-orphan"
    )
    transactions = db.relationship(
        "PaymentTransaction",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="PaymentTransaction.created_at.desc()",
    )
    invoice = db.relationship(
        "CourseInvoice", backref="order", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def pricing_snapshot(self):
        try:
            value = json.loads(self.pricing_snapshot_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class CourseOrderItem(db.Model):
    __tablename__ = "course_order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("course_orders.id"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    title_snapshot = db.Column(db.String(180), nullable=False)
    unit_price_toman = db.Column(db.Integer, nullable=False, default=0)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    line_total_toman = db.Column(db.Integer, nullable=False, default=0)
    course = db.relationship("Course")


class CourseInvoice(db.Model):
    __tablename__ = "course_invoices"
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("course_orders.id"), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="issued", index=True)
    gross_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    discount_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    organization_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    payable_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    refunded_at = db.Column(db.DateTime(timezone=True), nullable=True)


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("course_orders.id"), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False, default="zarinpal", index=True)
    idempotency_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    authority = db.Column(db.String(100), unique=True, nullable=True, index=True)
    amount_toman = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="initiated", index=True)
    provider_code = db.Column(db.String(40), nullable=False, default="")
    reference_id = db.Column(db.String(100), nullable=False, default="", index=True)
    card_pan = db.Column(db.String(40), nullable=False, default="")
    request_json = db.Column(db.Text, nullable=False, default="{}")
    response_json = db.Column(db.Text, nullable=False, default="{}")
    error_message = db.Column(db.String(500), nullable=False, default="")
    attempt_no = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def response(self):
        try:
            value = json.loads(self.response_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class IntegrationSetting(db.Model):
    __tablename__ = "integration_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False, default="")
    encrypted_value = db.Column(db.Text, nullable=False, default="")
    secret_hint = db.Column(db.String(20), nullable=False, default="")
    is_secret = db.Column(db.Boolean, nullable=False, default=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class SmsOutbox(db.Model):
    __tablename__ = "sms_outbox"
    id = db.Column(db.Integer, primary_key=True)
    unique_key = db.Column(db.String(160), unique=True, nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    recipient = db.Column(db.String(20), nullable=False, index=True)
    pattern_code = db.Column(db.String(100), nullable=False, default="")
    message = db.Column(db.String(1000), nullable=False, default="")
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(30), nullable=False, default="queued", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    provider_message_id = db.Column(db.String(100), nullable=False, default="")
    last_error = db.Column(db.String(500), nullable=False, default="")
    next_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def payload(self):
        try:
            value = json.loads(self.payload_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class CommerceAuditLog(db.Model):
    __tablename__ = "commerce_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("course_orders.id"), nullable=True, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="success", index=True)
    details_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    order = db.relationship("CourseOrder")

    @property
    def details(self):
        try:
            value = json.loads(self.details_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


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
    skill_links = db.relationship(
        "ScenarioTopicSkillMembership",
        backref="topic",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ScenarioTopicSkillMembership.sort_order",
    )

    @property
    def skills(self):
        return [item.skill for item in self.skill_links]


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


class ScenarioTopicProfile(db.Model):
    """Stage 13 metadata kept separate from the legacy topic table for safe migration."""

    __tablename__ = "scenario_topic_profiles"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, unique=True, index=True
    )
    domain = db.Column(db.String(100), nullable=False, default="ارتباط خانوادگی", index=True)
    target_skill_id = db.Column(
        db.Integer, db.ForeignKey("skill_modules.id"), nullable=True, index=True
    )
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    topic = db.relationship("ScenarioTopic", backref=db.backref("catalog_profile", uselist=False))
    target_skill = db.relationship("SkillModule")


class ScenarioTopicSkillMembership(db.Model):
    __tablename__ = "scenario_topic_skill_memberships"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, index=True
    )
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skill_modules.id"), nullable=False, index=True
    )
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    skill = db.relationship("SkillModule")
    __table_args__ = (db.UniqueConstraint("topic_id", "skill_id"),)


class CrisisLevelDefinition(db.Model):
    __tablename__ = "crisis_level_definitions"
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False, unique=True, index=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    title = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(700), nullable=False, default="")
    behavioral_markers_json = db.Column(db.Text, nullable=False, default="[]")
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    @property
    def behavioral_markers(self):
        try:
            value = json.loads(self.behavioral_markers_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []


class ParentingStyleDefinition(db.Model):
    __tablename__ = "parenting_style_definitions"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True, index=True)
    title = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(700), nullable=False, default="")
    traits_json = db.Column(db.Text, nullable=False, default="[]")
    color = db.Column(db.String(20), nullable=False, default="#176254")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    @property
    def traits(self):
        try:
            value = json.loads(self.traits_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []


class ScenarioNarrative(db.Model):
    __tablename__ = "scenario_narratives"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(
        db.Integer, db.ForeignKey("scenario_topics.id"), nullable=False, index=True
    )
    level = db.Column(db.Integer, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    context_text = db.Column(db.Text, nullable=False)
    child_age_min = db.Column(db.Integer, nullable=False, default=6)
    child_age_max = db.Column(db.Integer, nullable=False, default=18)
    child_quote = db.Column(db.String(700), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    source_note = db.Column(db.String(700), nullable=False, default="")
    copied_from_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narratives.id"), nullable=True, index=True
    )
    previous_narrative_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narratives.id"), nullable=True, index=True
    )
    growth_next_narrative_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narratives.id"), nullable=True, index=True
    )
    fall_next_narrative_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narratives.id"), nullable=True, index=True
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    topic = db.relationship("ScenarioTopic")
    creator = db.relationship("User")
    copied_from = db.relationship(
        "ScenarioNarrative", remote_side=[id], foreign_keys=[copied_from_id]
    )
    previous_narrative = db.relationship(
        "ScenarioNarrative", remote_side=[id], foreign_keys=[previous_narrative_id]
    )
    growth_next_narrative = db.relationship(
        "ScenarioNarrative", remote_side=[id], foreign_keys=[growth_next_narrative_id]
    )
    fall_next_narrative = db.relationship(
        "ScenarioNarrative", remote_side=[id], foreign_keys=[fall_next_narrative_id]
    )
    reactions = db.relationship(
        "ScenarioReaction",
        backref="narrative",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ScenarioReaction.id",
    )

    __table_args__ = (
        db.CheckConstraint("level >= 1 AND level <= 5", name="ck_narrative_level"),
        db.CheckConstraint("child_age_min >= 0", name="ck_narrative_age_min"),
        db.CheckConstraint("child_age_max >= child_age_min", name="ck_narrative_age_range"),
    )


class ScenarioReaction(db.Model):
    __tablename__ = "scenario_reactions"
    id = db.Column(db.Integer, primary_key=True)
    narrative_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narratives.id"), nullable=False, index=True
    )
    style_id = db.Column(
        db.Integer, db.ForeignKey("parenting_style_definitions.id"), nullable=False, index=True
    )
    reaction_text = db.Column(db.Text, nullable=False)
    present_skill_ids_json = db.Column(db.Text, nullable=False, default="[]")
    missing_skill_ids_json = db.Column(db.Text, nullable=False, default="[]")
    short_term_consequence = db.Column(db.Text, nullable=False, default="")
    long_term_consequence = db.Column(db.Text, nullable=False, default="")
    retry_guidance = db.Column(db.Text, nullable=False, default="")
    scientific_score = db.Column(db.Integer, nullable=False, default=0)

    style = db.relationship("ParentingStyleDefinition")
    __table_args__ = (
        db.UniqueConstraint("narrative_id", "style_id"),
        db.CheckConstraint(
            "scientific_score >= 0 AND scientific_score <= 100",
            name="ck_reaction_scientific_score",
        ),
    )

    @staticmethod
    def _ids(value):
        try:
            return [int(item) for item in json.loads(value or "[]")]
        except (TypeError, ValueError):
            return []

    @property
    def present_skill_ids(self):
        return self._ids(self.present_skill_ids_json)

    @property
    def missing_skill_ids(self):
        return self._ids(self.missing_skill_ids_json)


class ScenarioNarrativeAttempt(db.Model):
    __tablename__ = "scenario_narrative_attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    narrative_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narratives.id"), nullable=False, index=True
    )
    selected_reaction_id = db.Column(
        db.Integer, db.ForeignKey("scenario_reactions.id"), nullable=False, index=True
    )
    retry_of_id = db.Column(
        db.Integer, db.ForeignKey("scenario_narrative_attempts.id"), nullable=True, index=True
    )
    option_order_json = db.Column(db.Text, nullable=False, default="[]")
    score = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    narrative = db.relationship("ScenarioNarrative")
    selected_reaction = db.relationship("ScenarioReaction")
    retry_of = db.relationship("ScenarioNarrativeAttempt", remote_side=[id])

    @property
    def option_order(self):
        try:
            return [int(item) for item in json.loads(self.option_order_json or "[]")]
        except (TypeError, ValueError):
            return []


class DynamicForm(db.Model):
    __tablename__ = "dynamic_forms"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=False, default="")
    form_type = db.Column(db.String(30), nullable=False, default="assessment", index=True)
    use_case = db.Column(db.String(80), nullable=False, default="general", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    schema_json = db.Column(db.Text, nullable=False, default="[]")
    settings_json = db.Column(db.Text, nullable=False, default="{}")
    scoring_json = db.Column(db.Text, nullable=False, default="{}")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True)

    versions = db.relationship(
        "FormVersion", backref="form", lazy=True, cascade="all, delete-orphan",
        order_by="FormVersion.version.desc()",
    )
    assignments = db.relationship(
        "FormAssignment", backref="form", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def fields(self):
        try:
            value = json.loads(self.schema_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def settings(self):
        try:
            value = json.loads(self.settings_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def scoring(self):
        try:
            value = json.loads(self.scoring_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def response_count(self):
        return FormResponse.query.filter_by(form_id=self.id, status="submitted").count()


class FormVersion(db.Model):
    __tablename__ = "form_versions"
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    schema_json = db.Column(db.Text, nullable=False, default="[]")
    settings_json = db.Column(db.Text, nullable=False, default="{}")
    scoring_json = db.Column(db.Text, nullable=False, default="{}")
    snapshot_hash = db.Column(db.String(64), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (db.UniqueConstraint("form_id", "version"),)


class FormAssignment(db.Model):
    __tablename__ = "form_assignments"
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False, index=True)
    target_type = db.Column(db.String(30), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=True, index=True)
    target_ref = db.Column(db.String(120), nullable=False, default="")
    title = db.Column(db.String(180), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    is_required = db.Column(db.Boolean, nullable=False, default=False)
    opens_at = db.Column(db.DateTime(timezone=True), nullable=True)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class FormMediaAsset(db.Model):
    __tablename__ = "form_media_assets"
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    field_key = db.Column(db.String(80), nullable=False, default="")
    kind = db.Column(db.String(30), nullable=False, default="file")
    original_name = db.Column(db.String(240), nullable=False)
    storage_name = db.Column(db.String(120), unique=True, nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    is_private = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    form = db.relationship("DynamicForm")
    owner = db.relationship("User")


class FormResponse(db.Model):
    __tablename__ = "form_responses"
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("form_assignments.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=True)
    form_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="submitted", index=True)
    answers_json = db.Column(db.Text, nullable=False)
    score_total = db.Column(db.Float, nullable=True)
    subscale_scores_json = db.Column(db.Text, nullable=False, default="{}")
    result_key = db.Column(db.String(80), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    form = db.relationship("DynamicForm")
    child = db.relationship("Child")
    assignment = db.relationship("FormAssignment")
    user = db.relationship("User")

    __table_args__ = (
        db.Index("ix_form_response_family_timeline", "user_id", "child_id", "created_at"),
        db.Index("ix_form_response_form_status", "form_id", "status"),
    )

    @property
    def answers(self):
        try:
            value = json.loads(self.answers_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def subscale_scores(self):
        try:
            value = json.loads(self.subscale_scores_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class GrowthReportSchedule(db.Model):
    """A daily/weekly check-in attached to one child's growth path."""

    __tablename__ = "growth_report_schedules"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False, index=True)
    weekly_plan_id = db.Column(db.Integer, db.ForeignKey("weekly_plans.id"), nullable=True, index=True)
    daily_action_id = db.Column(db.Integer, db.ForeignKey("daily_actions.id"), nullable=True, index=True)
    cadence = db.Column(db.String(20), nullable=False, default="weekly", index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    completed_response_id = db.Column(
        db.Integer, db.ForeignKey("form_responses.id"), nullable=True, unique=True
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    child = db.relationship("Child")
    form = db.relationship("DynamicForm")
    plan = db.relationship("WeeklyPlan")
    action = db.relationship("DailyAction")
    response = db.relationship("FormResponse")


class JourneyNotification(db.Model):
    """In-product return-to-path notice with deterministic de-duplication."""

    __tablename__ = "journey_notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.String(700), nullable=False, default="")
    target_url = db.Column(db.String(300), nullable=False, default="")
    source_type = db.Column(db.String(40), nullable=False, default="")
    source_id = db.Column(db.Integer, nullable=True)
    dedupe_key = db.Column(db.String(160), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="unread", index=True)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)

    child = db.relationship("Child")


class BackgroundJob(db.Model):
    """Retryable work item for imports, reports, private-file scans and notifications."""

    __tablename__ = "background_jobs"
    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(db.String(50), nullable=False, index=True)
    idempotency_key = db.Column(db.String(180), nullable=False, unique=True, index=True)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    result_json = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    next_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_error = db.Column(db.String(700), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def payload(self):
        try:
            value = json.loads(self.payload_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def result(self):
        try:
            value = json.loads(self.result_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class ProfileDefinition(db.Model):
    __tablename__ = "profile_definitions"
    id = db.Column(db.Integer, primary_key=True)
    profile_type = db.Column(db.String(30), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    bindings = db.relationship(
        "ProfileFormBinding",
        backref="definition",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ProfileFormBinding.sort_order",
    )
    records = db.relationship(
        "ProfileRecord", backref="definition", lazy=True, cascade="all, delete-orphan"
    )
    __table_args__ = (db.UniqueConstraint("profile_type", "version"),)


class ProfileFormBinding(db.Model):
    __tablename__ = "profile_form_bindings"
    id = db.Column(db.Integer, primary_key=True)
    definition_id = db.Column(
        db.Integer, db.ForeignKey("profile_definitions.id"), nullable=False, index=True
    )
    form_id = db.Column(db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=False, index=True)
    section_key = db.Column(db.String(80), nullable=False, default="general")
    section_title = db.Column(db.String(160), nullable=False, default="اطلاعات تکمیلی")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    form = db.relationship("DynamicForm")
    __table_args__ = (db.UniqueConstraint("definition_id", "form_id"),)


class ProfileRecord(db.Model):
    __tablename__ = "profile_records"
    id = db.Column(db.Integer, primary_key=True)
    definition_id = db.Column(
        db.Integer, db.ForeignKey("profile_definitions.id"), nullable=False, index=True
    )
    subject_id = db.Column(db.Integer, nullable=False, index=True)
    values_json = db.Column(db.Text, nullable=False, default="{}")
    record_version = db.Column(db.Integer, nullable=False, default=1)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (db.UniqueConstraint("definition_id", "subject_id"),)

    @property
    def values(self):
        try:
            value = json.loads(self.values_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    legal_name = db.Column(db.String(200), nullable=False, default="")
    registration_no = db.Column(db.String(80), nullable=False, default="")
    contact_name = db.Column(db.String(120), nullable=False, default="")
    contact_mobile = db.Column(db.String(20), nullable=False, default="")
    contact_email = db.Column(db.String(160), nullable=False, default="")
    address = db.Column(db.String(700), nullable=False, default="")
    website = db.Column(db.String(300), nullable=False, default="")
    logo_url = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    profile_form_id = db.Column(
        db.Integer, db.ForeignKey("dynamic_forms.id"), nullable=True, index=True
    )
    profile_data_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    projects = db.relationship(
        "SponsoredProject", backref="organization", lazy=True, cascade="all, delete-orphan"
    )
    contracts = db.relationship(
        "OrganizationContract",
        backref="organization",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="OrganizationContract.created_at.desc()",
    )
    profile_form = db.relationship("DynamicForm")
    audit_logs = db.relationship(
        "OrganizationAuditLog",
        backref="organization",
        lazy=True,
        passive_deletes=True,
        order_by="OrganizationAuditLog.created_at.desc()",
    )

    @property
    def profile_data(self):
        try:
            value = json.loads(self.profile_data_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @property
    def active_contract_count(self):
        return sum(item.status in {"draft", "active"} for item in self.contracts)


class OrganizationContract(db.Model):
    __tablename__ = "organization_contracts"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    contract_no = db.Column(db.String(80), unique=True, nullable=False, index=True)
    body_text = db.Column(db.Text, nullable=False, default="")
    terms_text = db.Column(db.Text, nullable=False, default="")
    commitments_text = db.Column(db.Text, nullable=False, default="")
    starts_on = db.Column(db.Date, nullable=True)
    ends_on = db.Column(db.Date, nullable=True)
    total_amount_toman = db.Column(db.Integer, nullable=False, default=0)
    amount_paid_toman = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    services_json = db.Column(db.Text, nullable=False, default="[]")
    document_name = db.Column(db.String(240), nullable=False, default="")
    document_url = db.Column(db.String(700), nullable=False, default="")
    version = db.Column(db.Integer, nullable=False, default=1)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True)

    beneficiaries = db.relationship(
        "ContractBeneficiary",
        backref="contract",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ContractBeneficiary.created_at.desc()",
    )

    @property
    def services(self):
        try:
            value = json.loads(self.services_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def active_beneficiary_count(self):
        return sum(item.status == "active" for item in self.beneficiaries)

    @property
    def committed_amount_toman(self):
        return sum(project.committed_subsidy_toman for project in self.support_plans)

    @property
    def consumed_service_count(self):
        return sum(
            1
            for project in self.support_plans
            for membership in project.memberships
            for allocation in membership.allocations
            if allocation.status not in {"cancelled", "refunded"}
        )

    @property
    def covered_parents(self):
        values = {
            item.parent
            for item in self.beneficiaries
            if item.parent is not None and item.status == "active"
        }
        values.update(
            membership.parent
            for project in self.support_plans
            for membership in project.memberships
            if membership.status in {"active", "pending"}
        )
        return sorted(values, key=lambda item: item.full_name)

    @property
    def covered_children(self):
        values = {
            item.child
            for item in self.beneficiaries
            if item.child is not None and item.status == "active"
        }
        for parent in self.covered_parents:
            values.update(parent.children)
        return sorted(values, key=lambda item: item.name)


class ContractBeneficiary(db.Model):
    __tablename__ = "contract_beneficiaries"
    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer, db.ForeignKey("organization_contracts.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("children.id"), nullable=True, index=True)
    beneficiary_type = db.Column(db.String(20), nullable=False, default="family", index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    starts_on = db.Column(db.Date, nullable=True)
    ends_on = db.Column(db.Date, nullable=True)
    note = db.Column(db.String(700), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)

    parent = db.relationship("User")
    child = db.relationship("Child")


class OrganizationAuditLog(db.Model):
    __tablename__ = "organization_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_name = db.Column(db.String(160), nullable=False, default="")
    contract_id = db.Column(db.Integer, nullable=True, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False, index=True)
    details_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def details(self):
        try:
            value = json.loads(self.details_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


class SponsoredProject(db.Model):
    __tablename__ = "sponsored_projects"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    contract_id = db.Column(
        db.Integer, db.ForeignKey("organization_contracts.id"), nullable=True, index=True
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
    contract = db.relationship("OrganizationContract", backref="support_plans")

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

