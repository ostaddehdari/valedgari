"""Idempotent data migrations used while releasing Stage 15."""

import json

from .extensions import db
from .models import FormAssignment, Organization, ProfileRecord
from .profiles import active_profile_definition, sync_role_form_to_profile


def migrate_stage15_data(actor_id=None):
    """Move legacy role forms and organization profile JSON into unified profiles."""
    bindings_created = 0
    records_migrated = 0

    role_assignments = FormAssignment.query.filter_by(
        target_type="role", status="active"
    ).all()
    for assignment in role_assignments:
        before = sync_role_form_to_profile(
            assignment.form,
            assignment.target_ref,
            actor_id,
            assignment.title or assignment.form.title,
        )
        if before is not None and before.id is None:
            bindings_created += 1

    db.session.flush()
    for organization in Organization.query.filter(
        Organization.profile_form_id.isnot(None)
    ).all():
        binding = sync_role_form_to_profile(
            organization.profile_form,
            "organization",
            actor_id,
            organization.profile_form.title,
        )
        db.session.flush()
        organization_definition = active_profile_definition("organization")
        if not binding or not organization_definition:
            continue
        legacy_values = organization.profile_data
        if not legacy_values:
            continue
        record = ProfileRecord.query.filter_by(
            definition_id=organization_definition.id,
            subject_id=organization.id,
        ).first()
        values = dict(record.values) if record else {}
        for key, value in legacy_values.items():
            values.setdefault(f"{binding.id}:{key}", value)
        if not record:
            record = ProfileRecord(
                definition_id=organization_definition.id,
                subject_id=organization.id,
                updated_by=actor_id,
            )
            db.session.add(record)
        record.values_json = json.dumps(values, ensure_ascii=False)
        record.updated_by = actor_id
        records_migrated += 1

    db.session.commit()
    return {
        "role_assignments_checked": len(role_assignments),
        "bindings_created": bindings_created,
        "organization_records_migrated": records_migrated,
    }
