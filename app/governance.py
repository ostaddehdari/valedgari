from .models import (
    AssessmentInstrument,
    DynamicForm,
    MicroLesson,
    PersonalizationRule,
    SafetyProtocol,
    ScientificReview,
)


RESOURCE_MODELS = {
    "instrument": AssessmentInstrument,
    "lesson": MicroLesson,
    "rule": PersonalizationRule,
    "protocol": SafetyProtocol,
    "form": DynamicForm,
}


def resource_snapshot(resource_type, resource):
    if resource_type == "instrument":
        payload = {
            "title": resource.title,
            "version": resource.version,
            "source": resource.source_reference,
            "license": resource.license_note,
            "disclaimer": resource.disclaimer,
            "schema": resource.scoring_schema,
            "questions": [
                {
                    "code": item.code,
                    "text": item.text,
                    "dimension": item.dimension,
                    "weight": item.weight,
                    "reverse": item.reverse_score,
                }
                for item in resource.questions
            ],
        }
    elif resource_type == "lesson":
        payload = {
            "title": resource.title,
            "version": resource.version,
            "objective": resource.objective,
            "body": resource.body,
            "practice": resource.practice,
            "pitfall": resource.common_pitfall,
        }
    elif resource_type == "rule":
        payload = {
            "name": resource.name,
            "version": resource.version,
            "conditions": resource.conditions,
            "recommendation": resource.recommendation_text,
            "avoid": resource.avoid_text,
            "home_action": resource.home_action,
        }
    elif resource_type == "protocol":
        payload = {
            "title": resource.title,
            "version": resource.version,
            "keywords": resource.trigger_keywords,
            "response": resource.response_text,
            "steps": resource.immediate_steps,
        }
    elif resource_type == "form":
        payload = {
            "title": resource.title,
            "version": resource.version,
            "form_type": resource.form_type,
            "use_case": resource.use_case,
            "description": resource.description,
            "fields": resource.fields,
            "settings": resource.settings,
            "scoring": resource.scoring,
        }
    else:
        raise ValueError("نوع منبع علمی پشتیبانی نمی‌شود.")
    return payload


def resource_version(resource_type, resource):
    return str(resource.version)


def resource_title(resource_type, resource):
    return getattr(resource, "title", None) or getattr(resource, "name", resource_type)


def approved_for_current_snapshot(resource_type, resource):
    from .models import ScientificReview

    fingerprint = ScientificReview.fingerprint(resource_snapshot(resource_type, resource))
    return ScientificReview.query.filter_by(
        resource_type=resource_type,
        resource_id=resource.id,
        resource_version=resource_version(resource_type, resource),
        snapshot_hash=fingerprint,
        status="approved",
    ).first()
