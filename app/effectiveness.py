from collections import Counter

from .models import (
    Child,
    ChildProfileSnapshot,
    DailyAction,
    HomeActionOutcome,
    PlanReview,
    ProjectMembership,
    RecommendationRun,
    User,
    WeeklyPlan,
)


def _percent(part, whole):
    return round(part / whole * 100) if whole else 0


def activation_funnel():
    parents = {row.id for row in User.query.filter_by(role="parent").all()}
    with_child = {row.user_id for row in Child.query.all()} & parents
    with_profile = {row.user_id for row in ChildProfileSnapshot.query.all()} & parents
    with_plan = {row.user_id for row in WeeklyPlan.query.all()} & parents
    completed_week = {
        row.user_id for row in WeeklyPlan.query.filter_by(status="completed").all()
    } & parents
    stages = [
        ("ثبت‌نام والد", parents),
        ("ساخت پرونده فرزند", with_child),
        ("تکمیل نمای فرزند", with_profile),
        ("شروع برنامه هفتگی", with_plan),
        ("تکمیل هفته اول", completed_week),
    ]
    base = len(parents)
    return [
        {"label": label, "count": len(values), "rate": _percent(len(values), base)}
        for label, values in stages
    ]


def outcome_summary(user_ids=None):
    user_ids = set(user_ids or [])
    recommendations = RecommendationRun.query.all()
    if user_ids:
        recommendations = [item for item in recommendations if item.user_id in user_ids]
    recommendation_ids = {item.id for item in recommendations}
    outcomes = [
        item
        for item in HomeActionOutcome.query.all()
        if item.recommendation_id in recommendation_ids
    ]
    outcome_counts = Counter(item.outcome for item in outcomes)
    reviews = PlanReview.query.all()
    if user_ids:
        plan_users = {
            plan.id: plan.user_id for plan in WeeklyPlan.query.filter(WeeklyPlan.user_id.in_(user_ids)).all()
        }
        reviews = [item for item in reviews if item.weekly_plan_id in plan_users]
    relationship_counts = Counter(item.relationship_change for item in reviews)
    helped = outcome_counts.get("helped", 0)
    return {
        "recommendations": len(recommendations),
        "recorded_outcomes": len(outcomes),
        "helped": helped,
        "helped_rate": _percent(helped, len(outcomes)),
        "completed_weeks": len(reviews),
        "relationship_better": relationship_counts.get("better", 0),
        "relationship_same": relationship_counts.get("same", 0),
        "relationship_harder": relationship_counts.get("harder", 0),
        "average_confidence": (
            round(sum(item.confidence for item in reviews) / len(reviews), 1) if reviews else 0
        ),
    }


def project_anonymous_report(project, minimum_group_size=5):
    memberships = [item for item in project.memberships if item.status in {"active", "pending"}]
    user_ids = {item.user_id for item in memberships}
    children = Child.query.filter(Child.user_id.in_(user_ids)).all() if user_ids else []
    plans = WeeklyPlan.query.filter(WeeklyPlan.user_id.in_(user_ids)).all() if user_ids else []
    completed_actions = 0
    if plans:
        plan_ids = [item.id for item in plans]
        completed_actions = DailyAction.query.filter(
            DailyAction.weekly_plan_id.in_(plan_ids), DailyAction.status == "completed"
        ).count()
    suppressed = len(user_ids) < minimum_group_size
    return {
        "project": project.name,
        "organization": project.organization.name,
        "member_count": len(user_ids),
        "child_count": None if suppressed else len(children),
        "plans_started": None if suppressed else len(plans),
        "plans_completed": None if suppressed else sum(item.status == "completed" for item in plans),
        "actions_completed": None if suppressed else completed_actions,
        "outcomes": None if suppressed else outcome_summary(user_ids),
        "suppressed": suppressed,
        "minimum_group_size": minimum_group_size,
    }
