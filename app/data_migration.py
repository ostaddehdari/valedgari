"""Idempotent data migrations used while releasing Stage 15."""

import json

from .extensions import db
from .models import (
    FormAssignment,
    Organization,
    OrganizationContract,
    ProfileRecord,
    SponsoredProject,
)
from .profiles import active_profile_definition, sync_role_form_to_profile


def migrate_stage15_data(actor_id=None):
    """Move legacy role forms and organization profile JSON into unified profiles."""
    bindings_created = 0
    records_migrated = 0
    legacy_contracts_created = 0

    legacy_projects = SponsoredProject.query.filter_by(contract_id=None).all()
    if legacy_projects and not actor_id:
        raise RuntimeError("برای انتقال پروژه‌های قدیمی، وجود حساب مدیر الزامی است.")
    for organization in Organization.query.order_by(Organization.id).all():
        projects = [item for item in legacy_projects if item.organization_id == organization.id]
        if not projects:
            continue
        contract_no = f"LEGACY-ORG-{organization.id:05d}"
        contract = OrganizationContract.query.filter_by(contract_no=contract_no).first()
        if not contract:
            contract = OrganizationContract(
                organization_id=organization.id,
                contract_no=contract_no,
                title=f"قرارداد انتقالی {organization.name}",
                status="active" if any(item.status == "active" for item in projects) else "draft",
                services_json=json.dumps(
                    sorted({service for item in projects for service in item.eligible_services}),
                    ensure_ascii=False,
                ),
                terms_text="این قرارداد به‌صورت خودکار از پروژه‌های سازمانی پیش از استیج ۱۵ ساخته شده است.",
                created_by=actor_id,
            )
            db.session.add(contract)
            db.session.flush()
            legacy_contracts_created += 1
        for project in projects:
            project.contract_id = contract.id

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
        "legacy_contracts_created": legacy_contracts_created,
        "legacy_projects_attached": len(legacy_projects),
    }
