import json
import re

from .learning_path import TOPIC_SKILL, latest_child_profile
from .models import (
    CourseEnrollment,
    FormResponse,
    MicroLesson,
    PersonalizationRule,
    RecommendationRun,
    SafetyProtocol,
    ScenarioNarrativeAttempt,
    ScenarioTopic,
    SkillModule,
    WeeklyPlan,
)


TOPIC_KEYWORDS = {
    "anger": ["خشم", "عصبانی", "پرخاش", "داد", "فریاد", "کتک", "لجباز", "دعوا"],
    "screen-time": ["موبایل", "گوشی", "بازی", "اینترنت", "تبلت", "صفحه", "اینستا"],
    "school-drop": ["درس", "مدرسه", "نمره", "تکلیف", "امتحان", "تحصیل", "انگیزه"],
    "lying": ["دروغ", "پنهان", "حقیقت", "اعتماد", "راست نمی"],
    "friends": ["دوست", "رفیق", "همکلاسی", "جمع", "قلدری", "تنها"],
}

OUT_OF_SCOPE_KEYWORDS = [
    "چه دارویی",
    "دوز دارو",
    "نسخه پزشکی",
    "تشخیص بیماری",
    "تشخیص روانی",
    "حکم دادگاه",
    "قرارداد حقوقی",
    "خرید سهام",
    "سیگنال ارز",
]

POLICY_BYPASS_KEYWORDS = [
    "دستورها را نادیده",
    "قوانین را نادیده",
    "بدون محدودیت پاسخ",
    "نقش جدید بگیر",
    "منبع را جعل",
]


def normalize_text(value):
    value = (value or "").strip().lower()
    value = value.translate(str.maketrans("يكى", "یکی"))
    return re.sub(r"\s+", " ", value)


def _active_plan(user_id, child_id):
    return (
        WeeklyPlan.query.filter(
            WeeklyPlan.user_id == user_id,
            WeeklyPlan.child_id == child_id,
            WeeklyPlan.status.in_(["active", "awaiting_review"]),
        )
        .order_by(WeeklyPlan.created_at.desc())
        .first()
    )


def _detect_safety_protocol(text):
    protocols = (
        SafetyProtocol.query.filter_by(status="published")
        .order_by(SafetyProtocol.priority.desc())
        .all()
    )
    for protocol in protocols:
        if any(normalize_text(keyword) in text for keyword in protocol.trigger_keywords):
            return protocol
    return None


def _classify_topic(text, active_plan=None):
    scored = []
    for slug, keywords in TOPIC_KEYWORDS.items():
        score = sum(normalize_text(keyword) in text for keyword in keywords)
        if score:
            scored.append((score, slug))
    if scored:
        scored.sort(reverse=True)
        return ScenarioTopic.query.filter_by(slug=scored[0][1], is_published=True).first()
    return active_plan.topic if active_plan else None


def _published_lesson(topic):
    skill_slug = TOPIC_SKILL.get(topic.slug, "active-listening")
    return (
        MicroLesson.query.join(MicroLesson.module)
        .filter(MicroLesson.status == "published", SkillModule.slug == skill_slug)
        .order_by(MicroLesson.sort_order)
        .first()
    )


def _base_rule(topic_id):
    rules = (
        PersonalizationRule.query.filter_by(topic_id=topic_id, status="published")
        .order_by(PersonalizationRule.priority.asc(), PersonalizationRule.id.asc())
        .all()
    )
    return next((item for item in rules if not item.conditions), rules[0] if rules else None)


def _latest_recommendation(user_id, child_id, topic_id):
    return (
        RecommendationRun.query.filter_by(
            user_id=user_id, child_id=child_id, topic_id=topic_id
        )
        .order_by(RecommendationRun.created_at.desc())
        .first()
    )


def _safety_response(protocol, child):
    steps = "\n".join(f"{index}. {item}" for index, item in enumerate(protocol.immediate_steps, 1))
    body = (
        f"{protocol.response_title}\n\n"
        f"{protocol.response_text}\n\n"
        f"قدم‌های فوری:\n{steps}\n\n"
        "این پاسخ جایگزین خدمات اضطراری یا ارزیابی حضوری نیست. محل زندگی و وضعیت دقیق شما را نمی‌دانم، بنابراین شماره تماس حدس نمی‌زنم."
    )
    return {
        "decision_type": "safety",
        "body": body,
        "topic": None,
        "sources": [
            {
                "kind": "safety_protocol",
                "title": protocol.title,
                "version": protocol.version,
                "source_id": protocol.id,
            }
        ],
        "context": {"child_id": child.id, "child_name": child.name, "protocol": protocol.slug},
    }


def build_assistant_response(user_id, child, user_text):
    text = normalize_text(user_text)
    protocol = _detect_safety_protocol(text)
    if protocol:
        return _safety_response(protocol, child)

    if any(item in text for item in POLICY_BYPASS_KEYWORDS):
        return {
            "decision_type": "policy_boundary",
            "body": (
                "نمی‌توانم محدودیت‌های علمی و ایمنی والدیار را کنار بگذارم یا منبعی را جعل کنم. "
                "اگر مسئله والدگری مشخصی دارید، آن را با موقعیت واقعی و بدون اطلاعات هویتی حساس توضیح دهید."
            ),
            "topic": None,
            "sources": [],
            "context": {"child_id": child.id, "child_name": child.name},
        }

    if any(item in text for item in OUT_OF_SCOPE_KEYWORDS):
        return {
            "decision_type": "out_of_scope",
            "body": (
                "این درخواست به تشخیص، تجویز یا مشاوره تخصصی خارج از دامنه والدیار مربوط است. "
                "من نمی‌توانم دارو، تشخیص پزشکی/روان‌پزشکی یا نظر حقوقی ارائه کنم. "
                "برای این بخش از متخصص واجد صلاحیت کمک بگیرید؛ می‌توانم فقط برای آماده‌کردن یک گفت‌وگوی آرام با فرزندتان کمک کنم."
            ),
            "topic": None,
            "sources": [],
            "context": {"child_id": child.id, "child_name": child.name},
        }

    active_plan = _active_plan(user_id, child.id)
    topic = _classify_topic(text, active_plan)
    if not topic:
        return {
            "decision_type": "clarification",
            "body": (
                f"برای اینکه پاسخ به {child.name} مربوط باشد، موقعیت را کمی مشخص‌تر کنید: "
                "خشم، موبایل، مدرسه، صداقت یا رابطه با دوستان؟ همچنین بگویید شدت آن از ۱ تا ۵ چقدر است."
            ),
            "topic": None,
            "sources": [],
            "context": {"child_id": child.id, "child_name": child.name},
        }

    profile = latest_child_profile(user_id, child.id)
    lesson = _published_lesson(topic)
    recommendation = _latest_recommendation(user_id, child.id, topic.id)
    rule = _base_rule(topic.id)
    current_action = active_plan.current_action if active_plan and active_plan.topic_id == topic.id else None
    latest_form = (
        FormResponse.query.filter_by(user_id=user_id, child_id=child.id, status="submitted")
        .order_by(FormResponse.submitted_at.desc(), FormResponse.created_at.desc()).first()
    )
    latest_scenario = (
        ScenarioNarrativeAttempt.query.join(ScenarioNarrativeAttempt.narrative)
        .filter(ScenarioNarrativeAttempt.user_id == user_id,
                ScenarioNarrativeAttempt.child_id == child.id,
                ScenarioNarrativeAttempt.narrative.has(topic_id=topic.id))
        .order_by(ScenarioNarrativeAttempt.created_at.desc()).first()
    )
    active_course = (
        CourseEnrollment.query.filter_by(user_id=user_id, child_id=child.id, status="active")
        .order_by(CourseEnrollment.enrolled_at.desc()).first()
    )
    action_text = (
        current_action.instructions
        if current_action
        else recommendation.action_text
        if recommendation
        else rule.recommendation_text
        if rule
        else topic.description
    )
    practice = (
        recommendation.home_action
        if recommendation
        else lesson.practice
        if lesson
        else "یک اقدام کوچک اجرا و نتیجه قابل مشاهده را ثبت کنید."
    )
    avoid = (
        recommendation.avoid_text
        if recommendation
        else rule.avoid_text
        if rule
        else "از تهدید، تحقیر و بحث طولانی در اوج تنش پرهیز کنید."
    )
    context_reason = []
    if profile:
        summary = profile.summary
        if summary.get("anger_pattern"):
            context_reason.append(f"الگوی واکنش ثبت‌شده: {summary['anger_pattern']}")
        if summary.get("calming"):
            context_reason.append(f"راه آرام‌شدن گزارش‌شده: {summary['calming'][0]}")
    if current_action:
        context_reason.append(f"قدم جاری برنامه هفتگی: {current_action.title}")
    elif recommendation:
        context_reason.append(f"آخرین پیشنهاد ذخیره‌شده: {recommendation.title}")
    if not context_reason:
        context_reason.append("پیشنهاد پایه محتوای منتشرشده این موضوع")
    if latest_scenario:
        context_reason.append(f"آخرین تمرین همین موضوع: {latest_scenario.score} از ۱۰۰")
    if active_course and topic.id in {item.id for item in active_course.course.topics}:
        context_reason.append(f"دوره مرتبط در حال یادگیری: {active_course.course.title}")

    body = (
        f"برای موقعیت «{topic.title}» با {child.name}، بهتر است از یک قدم کوتاه و قابل مشاهده شروع کنید.\n\n"
        f"پیشنهاد اکنون:\n{action_text}\n\n"
        f"تمرین کوچک:\n{practice}\n\n"
        f"فعلاً انجام ندهید:\n{avoid}\n\n"
        f"چرا این پاسخ؟\n- " + "\n- ".join(context_reason) +
        "\n\nپس از اجرا، نتیجه را در برنامه والدیار ثبت کنید تا پیشنهاد بعدی بر اساس تجربه واقعی تنظیم شود."
    )
    sources = []
    if current_action:
        sources.append(
            {
                "kind": "weekly_plan",
                "title": current_action.title,
                "version": 1,
                "source_id": current_action.id,
            }
        )
    if recommendation:
        sources.append(
            {
                "kind": "recommendation",
                "title": recommendation.title,
                "version": recommendation.rule_version,
                "source_id": recommendation.id,
            }
        )
    if lesson:
        sources.append(
            {
                "kind": "micro_lesson",
                "title": lesson.title,
                "version": lesson.version,
                "source_id": lesson.id,
            }
        )
    if rule and not recommendation:
        sources.append(
            {
                "kind": "personalization_rule",
                "title": rule.name,
                "version": rule.version,
                "source_id": rule.id,
            }
        )
    if profile:
        sources.append({"kind": "child_profile", "title": "نمای ثبت‌شده فرزند",
                        "version": profile.version_no, "source_id": profile.id})
    if latest_form:
        sources.append({"kind": "form_response", "title": latest_form.form.title,
                        "version": latest_form.form_version, "source_id": latest_form.id})
    if latest_scenario:
        sources.append({"kind": "scenario_attempt", "title": latest_scenario.narrative.title,
                        "version": latest_scenario.narrative.version, "source_id": latest_scenario.id})
    if active_course and topic.id in {item.id for item in active_course.course.topics}:
        sources.append({"kind": "course", "title": active_course.course.title,
                        "version": active_course.course.version, "source_id": active_course.course_id})
    return {
        "decision_type": "grounded",
        "body": body,
        "topic": topic,
        "sources": sources,
        "context": {
            "child_id": child.id,
            "child_name": child.name,
            "profile_version": profile.version_no if profile else None,
            "active_plan_id": active_plan.id if active_plan else None,
            "topic_slug": topic.slug,
        },
    }
