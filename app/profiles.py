import json

from .extensions import db
from .form_engine import MULTI_VALUE_TYPES, NON_INPUT_TYPES
from .models import ProfileDefinition, ProfileFormBinding, ProfileRecord


PROFILE_TYPES = {
    "organization": "پروفایل سازمان",
    "guardian": "پروفایل والد / سرپرست",
    "child": "پروفایل فرزند",
}

ROLE_PROFILE_TYPES = {
    "parent": "guardian",
    "guardian": "guardian",
    "child": "child",
    "organization": "organization",
}


def active_profile_definition(profile_type):
    return (
        ProfileDefinition.query.filter_by(profile_type=profile_type, status="active")
        .order_by(ProfileDefinition.version.desc())
        .first()
    )


def profile_record(definition, subject_id):
    if not definition:
        return None
    return ProfileRecord.query.filter_by(
        definition_id=definition.id, subject_id=subject_id
    ).first()


def sync_role_form_to_profile(form, role_key, actor_id=None, section_title=None):
    """Treat a published role-linked form as the active profile schema for that role."""
    profile_type = ROLE_PROFILE_TYPES.get(role_key)
    if not profile_type or not form or form.status != "published":
        return None
    definition = active_profile_definition(profile_type)
    if not definition:
        definition = ProfileDefinition(
            profile_type=profile_type,
            title=PROFILE_TYPES[profile_type],
            version=1,
            status="active",
            created_by=actor_id,
        )
        db.session.add(definition)
        db.session.flush()
    binding = ProfileFormBinding.query.filter_by(
        definition_id=definition.id, form_id=form.id
    ).first()
    if not binding:
        binding = ProfileFormBinding(
            definition_id=definition.id,
            form_id=form.id,
            section_key=f"role-{role_key}",
            section_title=(section_title or form.title)[:160],
            sort_order=len(definition.bindings),
            is_active=True,
        )
        db.session.add(binding)
    else:
        binding.is_active = True
    return binding


def profile_sections(definition, record=None):
    values = record.values if record else {}
    sections = []
    for binding in definition.bindings if definition else []:
        if not binding.is_active:
            continue
        fields = []
        for field in binding.form.fields:
            if field.get("type") in NON_INPUT_TYPES:
                if field.get("type") in {"content", "section"}:
                    fields.append({**field, "field_id": "", "input_name": "", "value": ""})
                continue
            field_id = str(field.get("id", "")).strip()
            if not field_id:
                continue
            key = f"{binding.id}:{field_id}"
            fields.append(
                {
                    **field,
                    "field_id": field_id,
                    "input_name": f"profile_{binding.id}_{field_id}",
                    "value": values.get(key, ""),
                }
            )
        sections.append(
            {
                "binding": binding,
                "title": binding.section_title,
                "key": binding.section_key,
                "form": binding.form,
                "fields": fields,
            }
        )
    return sections


def save_profile_values(definition, subject_id, form_data, actor_id):
    record = profile_record(definition, subject_id)
    values = dict(record.values) if record else {}
    errors = []
    for section in profile_sections(definition, record):
        binding = section["binding"]
        for field in section["fields"]:
            if not field.get("input_name"):
                continue
            if field.get("type") in MULTI_VALUE_TYPES:
                value = form_data.getlist(field["input_name"])
            elif field.get("type") == "consent":
                value = form_data.get(field["input_name"]) == "1"
            else:
                value = form_data.get(field["input_name"], "")
            if isinstance(value, str):
                value = value.strip()
            if field.get("required") and not value:
                errors.append(f"فیلد «{field.get('label', 'بدون عنوان')}» الزامی است.")
            values[f"{binding.id}:{field['field_id']}"] = value
    if errors:
        return record, errors
    if not record:
        record = ProfileRecord(
            definition_id=definition.id,
            subject_id=subject_id,
            updated_by=actor_id,
        )
        db.session.add(record)
    else:
        record.record_version += 1
        record.updated_by = actor_id
    record.values_json = json.dumps(values, ensure_ascii=False)
    return record, []
