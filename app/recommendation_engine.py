from .models import (
    ChildProfileSnapshot,
    HomeActionOutcome,
    ParentingStyleAssessment,
    PersonalizationRule,
    RecommendationRun,
)


PROFILE_LABELS = {
    "anger_patterns": {
        "explosion": "واکنش سریع و پرصدا",
        "withdrawal": "کناره‌گیری و سکوت",
        "crying": "گریه و درماندگی",
        "arguing": "بحث طولانی و چانه‌زنی",
        "mixed": "الگوی متغیر",
    },
    "triggers": {
        "direct_pressure": "فشار و دستور مستقیم",
        "sudden_change": "تغییر ناگهانی برنامه",
        "fatigue": "خستگی یا گرسنگی",
        "screen_limit": "محدودشدن موبایل و بازی",
        "criticism": "انتقاد یا مقایسه",
        "sibling_conflict": "تعارض با خواهر یا برادر",
    },
    "calming": {
        "quiet_space": "فضای آرام و خلوت",
        "conversation": "گفت‌وگوی آرام",
        "movement": "حرکت و فعالیت بدنی",
        "time": "زمان کوتاه برای فروکش هیجان",
        "connection": "تماس عاطفی و اطمینان‌بخشی",
        "structured_choice": "دادن دو انتخاب محدود",
    },
    "priorities": {
        "anger": "خشم و تعارض",
        "screen": "موبایل و فضای مجازی",
        "school": "درس و مدرسه",
        "motivation": "انگیزه و مسئولیت",
        "honesty": "صداقت و اعتماد",
        "friends": "دوستان و ارتباط اجتماعی",
    },
    "previous_outcomes": {
        "helped": "اقدام قبلی کمک‌کننده بود",
        "neutral": "اقدام قبلی تغییر محسوسی نداشت",
        "worsened": "اقدام قبلی تنش را بیشتر کرد",
        "not_done": "اقدام قبلی اجرا نشد",
    },
}


def _latest_snapshot(user_id, child_id, profile_type):
    return (
        ChildProfileSnapshot.query.filter_by(
            user_id=user_id,
            child_id=child_id,
            profile_type=profile_type,
        )
        .order_by(ChildProfileSnapshot.version_no.desc())
        .first()
    )


def collect_context(user_id, child, topic_id):
    initial = _latest_snapshot(user_id, child.id, "initial")
    relationship = _latest_snapshot(user_id, child.id, "relationship")
    style = (
        ParentingStyleAssessment.query.filter_by(user_id=user_id, child_id=child.id)
        .order_by(ParentingStyleAssessment.created_at.desc())
        .first()
    )
    previous = (
        HomeActionOutcome.query.join(RecommendationRun)
        .filter(
            RecommendationRun.user_id == user_id,
            RecommendationRun.child_id == child.id,
            RecommendationRun.topic_id == topic_id,
        )
        .order_by(HomeActionOutcome.created_at.desc())
        .first()
    )
    answers = initial.answers if initial else {}
    relationship_summary = relationship.summary if relationship else {}
    return {
        "child_id": child.id,
        "child_name": child.name,
        "profile_version": initial.version_no if initial else None,
        "relationship_version": relationship.version_no if relationship else None,
        "style_version": style.instrument_version if style else None,
        "anger_pattern": answers.get("anger_pattern"),
        "triggers": answers.get("triggers", []),
        "calming": answers.get("calming", []),
        "priorities": answers.get("priorities", []),
        "style": style.dominant_style if style else None,
        "relationship_score": relationship_summary.get("score"),
        "previous_outcome": previous.outcome if previous else None,
        "previous_child_response": previous.child_response if previous else None,
        "profile_complete": bool(initial),
        "relationship_complete": bool(relationship),
        "style_complete": bool(style),
    }


def _condition_matches(rule, context):
    if not rule.min_severity <= context["severity"] <= rule.max_severity:
        return False
    conditions = rule.conditions
    mappings = {
        "anger_patterns": [context.get("anger_pattern")] if context.get("anger_pattern") else [],
        "triggers": context.get("triggers", []),
        "calming": context.get("calming", []),
        "priorities": context.get("priorities", []),
        "styles": [context.get("style")] if context.get("style") else [],
        "previous_outcomes": (
            [context.get("previous_outcome")] if context.get("previous_outcome") else []
        ),
    }
    for key, actual in mappings.items():
        expected = conditions.get(key, [])
        if expected and not set(expected).intersection(actual):
            return False
    relationship_score = context.get("relationship_score")
    minimum = conditions.get("relationship_score_min")
    maximum = conditions.get("relationship_score_max")
    if minimum is not None and (relationship_score is None or relationship_score < minimum):
        return False
    if maximum is not None and (relationship_score is None or relationship_score > maximum):
        return False
    return True


def _matched_reasons(rule, context):
    reasons = []
    if rule.reason_template:
        reasons.append(rule.reason_template.replace("{child}", context["child_name"]))
    conditions = rule.conditions
    for key, context_key in (
        ("anger_patterns", "anger_pattern"),
        ("triggers", "triggers"),
        ("calming", "calming"),
        ("priorities", "priorities"),
    ):
        expected = conditions.get(key, [])
        actual = context.get(context_key, [])
        if isinstance(actual, str):
            actual = [actual]
        matched = [item for item in expected if item in actual]
        if matched:
            labels = PROFILE_LABELS.get(key, {})
            reason_prefix = {
                "anger_patterns": "الگوی واکنش ثبت‌شده",
                "triggers": "محرک مهم",
                "calming": "راه آرام‌شدن مؤثر",
                "priorities": "اولویت فعلی خانواده",
            }[key]
            reasons.append(f"{reason_prefix}: {'، '.join(labels.get(item, item) for item in matched)}")
    if context.get("style") and context["style"] in conditions.get("styles", []):
        reasons.append(f"نتیجه آخر سبک والدگری در این رابطه: {context['style']}")
    previous = context.get("previous_outcome")
    if previous and previous in conditions.get("previous_outcomes", []):
        reasons.append(PROFILE_LABELS["previous_outcomes"].get(previous, previous))
    reasons.append(f"شدت انتخاب‌شده: سطح {context['severity']} از ۵")
    if not context.get("profile_complete"):
        reasons.append("نمای فرزند هنوز کامل نیست؛ پیشنهاد فعلی محافظه‌کارانه و عمومی‌تر است.")
    return reasons[:6]


def _render(value, context):
    return (value or "").replace("{child}", context["child_name"])


def build_personalized_recommendation(user_id, child, level):
    context = collect_context(user_id, child, level.topic_id)
    context["severity"] = level.level
    context["level_id"] = level.id
    context["topic_id"] = level.topic_id
    rules = (
        PersonalizationRule.query.filter_by(topic_id=level.topic_id, status="published")
        .order_by(PersonalizationRule.priority.desc(), PersonalizationRule.id.asc())
        .all()
    )
    matched_rule = next((rule for rule in rules if _condition_matches(rule, context)), None)
    if matched_rule:
        return {
            "rule": matched_rule,
            "context": context,
            "title": _render(matched_rule.recommendation_title, context),
            "action_text": _render(matched_rule.recommendation_text, context),
            "reasons": _matched_reasons(matched_rule, context),
            "avoid_text": _render(matched_rule.avoid_text, context) or level.wrong_action,
            "home_action": _render(matched_rule.home_action, context),
            "next_step_text": _render(matched_rule.next_step_text, context),
            "skill": matched_rule.skill,
        }
    return {
        "rule": None,
        "context": context,
        "title": "مکث، همدلی و مرز روشن",
        "action_text": level.recommended_action,
        "reasons": [
            f"برای موضوع «{level.topic.title}» و شدت {level.level} هنوز قاعده اختصاصی منتشر نشده است.",
            "پیشنهاد پایه این سطح نمایش داده می‌شود.",
        ],
        "avoid_text": level.wrong_action,
        "home_action": "یک بار پاسخ پیشنهادی را اجرا و نتیجه را کوتاه ثبت کنید.",
        "next_step_text": "پس از ثبت نتیجه، پیشنهاد بعدی با سابقه اقدام تنظیم می‌شود.",
        "skill": None,
    }
