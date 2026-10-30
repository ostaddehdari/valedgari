import json

from .extensions import db
from .models import ProfileDefinition, ProfileRecord


PROFILE_TYPES = {
    "organization": "پروفایل سازمان",
    "guardian": "پروفایل والد / سرپرست",
    "child": "پروفایل فرزند",
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


def profile_sections(definition, record=None):
    values = record.values if record else {}
    sections = []
    for binding in definition.bindings if definition else []:
        if not binding.is_active:
            continue
        fields = []
        for field in binding.form.fields:
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
