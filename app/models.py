import json
from datetime import datetime, timezone

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

