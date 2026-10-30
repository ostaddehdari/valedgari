import json
import math
import re
import secrets
from pathlib import Path

from werkzeug.utils import secure_filename


AI_CONTRACT = "ensha-assessment-v2"
FORM_STATUSES = {"draft", "review", "published", "archived"}
FORM_TYPES = {
    "assessment": "آزمون / سنجش",
    "intake": "جمع‌آوری اطلاعات اولیه",
    "profile": "فرم پروفایل",
    "quiz": "آزمون آموزشی",
    "report": "گزارش مسیر رشد",
    "survey": "نظرسنجی",
    "payment": "فرم مالی",
}


FIELD_CATALOG = {
    "general": {
        "label": "عمومی",
        "icon": "fa-cubes",
        "fields": [
            ("text", "T", "متن کوتاه"),
            ("paragraph", "¶", "متن بلند"),
            ("number", "#", "عدد"),
            ("dropdown", "◇", "فهرست کشویی"),
            ("single_choice", "◉", "تک‌گزینه‌ای"),
            ("multiple_choice", "☑", "چندگزینه‌ای"),
            ("multiselect", "◇", "انتخاب چندگانه"),
            ("image_choice", "◇", "انتخاب تصویری"),
        ],
    },
    "media": {
        "label": "رسانه‌ای",
        "icon": "fa-photo-film",
        "fields": [
            ("image_multiple_choice", "◇", "چندانتخابی تصویری"),
            ("video_choice", "◇", "تک‌انتخابی ویدیویی"),
            ("video_multiple_choice", "◇", "چندانتخابی ویدیویی"),
            ("audio_choice", "◇", "تک‌انتخابی صوتی"),
            ("audio_multiple_choice", "◇", "چندانتخابی صوتی"),
            ("image_answer", "◇", "پاسخ تصویری"),
            ("video_answer", "◇", "پاسخ ویدیویی"),
            ("audio_answer", "◇", "پاسخ صوتی"),
        ],
    },
    "identity": {
        "label": "اطلاعات فردی",
        "icon": "fa-address-card",
        "fields": [
            ("name", "◇", "نام و نام خانوادگی"),
            ("email", "◇", "ایمیل"),
            ("phone", "◇", "تلفن"),
            ("national_id", "◇", "کد ملی"),
            ("address", "◇", "نشانی"),
            ("date", "◇", "تاریخ"),
            ("time", "◇", "ساعت"),
            ("url", "◇", "وب‌سایت"),
            ("password", "◇", "رمز محرمانه"),
        ],
    },
    "assessment": {
        "label": "تخصصی آزمون",
        "icon": "fa-flask-vial",
        "fields": [
            ("scale", "▤", "طیف لیکرت"),
            ("rating", "◇", "امتیاز ستاره‌ای"),
            ("slider", "◇", "اسلایدر عددی"),
            ("matrix", "▦", "ماتریس چندردیفی"),
            ("list", "◇", "فهرست تکرارشونده"),
            ("consent", "◇", "رضایت‌نامه"),
            ("file", "↥", "بارگذاری فایل"),
            ("signature", "✎", "امضا"),
            ("calculation", "∑", "محاسبه"),
            ("quiz", "◇", "سؤال آزمونی"),
            ("poll", "◇", "نظرسنجی"),
            ("chained", "◇", "انتخاب وابسته"),
            ("repeater", "◇", "جدول تکرارشونده"),
            ("captcha", "◇", "کد بررسی"),
        ],
    },
    "layout": {
        "label": "چیدمان",
        "icon": "fa-table-columns",
        "fields": [
            ("content", "◇", "متن راهنما"),
            ("section", "◇", "جداکننده بخش"),
            ("page", "↵", "صفحه جدید"),
            ("hidden", "◇", "مقدار پنهان"),
        ],
    },
    "pricing": {
        "label": "قیمت‌گذاری",
        "icon": "fa-tags",
        "fields": [
            ("product", "◇", "محصول / خدمت"),
            ("quantity", "◇", "تعداد"),
            ("price_option", "◇", "گزینه قیمت"),
            ("shipping", "◇", "هزینه جانبی"),
            ("total", "◇", "جمع مبلغ"),
        ],
    },
    "content": {
        "label": "محتوا",
        "icon": "fa-file-lines",
        "fields": [
            ("post_title", "◇", "عنوان محتوا"),
            ("post_content", "◇", "متن محتوا"),
            ("post_excerpt", "◇", "خلاصه محتوا"),
            ("post_tags", "◇", "برچسب‌ها"),
            ("post_category", "◇", "دسته محتوا"),
            ("custom_field", "◇", "فیلد سفارشی"),
        ],
    },
}

FIELD_TYPES = {
    field_type
    for category in FIELD_CATALOG.values()
    for field_type, _icon, _label in category["fields"]
}
FIELD_LABELS = {
    field_type: label
    for category in FIELD_CATALOG.values()
    for field_type, _icon, label in category["fields"]
}
CHOICE_TYPES = {
    "dropdown", "single_choice", "multiple_choice", "multiselect", "image_choice",
    "image_multiple_choice", "video_choice", "video_multiple_choice", "audio_choice",
    "audio_multiple_choice", "quiz", "poll", "price_option", "post_category",
}
MULTI_VALUE_TYPES = {
    "multiple_choice", "multiselect", "image_multiple_choice",
    "video_multiple_choice", "audio_multiple_choice", "post_tags",
}
UPLOAD_TYPES = {"file", "image_answer", "video_answer", "audio_answer", "signature"}
NON_INPUT_TYPES = {"content", "section", "page"}
ALLOWED_WIDTHS = {25, 33, 50, 66, 75, 100}
DEFAULT_UPLOAD_EXTENSIONS = {
    "file": {"pdf", "doc", "docx", "jpg", "jpeg", "png"},
    "image_answer": {"jpg", "jpeg", "png", "webp"},
    "video_answer": {"mp4", "webm"},
    "audio_answer": {"mp3", "wav", "ogg", "m4a"},
    "signature": {"png", "jpg", "jpeg"},
}
MIME_BY_EXTENSION = {
    "pdf": {"application/pdf"},
    "doc": {"application/msword"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "jpg": {"image/jpeg"}, "jpeg": {"image/jpeg"}, "png": {"image/png"},
    "webp": {"image/webp"}, "mp4": {"video/mp4"}, "webm": {"video/webm"},
    "mp3": {"audio/mpeg"}, "wav": {"audio/wav", "audio/x-wav"},
    "ogg": {"audio/ogg"}, "m4a": {"audio/mp4", "audio/x-m4a"},
}


def file_signature_matches(extension, header_bytes):
    """Check common container signatures instead of trusting browser supplied MIME alone."""
    header = bytes(header_bytes or b"")[:32]
    if extension == "pdf":
        return header.startswith(b"%PDF-")
    if extension in {"jpg", "jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == "png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == "webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if extension in {"mp4", "m4a"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if extension == "webm":
        return header.startswith(b"\x1aE\xdf\xa3")
    if extension == "mp3":
        return header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
    if extension == "wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if extension == "ogg":
        return header.startswith(b"OggS")
    if extension == "doc":
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension == "docx":
        return header.startswith(b"PK\x03\x04")
    return False


def _json_dict(value, default=None):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else (default or {})
        except ValueError:
            return default or {}
    return default or {}


def _json_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except ValueError:
            return []
    return []


def field_catalog_payload():
    return [
        {
            "key": key,
            "label": group["label"],
            "icon": group["icon"],
            "fields": [
                {"type": field_type, "icon": icon, "label": label}
                for field_type, icon, label in group["fields"]
            ],
        }
        for key, group in FIELD_CATALOG.items()
    ]


def default_field(field_type, index=1):
    field_type = field_type if field_type in FIELD_TYPES else "text"
    options = []
    if field_type in CHOICE_TYPES:
        options = [
            {"label": "گزینه اول", "value": "option_1", "score": 0},
            {"label": "گزینه دوم", "value": "option_2", "score": 0},
        ]
    field = {
        "id": f"field_{secrets.token_hex(4)}",
        "key": f"field_{index}",
        "type": field_type,
        "label": FIELD_LABELS[field_type],
        "description": "",
        "placeholder": "",
        "required": False,
        "width": 100,
        "default": "",
        "options": options,
        "validation": {},
        "conditional_logic": {"enabled": False, "match": "all", "action": "show", "rules": []},
        "scoring": {"weight": 1, "reverse": False, "subscale": ""},
        "media": {"url": "", "kind": "", "alt": ""},
    }
    if field_type in {"scale", "rating", "slider"}:
        field["validation"] = {"min": 1, "max": 5, "step": 1}
    if field_type in UPLOAD_TYPES:
        field["validation"] = {
            "allowed_extensions": sorted(DEFAULT_UPLOAD_EXTENSIONS[field_type]),
            "max_size_mb": 5,
            "max_files": 1,
        }
    if field_type == "page":
        field["label"] = "صفحه جدید"
        field["progress_title"] = f"مرحله {index}"
    return field


def _clean_key(value, fallback):
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(value or "").strip()).strip("_")
    return cleaned[:80] or fallback


def normalize_option(option, index):
    if not isinstance(option, dict):
        option = {"label": str(option), "value": str(option)}
    label = str(option.get("label", "")).strip()[:200] or f"گزینه {index}"
    value = _clean_key(option.get("value"), f"option_{index}")
    try:
        score = float(option.get("score", 0) or 0)
    except (TypeError, ValueError):
        score = 0
    return {
        "label": label,
        "value": value,
        "score": score,
        "media_url": str(option.get("media_url", "")).strip()[:700],
        "media_kind": str(option.get("media_kind", "")).strip()[:20],
    }


def normalize_field(field, index, errors):
    path = f"fields[{index}]"
    if not isinstance(field, dict):
        errors.append(f"{path}: باید شیء JSON باشد.")
        return None
    field_type = str(field.get("type", "")).strip()
    field_type = {"textarea": "paragraph", "radio": "single_choice", "select": "dropdown"}.get(
        field_type, field_type
    )
    if field_type not in FIELD_TYPES:
        errors.append(f"{path}.type: نوع «{field_type}» پشتیبانی نمی‌شود.")
        return None
    field_id = _clean_key(field.get("id"), f"field_{index + 1}")
    key = _clean_key(field.get("key"), field_id)
    label = str(field.get("label", "")).strip()[:300]
    if not label:
        errors.append(f"{path}.label: عنوان فیلد الزامی است.")
    try:
        width = int(field.get("width", 100))
    except (TypeError, ValueError):
        width = 100
    if width not in ALLOWED_WIDTHS:
        width = 100
    options = _json_list(field.get("options", []))
    if len(options) > 100:
        errors.append(f"{path}.options: حداکثر ۱۰۰ گزینه مجاز است.")
        options = options[:100]
    normalized_options = [normalize_option(option, i + 1) for i, option in enumerate(options)]
    if field_type in CHOICE_TYPES and not normalized_options:
        normalized_options = default_field(field_type)["options"]
    validation = _json_dict(field.get("validation"))
    conditional = _json_dict(field.get("conditional_logic"))
    rules = _json_list(conditional.get("rules"))
    if len(rules) > 20:
        errors.append(f"{path}.conditional_logic.rules: حداکثر ۲۰ شرط مجاز است.")
        rules = rules[:20]
    normalized_rules = []
    for rule_index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"{path}.conditional_logic.rules[{rule_index}]: شرط معتبر نیست.")
            continue
        normalized_rules.append(
            {
                "field": _clean_key(rule.get("field"), ""),
                "operator": str(rule.get("operator", "equals"))[:30],
                "value": rule.get("value", ""),
            }
        )
    scoring = _json_dict(field.get("scoring"))
    try:
        weight = float(scoring.get("weight", 1) or 1)
    except (TypeError, ValueError):
        weight = 1
    media = _json_dict(field.get("media"))
    return {
        "id": field_id,
        "key": key,
        "type": field_type,
        "label": label or FIELD_LABELS[field_type],
        "description": str(field.get("description", field.get("help", ""))).strip()[:1000],
        "placeholder": str(field.get("placeholder", "")).strip()[:300],
        "required": bool(field.get("required", False)),
        "width": width,
        "default": field.get("default", ""),
        "options": normalized_options,
        "validation": validation,
        "conditional_logic": {
            "enabled": bool(conditional.get("enabled", False)),
            "match": "any" if conditional.get("match") == "any" else "all",
            "action": "hide" if conditional.get("action") == "hide" else "show",
            "rules": normalized_rules,
        },
        "scoring": {
            "weight": weight,
            "reverse": bool(scoring.get("reverse", False)),
            "subscale": _clean_key(scoring.get("subscale"), ""),
            "formula": str(scoring.get("formula", "")).strip()[:500],
        },
        "media": {
            "url": str(media.get("url", "")).strip()[:700],
            "kind": str(media.get("kind", "")).strip()[:20],
            "alt": str(media.get("alt", "")).strip()[:300],
        },
        **({"progress_title": str(field.get("progress_title", label)).strip()[:160]} if field_type == "page" else {}),
    }


def normalize_schema(fields):
    errors = []
    fields = _json_list(fields)
    if not fields:
        return [], ["fields: دست‌کم یک فیلد لازم است."]
    if len(fields) > 500:
        errors.append("fields: حداکثر ۵۰۰ فیلد مجاز است.")
        fields = fields[:500]
    normalized = []
    seen_ids = set()
    seen_keys = set()
    section_count = 0
    for index, raw in enumerate(fields):
        field = normalize_field(raw, index, errors)
        if not field:
            continue
        if field["id"] in seen_ids:
            errors.append(f"fields[{index}].id: شناسه تکراری است.")
        if field["key"] in seen_keys:
            errors.append(f"fields[{index}].key: کلید تکراری است.")
        seen_ids.add(field["id"])
        seen_keys.add(field["key"])
        if field["type"] in {"section", "page"}:
            section_count += 1
        normalized.append(field)
    if section_count > 100:
        errors.append("fields: حداکثر ۱۰۰ بخش/صفحه مجاز است.")
    valid_keys = {field["key"] for field in normalized}
    for index, field in enumerate(normalized):
        for rule_index, rule in enumerate(field["conditional_logic"]["rules"]):
            if rule["field"] not in valid_keys:
                errors.append(
                    f"fields[{index}].conditional_logic.rules[{rule_index}].field: کلید مرجع پیدا نشد."
                )
    return normalized, errors


def normalize_settings(settings):
    settings = _json_dict(settings)
    return {
        "progress": settings.get("progress", "bar") if settings.get("progress") in {"bar", "steps", "none"} else "bar",
        "save_draft": bool(settings.get("save_draft", True)),
        "shuffle_fields": bool(settings.get("shuffle_fields", False)),
        "one_question_per_page": bool(settings.get("one_question_per_page", False)),
        "previous_label": str(settings.get("previous_label", "قبلی"))[:80],
        "next_label": str(settings.get("next_label", "بعدی"))[:80],
        "submit_label": str(settings.get("submit_label", "ثبت نهایی"))[:80],
        "confirmation_title": str(settings.get("confirmation_title", "پاسخ شما ثبت شد"))[:200],
        "confirmation_message": str(settings.get("confirmation_message", "از همراهی شما سپاسگزاریم."))[:700],
        "allow_multiple": bool(settings.get("allow_multiple", False)),
    }


def normalize_scoring(scoring):
    errors = []
    scoring = _json_dict(scoring)
    mode = scoring.get("mode", "manual")
    if mode not in {"manual", "sum", "weighted"}:
        errors.append("scoring.mode: فقط manual، sum یا weighted مجاز است.")
        mode = "manual"
    interpretations = _json_list(scoring.get("interpretations", []))
    normalized_ranges = []
    for index, item in enumerate(interpretations):
        if not isinstance(item, dict):
            errors.append(f"scoring.interpretations[{index}]: باید شیء باشد.")
            continue
        try:
            minimum = float(item.get("min", 0))
            maximum = float(item.get("max", 0))
        except (TypeError, ValueError):
            errors.append(f"scoring.interpretations[{index}]: بازه عددی معتبر نیست.")
            continue
        if minimum > maximum:
            errors.append(f"scoring.interpretations[{index}]: حداقل از حداکثر بیشتر است.")
        normalized_ranges.append(
            {
                "key": _clean_key(item.get("key"), f"range_{index + 1}"),
                "min": minimum,
                "max": maximum,
                "title": str(item.get("title", "")).strip()[:200],
                "body": str(item.get("body", "")).strip()[:1200],
                "color": str(item.get("color", "#0f4c45"))[:20],
            }
        )
    ordered = sorted(normalized_ranges, key=lambda item: (item["min"], item["max"]))
    for previous, current in zip(ordered, ordered[1:]):
        if current["min"] <= previous["max"]:
            errors.append(
                f"scoring.interpretations: بازه «{previous['key']}» و «{current['key']}» هم‌پوشانی دارند."
            )
    return {
        "mode": mode,
        "show_score": bool(scoring.get("show_score", True)),
        "show_interpretation": bool(scoring.get("show_interpretation", True)),
        "subscales": _json_list(scoring.get("subscales", [])),
        "interpretations": normalized_ranges,
    }, errors


def validate_ai_contract(payload):
    errors = []
    if not isinstance(payload, dict):
        return None, ["$: ریشه JSON باید شیء باشد."]
    if payload.get("contract") != AI_CONTRACT:
        errors.append(f"contract: مقدار باید دقیقاً {AI_CONTRACT} باشد.")
    meta = _json_dict(payload.get("meta"))
    title = str(meta.get("title", "")).strip()[:160]
    if len(title) < 3:
        errors.append("meta.title: عنوان حداقل سه نویسه لازم دارد.")
    form_type = meta.get("type", "assessment")
    if form_type not in FORM_TYPES:
        errors.append("meta.type: نوع فرم پشتیبانی نمی‌شود.")
        form_type = "assessment"
    sections = payload.get("sections", [])
    if not isinstance(sections, list):
        errors.append("sections: باید آرایه باشد.")
        sections = []
    if len(sections) > 100:
        errors.append("sections: حداکثر ۱۰۰ بخش مجاز است.")
        sections = sections[:100]
    flattened = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            errors.append(f"sections[{section_index}]: باید شیء باشد.")
            continue
        section_title = str(section.get("title", "")).strip()[:200]
        if section_index or section_title:
            flattened.append(
                {
                    **default_field("section", len(flattened) + 1),
                    "id": _clean_key(section.get("id"), f"section_{section_index + 1}"),
                    "key": _clean_key(section.get("id"), f"section_{section_index + 1}"),
                    "label": section_title or f"بخش {section_index + 1}",
                    "description": str(section.get("description", ""))[:1000],
                }
            )
        fields = section.get("fields", [])
        if not isinstance(fields, list):
            errors.append(f"sections[{section_index}].fields: باید آرایه باشد.")
            continue
        flattened.extend(fields)
    if not sections and isinstance(payload.get("fields"), list):
        flattened = payload["fields"]
    fields, field_errors = normalize_schema(flattened)
    errors.extend(field_errors)
    scoring, scoring_errors = normalize_scoring(payload.get("scoring", {}))
    errors.extend(scoring_errors)
    normalized = {
        "title": title,
        "slug": _clean_key(meta.get("slug"), "ai-form").lower().replace("_", "-"),
        "description": str(meta.get("description", "")).strip()[:500],
        "form_type": form_type,
        "use_case": str(meta.get("use_case", "general")).strip()[:80] or "general",
        "fields": fields,
        "settings": normalize_settings(payload.get("settings", {})),
        "scoring": scoring,
    }
    return normalized, errors


def form_to_ai_contract(form):
    sections = []
    current = {"id": "general", "title": "بخش اصلی", "description": "", "fields": []}
    for field in form.fields:
        if field.get("type") == "section":
            if current["fields"] or sections:
                sections.append(current)
            current = {
                "id": field.get("key", field.get("id")),
                "title": field.get("label", "بخش جدید"),
                "description": field.get("description", ""),
                "fields": [],
            }
        else:
            current["fields"].append(field)
    if current["fields"] or not sections:
        sections.append(current)
    return {
        "contract": AI_CONTRACT,
        "meta": {
            "title": form.title,
            "slug": form.slug,
            "type": form.form_type,
            "use_case": form.use_case,
            "description": form.description,
            "language": "fa",
            "direction": "rtl",
            "version": form.version,
        },
        "settings": form.settings,
        "sections": sections,
        "scoring": form.scoring,
    }


def evaluate_condition(field, answers):
    logic = field.get("conditional_logic") or {}
    if not logic.get("enabled") or not logic.get("rules"):
        return True
    outcomes = []
    for rule in logic["rules"]:
        actual = answers.get(rule.get("field"))
        expected = rule.get("value")
        operator = rule.get("operator", "equals")
        if operator == "not_equals":
            matched = str(actual) != str(expected)
        elif operator == "contains":
            matched = str(expected) in (actual if isinstance(actual, list) else str(actual or ""))
        elif operator == "greater_than":
            try: matched = float(actual) > float(expected)
            except (TypeError, ValueError): matched = False
        elif operator == "less_than":
            try: matched = float(actual) < float(expected)
            except (TypeError, ValueError): matched = False
        elif operator == "is_empty":
            matched = actual in (None, "", [])
        elif operator == "is_not_empty":
            matched = actual not in (None, "", [])
        else:
            matched = str(actual) == str(expected)
        outcomes.append(matched)
    matched = any(outcomes) if logic.get("match") == "any" else all(outcomes)
    return not matched if logic.get("action") == "hide" else matched


def validate_answers(fields, answers, final=False):
    errors = []
    for field in fields:
        if field.get("type") in NON_INPUT_TYPES or not evaluate_condition(field, answers):
            continue
        value = answers.get(field.get("key"))
        if final and field.get("type") == "captcha" and str(value).strip() != "9":
            errors.append(f"پاسخ بررسی انسانی «{field.get('label')}» صحیح نیست.")
            continue
        if final and field.get("required") and value in (None, "", []):
            errors.append(f"فیلد «{field.get('label')}» الزامی است.")
        validation = field.get("validation") or {}
        if value in (None, "", []):
            continue
        if isinstance(value, str):
            minimum_length = validation.get("min_length")
            maximum_length = validation.get("max_length")
            if minimum_length and len(value) < int(minimum_length):
                errors.append(f"پاسخ «{field.get('label')}» کوتاه‌تر از حد مجاز است.")
            if maximum_length and len(value) > int(maximum_length):
                errors.append(f"پاسخ «{field.get('label')}» بلندتر از حد مجاز است.")
            pattern = validation.get("pattern")
            if pattern:
                try:
                    if not re.fullmatch(pattern, value):
                        errors.append(f"قالب پاسخ «{field.get('label')}» معتبر نیست.")
                except re.error:
                    errors.append(f"الگوی اعتبارسنجی «{field.get('label')}» معتبر نیست.")
        if field.get("type") in {"number", "scale", "rating", "slider", "quantity"}:
            try:
                numeric = float(value)
                if validation.get("min") is not None and numeric < float(validation["min"]):
                    errors.append(f"مقدار «{field.get('label')}» کمتر از حد مجاز است.")
                if validation.get("max") is not None and numeric > float(validation["max"]):
                    errors.append(f"مقدار «{field.get('label')}» بیشتر از حد مجاز است.")
            except (TypeError, ValueError):
                errors.append(f"مقدار «{field.get('label')}» باید عددی باشد.")
    return errors


def score_answers(fields, answers, scoring):
    mode = (scoring or {}).get("mode", "manual")
    if mode == "manual":
        return None, {}, None
    total = 0.0
    subscales = {}
    for field in fields:
        if field.get("type") in NON_INPUT_TYPES or not evaluate_condition(field, answers):
            continue
        value = answers.get(field.get("key"))
        if value in (None, "", []):
            continue
        field_scoring = field.get("scoring") or {}
        option_scores = {
            str(option.get("value")): float(option.get("score", 0) or 0)
            for option in field.get("options", [])
        }
        values = value if isinstance(value, list) else [value]
        if option_scores:
            raw = sum(option_scores.get(str(item), 0) for item in values)
        else:
            try: raw = float(value)
            except (TypeError, ValueError): raw = 0
        if field_scoring.get("reverse"):
            validation = field.get("validation") or {}
            minimum = float(validation.get("min", 1) or 1)
            maximum = float(validation.get("max", 5) or 5)
            raw = maximum + minimum - raw
        weight = float(field_scoring.get("weight", 1) or 1) if mode == "weighted" else 1
        score = raw * weight
        total += score
        subscale = field_scoring.get("subscale")
        if subscale:
            subscales[subscale] = subscales.get(subscale, 0) + score
    total = round(total, 2)
    subscales = {key: round(value, 2) for key, value in subscales.items()}
    result = next(
        (
            item for item in (scoring or {}).get("interpretations", [])
            if float(item.get("min", -math.inf)) <= total <= float(item.get("max", math.inf))
        ),
        None,
    )
    return total, subscales, result


def allowed_upload(field, filename, mime_type, size_bytes, header_bytes=b""):
    validation = field.get("validation") or {}
    extension = Path(secure_filename(filename or "")).suffix.lower().lstrip(".")
    allowed = set(validation.get("allowed_extensions") or DEFAULT_UPLOAD_EXTENSIONS.get(field.get("type"), set()))
    max_bytes = min(8, float(validation.get("max_size_mb", 5) or 5)) * 1024 * 1024
    if not extension or extension not in allowed:
        return False, "پسوند فایل مجاز نیست."
    if size_bytes > max_bytes:
        return False, "حجم فایل از محدودیت این فیلد بیشتر است."
    expected_mimes = MIME_BY_EXTENSION.get(extension, set())
    if expected_mimes and mime_type not in expected_mimes:
        return False, "نوع MIME فایل با پسوند آن سازگار نیست."
    if expected_mimes and not file_signature_matches(extension, header_bytes):
        return False, "محتوای واقعی فایل با پسوند اعلام‌شده سازگار نیست."
    return True, extension


def storage_filename(extension):
    return f"{secrets.token_hex(24)}.{extension}"
