import json
from datetime import date, timedelta

from .extensions import db
from .models import (
    ChildProfileSnapshot,
    DailyAction,
    MicroLesson,
    RecommendationRun,
    ScenarioTopic,
    SkillModule,
    WeeklyPlan,
)


PRIORITY_TOPIC = {
    "anger": "anger",
    "screen": "screen-time",
    "school": "school-drop",
    "motivation": "school-drop",
    "honesty": "lying",
    "friends": "friends",
}

TOPIC_SKILL = {
    "anger": "emotion-regulation",
    "screen-time": "boundaries",
    "school-drop": "motivation",
    "lying": "empathy",
    "friends": "active-listening",
}


def latest_child_profile(user_id, child_id):
    return (
        ChildProfileSnapshot.query.filter_by(
            user_id=user_id, child_id=child_id, profile_type="initial"
        )
        .order_by(ChildProfileSnapshot.version_no.desc())
        .first()
    )


def suggested_topic_for_child(user_id, child):
    profile = latest_child_profile(user_id, child.id)
    priorities = profile.answers.get("priorities", []) if profile else []
    preferred_slug = next(
        (PRIORITY_TOPIC[item] for item in priorities if item in PRIORITY_TOPIC), None
    )
    topic = ScenarioTopic.query.filter_by(slug=preferred_slug, is_published=True).first()
    return topic or ScenarioTopic.query.filter_by(is_published=True).order_by(ScenarioTopic.id).first()


def _lesson_for_skill(skill_slug):
    return (
        MicroLesson.query.join(MicroLesson.module)
        .filter(MicroLesson.status == "published")
        .filter(SkillModule.slug == skill_slug)
        .order_by(MicroLesson.sort_order)
        .first()
    )


def _latest_recommendation(user_id, child_id, topic_id):
    return (
        RecommendationRun.query.filter_by(
            user_id=user_id, child_id=child_id, topic_id=topic_id
        )
        .order_by(RecommendationRun.created_at.desc())
        .first()
    )


def build_weekly_plan(user_id, child, topic, goal_title=""):
    profile = latest_child_profile(user_id, child.id)
    profile_answers = profile.answers if profile else {}
    skill_slug = TOPIC_SKILL.get(topic.slug, "active-listening")
    primary_lesson = _lesson_for_skill(skill_slug)
    regulation_lesson = _lesson_for_skill("emotion-regulation")
    latest_recommendation = _latest_recommendation(user_id, child.id, topic.id)
    priorities = profile_answers.get("priorities", [])
    trigger_labels = (profile.summary.get("triggers", []) if profile else [])[:2]
    calming_labels = (profile.summary.get("calming", []) if profile else [])[:2]
    rationale_parts = [f"موضوع فعال این هفته «{topic.title}» است."]
    if priorities:
        rationale_parts.append("این انتخاب با اولویت ثبت‌شده در نمای فرزند هماهنگ است.")
    if latest_recommendation:
        rationale_parts.append("آخرین برنامه موقعیتی و نتیجه آن در ترتیب تمرین‌ها لحاظ شده است.")
    if not profile:
        rationale_parts.append("نمای فرزند کامل نیست؛ برنامه با تمرین‌های محافظه‌کارانه آغاز می‌شود.")

    start = date.today()
    plan = WeeklyPlan(
        user_id=user_id,
        child_id=child.id,
        topic_id=topic.id,
        status="active",
        goal_title=(goal_title.strip()[:220] or f"یک هفته تمرین آرام‌تر برای {topic.title}"),
        rationale=" ".join(rationale_parts),
        starts_on=start,
        ends_on=start + timedelta(days=6),
        source_context_json=json.dumps(
            {
                "profile_version": profile.version_no if profile else None,
                "priorities": priorities,
                "triggers": profile_answers.get("triggers", []),
                "calming": profile_answers.get("calming", []),
                "recommendation_id": latest_recommendation.id if latest_recommendation else None,
                "topic_slug": topic.slug,
                "skill_slug": skill_slug,
            },
            ensure_ascii=False,
        ),
    )
    db.session.add(plan)
    db.session.flush()

    trigger_text = " و ".join(trigger_labels) if trigger_labels else "لحظه شروع تنش"
    calming_text = " و ".join(calming_labels) if calming_labels else "مکث کوتاه و فضای آرام"
    home_action = (
        latest_recommendation.home_action
        if latest_recommendation
        else "یک گفت‌وگوی کوتاه اجرا کنید و فقط نتیجه قابل مشاهده را یادداشت کنید."
    )
    actions = [
        {
            "type": "lesson",
            "title": primary_lesson.title if primary_lesson else "اصل این هفته را یاد بگیرید",
            "instructions": primary_lesson.body if primary_lesson else topic.description,
            "why": "اول یک اصل کوتاه می‌آموزیم تا تمرین‌های بعدی پراکنده نباشند.",
            "duration": primary_lesson.duration if primary_lesson else 7,
            "lesson": primary_lesson,
        },
        {
            "type": "observe",
            "title": f"محرک‌های {child.name} را فقط مشاهده کنید",
            "instructions": f"امروز هنگام «{trigger_text}» هنوز مداخله را تغییر ندهید؛ زمان، نشانه اولیه و واکنش خودتان را کوتاه ثبت کنید.",
            "why": "دیدن الگو پیش از تغییر آن، از واکنش عجولانه جلوگیری می‌کند.",
            "duration": 5,
        },
        {
            "type": "lesson",
            "title": regulation_lesson.title if regulation_lesson else "مکث پیش از پاسخ",
            "instructions": regulation_lesson.body if regulation_lesson else "پیش از پاسخ سه ثانیه مکث کنید.",
            "why": f"برای {child.name}، شروع از «{calming_text}» احتمال گفت‌وگوی بهتر را بالا می‌برد.",
            "duration": regulation_lesson.duration if regulation_lesson else 5,
            "lesson": regulation_lesson,
        },
        {
            "type": "scenario",
            "title": "پاسخ خود را پیش از موقعیت تمرین کنید",
            "instructions": f"به مسیر «{topic.title}» بروید، شدت نزدیک به واقعیت را انتخاب کنید و جمله پیشنهادی را یک بار با صدای آرام تمرین کنید.",
            "why": "تمرین قبل از تعارض، دسترسی به پاسخ آموخته‌شده را در لحظه واقعی آسان‌تر می‌کند.",
            "duration": 8,
        },
        {
            "type": "home_action",
            "title": f"اقدام واقعی کوچک با {child.name}",
            "instructions": home_action,
            "why": "هدف، اجرای کامل و بی‌نقص نیست؛ یک تجربه کوچک و قابل مشاهده است.",
            "duration": 10,
        },
        {
            "type": "repair",
            "title": "رابطه را بعد از تمرین ترمیم کنید",
            "instructions": "یک نکته مثبت و واقعی درباره تلاش فرزند بازتاب دهید. اگر پاسخ خودتان مناسب نبود، کوتاه و بدون توجیه عذرخواهی کنید.",
            "why": "ترمیم، اعتماد را حفظ می‌کند و اجازه می‌دهد آموزش به جنگ قدرت تبدیل نشود.",
            "duration": 5,
        },
        {
            "type": "review",
            "title": "هفته را مرور و قدم بعدی را انتخاب کنید",
            "instructions": "به نتیجه این هفته، اعتماد خودتان و تغییر رابطه امتیاز بدهید؛ سپس یک تمرکز کوچک برای هفته بعد بنویسید.",
            "why": "مرور نتیجه، مسیر را از توصیه‌های پراکنده به یادگیری پیوسته تبدیل می‌کند.",
            "duration": 7,
        },
    ]
    for index, item in enumerate(actions, 1):
        db.session.add(
            DailyAction(
                weekly_plan_id=plan.id,
                day_index=index,
                action_type=item["type"],
                title=item["title"],
                instructions=item["instructions"],
                why_text=item["why"],
                duration=item["duration"],
                lesson_id=item.get("lesson").id if item.get("lesson") else None,
                topic_id=topic.id if item["type"] == "scenario" else None,
            )
        )
    db.session.flush()
    return plan
