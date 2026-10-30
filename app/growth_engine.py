"""Stage 14 longitudinal growth, explainability, reporting, and return-to-path services."""

from collections import defaultdict
from datetime import datetime, timezone

from .extensions import db
from .models import (
    ChildProfileSnapshot,
    Course,
    CourseAssessmentBinding,
    CourseEnrollment,
    FormResponse,
    GrowthReportSchedule,
    JourneyNotification,
    ParentingStyleAssessment,
    RecommendationRun,
    ScenarioNarrativeAttempt,
    SkillModule,
    SkillProgress,
    WeeklyPlan,
    utcnow,
)


ANONYMOUS_REPORT_MIN_GROUP = 5


def _event(kind, title, occurred_at, source_id, detail="", icon="fa-circle"):
    return {
        "kind": kind,
        "title": title,
        "detail": detail,
        "occurred_at": occurred_at,
        "source_id": source_id,
        "icon": icon,
    }


def build_growth_timeline(user_id, child_id, limit=60):
    """Build one child's longitudinal record from existing immutable source records."""
    events = []
    for item in ChildProfileSnapshot.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("profile", "نمای فرزند به‌روزرسانی شد", item.created_at, item.id,
                             f"نسخه {item.version_no} · {item.profile_type}", "fa-fingerprint"))
    for item in ParentingStyleAssessment.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("assessment", "سنجش سبک والدگری", item.created_at, item.id,
                             item.dominant_style, "fa-chart-simple"))
    for item in FormResponse.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("form", item.form.title, item.submitted_at or item.created_at, item.id,
                             "فرم تکمیل‌شده", "fa-rectangle-list"))
    for item in ScenarioNarrativeAttempt.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("scenario", item.narrative.title, item.created_at, item.id,
                             f"تمرین موقعیت · امتیاز {item.score} از ۱۰۰", "fa-masks-theater"))
    for item in RecommendationRun.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("recommendation", item.title, item.created_at, item.id,
                             item.status, "fa-wand-magic-sparkles"))
    for item in WeeklyPlan.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("plan", item.goal_title, item.created_at, item.id,
                             f"برنامه هفتگی · {item.progress_percent}٪", "fa-calendar-week"))
    for item in CourseEnrollment.query.filter_by(user_id=user_id, child_id=child_id).all():
        events.append(_event("course", item.course.title, item.enrolled_at, item.id,
                             f"دوره · {item.progress_percent}٪", "fa-graduation-cap"))
    events.sort(key=lambda item: item["occurred_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return events[:limit]


def prioritized_skill_needs(user_id, child_id, limit=6):
    """Rank skill needs and retain human-readable evidence for every score."""
    skills = {item.id: item for item in SkillModule.query.all()}
    signals = defaultdict(lambda: {"score": 0, "reasons": [], "sources": []})

    def add(skill_id, points, reason, kind, source_id):
        if skill_id not in skills:
            return
        bucket = signals[skill_id]
        bucket["score"] += points
        if reason not in bucket["reasons"]:
            bucket["reasons"].append(reason)
        bucket["sources"].append({"kind": kind, "source_id": source_id})

    for item in SkillProgress.query.filter_by(user_id=user_id, child_id=child_id).all():
        if item.percent < 100:
            add(item.module_id, max(8, 30 - item.percent // 5),
                f"این مهارت در مسیر یادگیری {item.percent}٪ پیش رفته است.", "skill_progress", item.id)
        else:
            add(item.module_id, -15, "این مهارت در مسیر یادگیری تکمیل شده است.", "skill_progress", item.id)

    attempts = (ScenarioNarrativeAttempt.query.filter_by(user_id=user_id, child_id=child_id)
                .order_by(ScenarioNarrativeAttempt.created_at.desc()).limit(20).all())
    for attempt in attempts:
        reaction = attempt.selected_reaction
        for skill_id in reaction.missing_skill_ids:
            add(skill_id, 24, f"در تمرین «{attempt.narrative.title}» جای تقویت داشته است.",
                "scenario_attempt", attempt.id)
        for skill_id in reaction.present_skill_ids:
            add(skill_id, -6, f"در تمرین «{attempt.narrative.title}» مشاهده شده است.",
                "scenario_attempt", attempt.id)

    for item in RecommendationRun.query.filter_by(user_id=user_id, child_id=child_id).all():
        if item.skill_module_id:
            add(item.skill_module_id, 18, f"پیشنهاد «{item.title}» به این مهارت متصل است.",
                "recommendation", item.id)

    for enrollment in CourseEnrollment.query.filter_by(user_id=user_id, child_id=child_id).all():
        for skill in enrollment.course.skills:
            if enrollment.progress_percent < 100:
                add(skill.id, 12, f"دوره «{enrollment.course.title}» هنوز {enrollment.progress_percent}٪ پیش رفته است.",
                    "course_enrollment", enrollment.id)
            else:
                add(skill.id, -12, f"دوره «{enrollment.course.title}» تکمیل شده است.",
                    "course_enrollment", enrollment.id)

    ranked = []
    for skill_id, bucket in signals.items():
        if bucket["score"] <= 0:
            continue
        ranked.append({
            "skill": skills[skill_id],
            "score": min(100, bucket["score"]),
            "reasons": bucket["reasons"][:4],
            "sources": bucket["sources"],
        })
    return sorted(ranked, key=lambda item: (-item["score"], item["skill"].sort_order))[:limit]


def explainable_course_recommendations(user_id, child_id, limit=4):
    needs = prioritized_skill_needs(user_id, child_id, limit=20)
    need_by_skill = {item["skill"].id: item for item in needs}
    recent_topics = {
        item.topic_id for item in RecommendationRun.query.filter_by(user_id=user_id, child_id=child_id).all()
    }
    active_course_ids = {
        item.course_id for item in CourseEnrollment.query.filter_by(user_id=user_id, child_id=child_id)
        .filter(CourseEnrollment.status.in_(["active", "completed"])).all()
    }
    ranked = []
    for course in Course.query.filter_by(status="published").all():
        if course.id in active_course_ids:
            continue
        reasons, evidence, score = [], [], 0
        for skill in course.skills:
            need = need_by_skill.get(skill.id)
            if need:
                score += need["score"]
                reasons.append(f"مهارت «{skill.title}» در اولویت رشد {need['score']} از ۱۰۰ است.")
                evidence.extend(need["sources"])
        topic_matches = [topic for topic in course.topics if topic.id in recent_topics]
        if topic_matches:
            score += 25 * len(topic_matches)
            reasons.append("با موقعیت‌های ثبت‌شده «" + "، ".join(item.title for item in topic_matches) + "» مرتبط است.")
        if course.is_featured:
            score += 3
        if reasons:
            ranked.append({"course": course, "score": score, "reasons": reasons[:3],
                           "evidence": evidence, "child_id": child_id})
    return sorted(ranked, key=lambda item: (-item["score"], item["course"].sort_order))[:limit]


def course_assessment_change(user_id, child_id, course_id):
    bindings = {item.assessment_type: item for item in CourseAssessmentBinding.query.filter_by(course_id=course_id).all()}
    result = {"available": False, "pre": None, "post": None, "change": None, "message": "سنجش قبل و بعد کامل نشده است."}
    for kind in ("pre", "post"):
        binding = bindings.get(kind)
        if not binding:
            continue
        response = (FormResponse.query.filter_by(user_id=user_id, child_id=child_id,
                                                  form_id=binding.form_id, status="submitted")
                    .order_by(FormResponse.submitted_at.desc(), FormResponse.created_at.desc()).first())
        if response and response.score_total is not None:
            result[kind] = {"score": response.score_total, "response_id": response.id,
                            "form_title": binding.form.title}
    if result["pre"] and result["post"]:
        result["available"] = True
        result["change"] = round(result["post"]["score"] - result["pre"]["score"], 1)
        result["message"] = "این تغییر، نشانه آموزشی است و تشخیص بالینی محسوب نمی‌شود."
    return result


def growth_report_trend(user_id, child_id):
    schedules = (GrowthReportSchedule.query.filter_by(user_id=user_id, child_id=child_id)
                 .order_by(GrowthReportSchedule.created_at).all())
    points = [
        {"score": item.response.score_total, "at": item.completed_at, "schedule_id": item.id}
        for item in schedules
        if item.status == "completed" and item.response and item.response.score_total is not None
    ]
    change = round(points[-1]["score"] - points[0]["score"], 1) if len(points) > 1 else None
    return {
        "scheduled": len(schedules),
        "completed": sum(item.status == "completed" for item in schedules),
        "pending": sum(item.status == "pending" for item in schedules),
        "points": points,
        "change": change,
        "direction": "up" if change is not None and change > 0 else "down" if change is not None and change < 0 else "stable",
    }


def growth_dashboard_state(user_id, child_id):
    needs = prioritized_skill_needs(user_id, child_id)
    courses = explainable_course_recommendations(user_id, child_id)
    plan = (WeeklyPlan.query.filter(WeeklyPlan.user_id == user_id, WeeklyPlan.child_id == child_id,
                                    WeeklyPlan.status.in_(["active", "awaiting_review"]))
            .order_by(WeeklyPlan.created_at.desc()).first())
    if plan and plan.current_action:
        next_step = {"title": plan.current_action.title, "detail": plan.current_action.instructions,
                     "url": f"/dashboard/journey/{plan.id}", "kind": "plan"}
    elif courses:
        course = courses[0]["course"]
        next_step = {"title": f"بررسی دوره «{course.title}»", "detail": courses[0]["reasons"][0],
                     "url": f"/dashboard/courses/{course.slug}", "kind": "course"}
    else:
        next_step = {"title": "یک موقعیت امروز را ثبت کنید",
                     "detail": "با یک موقعیت واقعی، مسیر بعدی دقیق‌تر می‌شود.",
                     "url": "/dashboard/scenario", "kind": "scenario"}
    where = f"{plan.progress_percent}٪ از برنامه «{plan.goal_title}»" if plan else "در حال ساخت خط مبنای رشد"
    why = needs[0]["reasons"][0] if needs else "هنوز داده کافی برای اولویت‌بندی مهارت‌ها ثبت نشده است."
    return {"where": where, "why": why, "next": next_step, "needs": needs, "courses": courses}


def sync_journey_notifications(user_id, child_id):
    candidates = []
    plan = (WeeklyPlan.query.filter(WeeklyPlan.user_id == user_id, WeeklyPlan.child_id == child_id,
                                    WeeklyPlan.status.in_(["active", "awaiting_review"]))
            .order_by(WeeklyPlan.created_at.desc()).first())
    if plan and plan.current_action:
        action = plan.current_action
        candidates.append((f"action:{action.id}", "incomplete_action", "قدم امروز آماده است",
                           action.title, f"/dashboard/journey/{plan.id}", "daily_action", action.id, None))
    for enrollment in CourseEnrollment.query.filter_by(user_id=user_id, child_id=child_id, status="active").all():
        if enrollment.progress_percent < 100:
            candidates.append((f"course:{enrollment.id}:{enrollment.progress_percent}", "next_lesson",
                               "ادامه دوره", f"«{enrollment.course.title}» را از همان‌جا ادامه دهید.",
                               f"/dashboard/courses/{enrollment.course.slug}/learn", "course_enrollment",
                               enrollment.id, None))
    for schedule in GrowthReportSchedule.query.filter_by(user_id=user_id, child_id=child_id, status="pending").all():
        candidates.append((f"report:{schedule.id}", "due_report", "گزارش رشد آماده تکمیل است",
                           schedule.form.title, "/dashboard/forms", "growth_report",
                           schedule.id, schedule.due_at))
    existing = {item.dedupe_key for item in JourneyNotification.query.filter_by(user_id=user_id).all()}
    created = []
    for key, kind, title, body, target, source_type, source_id, due_at in candidates:
        dedupe_key = f"u{user_id}:c{child_id}:{key}"
        if dedupe_key in existing:
            continue
        item = JourneyNotification(user_id=user_id, child_id=child_id, kind=kind, title=title,
                                   body=body, target_url=target, source_type=source_type,
                                   source_id=source_id, dedupe_key=dedupe_key, due_at=due_at)
        db.session.add(item)
        created.append(item)
    return created


def contract_aggregate_report(contract):
    parents = {item.id: item for item in contract.covered_parents}
    children = {item.id: item for item in contract.covered_children}
    child_ids = set(children)
    parent_ids = set(parents)
    enrollments = CourseEnrollment.query.filter(CourseEnrollment.user_id.in_(parent_ids or {-1})).all()
    if child_ids:
        enrollments = [item for item in enrollments if item.child_id in child_ids or item.child_id is None]
    completed = sum(item.progress_percent >= 100 for item in enrollments)
    average = round(sum(item.progress_percent for item in enrollments) / len(enrollments)) if enrollments else 0
    group_size = len(parent_ids)
    impact = {"available": False, "message": f"برای حفاظت از حریم خصوصی، گزارش اثر از {ANONYMOUS_REPORT_MIN_GROUP} خانواده فعال می‌شود."}
    if group_size >= ANONYMOUS_REPORT_MIN_GROUP:
        scores = [item.score_total for item in FormResponse.query.filter(
            FormResponse.user_id.in_(parent_ids), FormResponse.child_id.in_(child_ids or {-1}),
            FormResponse.status == "submitted", FormResponse.score_total.isnot(None)).all()]
        impact = {"available": True, "response_count": len(scores),
                  "average_score": round(sum(scores) / len(scores), 1) if scores else None,
                  "message": "نمای تجمیعی؛ بدون نمایش پاسخ یا هویت فردی"}
    return {"parents": group_size, "children": len(child_ids), "enrollments": len(enrollments),
            "completed": completed, "completion_percent": round(completed / len(enrollments) * 100) if enrollments else 0,
            "average_progress": average, "service_usage": contract.consumed_service_count, "impact": impact}

