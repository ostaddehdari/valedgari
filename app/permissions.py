"""Central Stage 15 RBAC and family-resource ownership checks."""

from .models import Child, GuardianRelationship


ROLE_PERMISSIONS = {
    "admin": {"*"},
    "reviewer": {
        "admin.view",
        "scientific.review",
        "content.view",
        "profile.view",
        "report.aggregate.view",
    },
    "parent": {
        "family.view",
        "family.edit",
        "form.fill",
        "course.learn",
        "assistant.use",
        "privacy.manage",
    },
}


def has_permission(user, permission):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    granted = ROLE_PERMISSIONS.get(user.role, set())
    return "*" in granted or permission in granted


def child_access_level(user, child):
    if not user or not child:
        return None
    if user.role == "admin":
        return "full"
    if child.user_id == user.id:
        return "full"
    link = GuardianRelationship.query.filter_by(
        child_id=child.id, guardian_id=user.id, status="active"
    ).first()
    return link.access_level if link else None


def can_access_child(user, child, write=False):
    level = child_access_level(user, child)
    if write:
        return level == "full"
    return level in {"full", "view", "limited"}


def accessible_child_ids(user, write=False):
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    if user.role == "admin":
        return {item.id for item in Child.query.with_entities(Child.id).all()}
    owned = {item.id for item in Child.query.filter_by(user_id=user.id).all()}
    levels = ["full"] if write else ["full", "view", "limited"]
    owned.update(
        item.child_id
        for item in GuardianRelationship.query.filter(
            GuardianRelationship.guardian_id == user.id,
            GuardianRelationship.status == "active",
            GuardianRelationship.access_level.in_(levels),
        ).all()
    )
    return owned

