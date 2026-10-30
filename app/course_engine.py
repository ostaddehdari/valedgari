import json

from .extensions import db
from .models import (
    Course,
    CourseChapter,
    CourseEnrollment,
    CourseUnit,
    ParentingStyleAssessment,
    RecommendationRun,
    SkillProgress,
)


COURSE_LEVELS = {
    "foundation": "پایه",
    "intermediate": "میانی",
    "advanced": "پیشرفته",
}
COURSE_STATUSES = {"draft", "published", "archived"}
UNIT_TYPES = {
    "text": "متن آموزشی",
    "video": "ویدئو",
    "audio": "صوت",
    "file": "فایل",
    "link": "لینک",
    "quiz": "آزمون",
}
STYLE_TAGS = {
    "authoritative": "مقتدرانه",
    "authoritarian": "مستبدانه",
    "permissive": "سهل‌گیرانه",
    "uninvolved": "غافلانه",
    "general": "عمومی",
}


def _integer(value, default=0, minimum=0, maximum=1000000000):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def parse_course_structure(raw):
    errors = []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            return [], ["ساختار فصل‌ها JSON معتبر نیست."]
    if not isinstance(raw, list):
        return [], ["ساختار دوره باید آرایه‌ای از فصل‌ها باشد."]
    if len(raw) > 50:
        errors.append("هر دوره حداکثر ۵۰ فصل می‌تواند داشته باشد.")
        raw = raw[:50]
    chapters = []
    total_units = 0
    for chapter_index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"فصل {chapter_index + 1} معتبر نیست.")
            continue
        title = str(item.get("title", "")).strip()[:180]
        if len(title) < 2:
            errors.append(f"عنوان فصل {chapter_index + 1} الزامی است.")
        raw_units = item.get("units", [])
        if not isinstance(raw_units, list):
            errors.append(f"درس‌های فصل {chapter_index + 1} باید آرایه باشند.")
            raw_units = []
        units = []
        for unit_index, unit in enumerate(raw_units):
            if total_units >= 200:
                if "هر دوره حداکثر ۲۰۰ درس می‌تواند داشته باشد." not in errors:
                    errors.append("هر دوره حداکثر ۲۰۰ درس می‌تواند داشته باشد.")
                break
            total_units += 1
            if not isinstance(unit, dict):
                errors.append(f"درس {unit_index + 1} فصل {chapter_index + 1} معتبر نیست.")
                continue
            unit_type = str(unit.get("type", "text"))
            if unit_type not in UNIT_TYPES:
                errors.append(f"نوع درس «{unit_type}» پشتیبانی نمی‌شود.")
                unit_type = "text"
            unit_title = str(unit.get("title", "")).strip()[:180]
            if len(unit_title) < 2:
                errors.append(f"عنوان درس {unit_index + 1} فصل {chapter_index + 1} الزامی است.")
            units.append(
                {
                    "id": _integer(unit.get("id"), None),
                    "title": unit_title,
                    "type": unit_type,
                    "body": str(unit.get("body", "")).strip()[:20000],
                    "source_url": str(unit.get("source_url", "")).strip()[:700],
                    "duration": _integer(unit.get("duration"), 5, 1, 240),
                    "is_preview": bool(unit.get("is_preview", False)),
                    "form_id": _integer(unit.get("form_id"), None),
                }
            )
        chapters.append(
            {
                "id": _integer(item.get("id"), None),
                "title": title,
                "description": str(item.get("description", "")).strip()[:700],
                "units": units,
            }
        )
    return chapters, errors


def sync_course_structure(course, structure):
    existing_chapters = {item.id: item for item in course.chapters}
    retained_chapters = set()
    retained_units = set()
    for chapter_order, item in enumerate(structure, 1):
        chapter = existing_chapters.get(item.get("id"))
        if not chapter:
            chapter = CourseChapter(
                course_id=course.id,
                title=item["title"],
                description=item["description"],
                sort_order=chapter_order,
                status="active",
            )
            db.session.add(chapter)
            db.session.flush()
        retained_chapters.add(chapter.id)
        chapter.title = item["title"]
        chapter.description = item["description"]
        chapter.sort_order = chapter_order
        chapter.status = "active"
        existing_units = {unit.id: unit for unit in chapter.units}
        for unit_order, unit_data in enumerate(item["units"], 1):
            unit = existing_units.get(unit_data.get("id"))
            if not unit:
                unit = CourseUnit(
                    chapter_id=chapter.id,
                    title=unit_data["title"],
                    unit_type=unit_data["type"],
                    body=unit_data["body"],
                    source_url=unit_data["source_url"],
                    duration_minutes=unit_data["duration"],
                    is_preview=unit_data["is_preview"],
                    form_id=unit_data["form_id"] if unit_data["type"] == "quiz" else None,
                    sort_order=unit_order,
                    status="active",
                )
                db.session.add(unit)
                db.session.flush()
            retained_units.add(unit.id)
            unit.title = unit_data["title"]
            unit.unit_type = unit_data["type"]
            unit.body = unit_data["body"]
            unit.source_url = unit_data["source_url"]
            unit.duration_minutes = unit_data["duration"]
            unit.is_preview = unit_data["is_preview"]
            unit.form_id = unit_data["form_id"] if unit_data["type"] == "quiz" else None
            unit.sort_order = unit_order
            unit.status = "active"
        for unit in chapter.units:
            if unit.id not in retained_units:
                unit.status = "archived"
    for chapter in course.chapters:
        if chapter.id not in retained_chapters:
            chapter.status = "archived"
            for unit in chapter.units:
                unit.status = "archived"


def structure_payload(course):
    return [
        {
            "id": chapter.id,
            "title": chapter.title,
            "description": chapter.description,
            "units": [
                {
                    "id": unit.id,
                    "title": unit.title,
                    "type": unit.unit_type,
                    "body": unit.body,
                    "source_url": unit.source_url,
                    "duration": unit.duration_minutes,
                    "is_preview": unit.is_preview,
                    "form_id": unit.form_id,
                }
                for unit in chapter.units if unit.status == "active"
            ],
        }
        for chapter in course.chapters if chapter.status == "active"
    ]


def enrollment_for(course_id, user_id, child_id=None):
    query = CourseEnrollment.query.filter_by(course_id=course_id, user_id=user_id)
    if child_id is None:
        return query.order_by(CourseEnrollment.enrolled_at.desc()).first()
    return query.filter_by(child_id=child_id).first()


def recommended_courses(user_id, child):
    published = Course.query.filter_by(status="published").order_by(
        Course.is_featured.desc(), Course.sort_order, Course.id
    ).all()
    if not published:
        return []
    child_id = child.id if child else None
    incomplete_skill_ids = {
        item.module_id for item in SkillProgress.query.filter_by(
            user_id=user_id, child_id=child_id
        ).all() if item.percent < 100
    } if child_id else set()
    recommendation_skill_ids = {
        item.skill_module_id for item in RecommendationRun.query.filter_by(
            user_id=user_id, child_id=child_id
        ).all() if item.skill_module_id
    } if child_id else set()
    recommendation_topic_ids = {
        item.topic_id for item in RecommendationRun.query.filter_by(
            user_id=user_id, child_id=child_id
        ).all()
    } if child_id else set()
    style = (
        ParentingStyleAssessment.query.filter_by(user_id=user_id, child_id=child_id)
        .order_by(ParentingStyleAssessment.created_at.desc()).first()
        if child_id else None
    )
    style_text = (style.dominant_style or "") if style else ""
    ranked = []
    for course in published:
        reasons = []
        score = 0
        skill_ids = {item.id for item in course.skills}
        topic_ids = {item.id for item in course.topics}
        if skill_ids & recommendation_skill_ids:
            score += 5
            reasons.append("با پیشنهادهای فعال این فرزند هم‌راستاست")
        if skill_ids & incomplete_skill_ids:
            score += 3
            reasons.append("مهارتی نیمه‌تمام را تقویت می‌کند")
        if topic_ids & recommendation_topic_ids:
            score += 4
            reasons.append("به موقعیت پرتکرار ثبت‌شده مرتبط است")
        if style_text and any(tag in style_text for tag in course.style_tags):
            score += 2
            reasons.append("با نتیجه سبک والدگری مرتبط است")
        if course.is_featured:
            score += 1
        if not reasons:
            reasons.append("برای تقویت عمومی مسیر والدگری پیشنهاد می‌شود")
        ranked.append({"course": course, "score": score, "reasons": reasons})
    return sorted(ranked, key=lambda item: (-item["score"], item["course"].sort_order))
