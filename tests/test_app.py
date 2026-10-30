import json

from app.extensions import db
from app.models import (
    AssessmentInstrument,
    AssessmentQuestion,
    AssistantConversation,
    AssistantFeedback,
    AssistantMessage,
    Child,
    ChildProfileSnapshot,
    ConsentRecord,
    DataDeletionRequest,
    DailyAction,
    HomeActionOutcome,
    MicroLesson,
    Organization,
    ParentingAssessment,
    ParentingStyleAssessment,
    PaymentAllocation,
    ProjectAuditLog,
    ProjectMembership,
    PlanReview,
    RecommendationRun,
    SafetyProtocol,
    ScientificReview,
    ScenarioTopic,
    SkillDomain,
    SkillProgress,
    SponsoredProject,
    User,
    WeeklyPlan,
)

from .conftest import login


def test_landing_and_health(client):
    assert client.get("/").status_code == 200
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_register_normalizes_persian_digits(client, app):
    response = client.post(
        "/auth/register",
        data={
            "full_name": "مادر نمونه",
            "mobile": "۰۹۱۲۳۴۵۶۷۸۹",
            "password": "SecurePass123",
                "privacy_consent": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert User.query.filter_by(mobile="09123456789").one().role == "parent"


def test_login_and_multi_child_isolation(client, app):
    assert login(client).status_code == 302
    first = client.post(
        "/dashboard/children",
        data={"name": "سارا", "birth_year": "1392", "gender": "girl"},
    )
    second = client.post(
        "/dashboard/children",
        data={"name": "علی", "birth_year": "1390", "gender": "boy"},
    )
    assert first.status_code == second.status_code == 302
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        assert {child.name for child in parent.children} == {"سارا", "علی"}


def test_assessment_saved_for_active_child(client, app):
    login(client)
    client.post(
        "/dashboard/children",
        data={"name": "سارا", "birth_year": "1392", "gender": "girl"},
    )
    response = client.post(
        "/dashboard/assessment",
        data={f"q{index}": "4" for index in range(8)},
    )
    assert response.status_code == 302
    with app.app_context():
        result = ParentingAssessment.query.one()
        assert result.score == 80
        assert db.session.get(Child, result.child_id).name == "سارا"


def test_parent_forbidden_from_admin(client):
    login(client)
    assert client.get("/admin/").status_code == 403


def test_admin_can_open_builders(client):
    login(client, mobile="09120000001", password="AdminPass123")
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/tree").status_code == 200
    assert client.get("/admin/forms").status_code == 200
    assert client.get("/admin/projects").status_code == 200
    assert client.get("/admin/assessments/baumrind").status_code == 200
    assert client.get("/admin/learning-path").status_code == 200
    assert client.get("/admin/assistant-control").status_code == 200


def create_sponsored_project(client, capacity="10", budget="7000000"):
    login(client, mobile="09120000001", password="AdminPass123")
    response = client.post(
        "/admin/projects",
        data={
            "new_organization_name": "سازمان نمونه",
            "legal_name": "شرکت نمونه",
            "contact_name": "مسئول رفاه",
            "contact_mobile": "09121111111",
            "name": "پایلوت والدگری کارکنان",
            "code": "ORG-70",
            "status": "active",
            "pricing_model": "percent",
            "service_price_toman": "1000000",
            "organization_share_percent": "70",
            "organization_fixed_toman": "0",
            "subsidy_cap_per_parent_toman": "0",
            "total_budget_toman": budget,
            "capacity": capacity,
            "eligible_services": "دسترسی والدیار",
        },
    )
    assert response.status_code == 302
    client.post("/auth/logout")


def test_organization_project_and_70_30_membership(client, app):
    create_sponsored_project(client)
    login(client)
    response = client.post(
        "/dashboard/projects",
        data={"action": "join", "code": "ORG-70"},
    )
    assert response.status_code == 302
    with app.app_context():
        project = SponsoredProject.query.filter_by(code="ORG-70").one()
        assert project.organization.name == "سازمان نمونه"
        assert project.calculate_split() == (1000000, 700000, 300000)
        membership = ProjectMembership.query.one()
        assert membership.status == "pending"
        allocation = PaymentAllocation.query.one()
        assert allocation.gross_amount_toman == 1000000
        assert allocation.organization_amount_toman == 700000
        assert allocation.parent_amount_toman == 300000
        assert allocation.status == "reserved"
        assert project.remaining_budget_toman == 6300000
        assert ProjectAuditLog.query.filter_by(action="parent_joined").count() == 1


def test_project_capacity_and_budget_are_enforced(client, app):
    create_sponsored_project(client, capacity="1", budget="700000")
    login(client)
    client.post("/dashboard/projects", data={"action": "join", "code": "ORG-70"})
    client.post("/auth/logout")
    with app.app_context():
        second = User(full_name="والد دوم", mobile="09120000003", role="parent")
        second.set_password("ParentPass123")
        db.session.add(second)
        db.session.commit()
    login(client, mobile="09120000003", password="ParentPass123")
    response = client.post(
        "/dashboard/projects",
        data={"action": "join", "code": "ORG-70"},
        follow_redirects=True,
    )
    assert "ظرفیت این پروژه تکمیل شده است" in response.get_data(as_text=True)
    with app.app_context():
        assert ProjectMembership.query.count() == 1
        assert PaymentAllocation.query.count() == 1


def test_admin_financial_status_and_csv_report(client, app):
    create_sponsored_project(client)
    login(client)
    client.post("/dashboard/projects", data={"action": "join", "code": "ORG-70"})
    client.post("/auth/logout")
    login(client, mobile="09120000001", password="AdminPass123")
    with app.app_context():
        project_id = SponsoredProject.query.one().id
        allocation_id = PaymentAllocation.query.one().id
    assert client.get(f"/admin/projects/{project_id}").status_code == 200
    response = client.post(
        f"/admin/projects/{project_id}",
        data={
            "action": "allocation_status",
            "allocation_id": str(allocation_id),
            "status": "parent_paid",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(PaymentAllocation, allocation_id).status == "parent_paid"
        assert ProjectMembership.query.one().status == "active"
    export = client.get(f"/admin/projects/{project_id}/export.csv")
    assert export.status_code == 200
    assert export.data.startswith("\ufeff".encode())
    assert "700000" in export.get_data(as_text=True)


def test_parent_cannot_open_project_admin(client):
    login(client)
    assert client.get("/admin/projects").status_code == 403


def initial_profile_payload():
    return {
        "profile_type": "initial",
        "emotional_intensity": "4",
        "adaptability": "3",
        "sensory_sensitivity": "4",
        "communication_openness": "3",
        "persistence": "5",
        "social_comfort": "2",
        "anger_pattern": "withdrawal",
        "strengths": ["empathy", "persistence"],
        "triggers": ["direct_pressure", "sudden_change"],
        "calming": ["quiet_space", "time"],
        "priorities": ["anger", "school"],
        "parent_notes": "در تغییر برنامه به زمان بیشتری نیاز دارد.",
    }


def test_child_profile_is_versioned_and_isolated(client, app):
    login(client)
    client.post(
        "/dashboard/children",
        data={"name": "سارا", "birth_year": "1392", "gender": "girl"},
    )
    first = client.post("/dashboard/child-profile", data=initial_profile_payload())
    second = client.post("/dashboard/child-profile", data=initial_profile_payload())
    relationship = client.post(
        "/dashboard/child-profile",
        data={"profile_type": "relationship", **{f"r{i}": "4" for i in range(8)}},
    )
    assert first.status_code == second.status_code == relationship.status_code == 302
    with app.app_context():
        sara = Child.query.filter_by(name="سارا").one()
        initial = ChildProfileSnapshot.query.filter_by(
            child_id=sara.id, profile_type="initial"
        ).order_by(ChildProfileSnapshot.version_no).all()
        assert [item.version_no for item in initial] == [1, 2]
        assert initial[-1].summary["anger_pattern"] == "کناره‌گیری و سکوت"
        relation = ChildProfileSnapshot.query.filter_by(
            child_id=sara.id, profile_type="relationship"
        ).one()
        assert relation.summary["score"] == 80
    client.post(
        "/dashboard/children",
        data={"name": "علی", "birth_year": "1390", "gender": "boy"},
    )
    page = client.get("/dashboard/child-profile")
    assert page.status_code == 200
    assert "نمای علی هنوز ساخته نشده است" in page.get_data(as_text=True)


def approved_baumrind_questions():
    questions = []
    for dimension, prefix in (
        ("authoritative", "A"),
        ("authoritarian", "R"),
        ("permissive", "P"),
    ):
        for index in range(1, 3):
            questions.append(
                {
                    "code": f"{prefix}{index}",
                    "text": f"گزاره آزمایشی تأییدشده {prefix}{index}",
                    "dimension": dimension,
                    "weight": 1,
                    "reverse_score": False,
                    "is_required": True,
                }
            )
    return questions


def publish_test_baumrind(client):
    login(client, mobile="09120000001", password="AdminPass123")
    client.post(
        "/admin/assessments/baumrind",
        data={
            "action": "save_metadata",
            "title": "نسخه آزمون تأییدشده",
            "version": "test-1",
            "source_reference": "منبع علمی نمونه برای تست نرم‌افزار",
            "license_note": "مجوز نمونه فقط برای تست خودکار",
            "disclaimer": "این نتیجه تشخیص بالینی نیست.",
        },
    )
    client.post(
        "/admin/assessments/baumrind",
        data={
            "action": "import_questions",
            "questions_json": json.dumps(approved_baumrind_questions(), ensure_ascii=False),
        },
    )
    response = client.post(
        "/admin/assessments/baumrind", data={"action": "publish"}
    )
    assert response.status_code == 302
    assert client.get("/admin/assessments/baumrind").status_code == 200
    client.post("/auth/logout")


def test_baumrind_scoring_is_versioned_per_child(client, app):
    publish_test_baumrind(client)
    login(client)
    client.post(
        "/dashboard/children",
        data={"name": "زهرا", "birth_year": "1391", "gender": "girl"},
    )
    with app.app_context():
        instrument = AssessmentInstrument.query.filter_by(status="published").one()
        values = {
            f"q_{question.id}": "5" if question.dimension == "authoritative" else "1"
            for question in instrument.questions
        }
        assert len(instrument.questions) == 6
    response = client.post("/dashboard/parenting-style", data=values)
    assert response.status_code == 302
    assert client.get("/dashboard/parenting-style").status_code == 200
    with app.app_context():
        result = ParentingStyleAssessment.query.one()
        assert result.child.name == "زهرا"
        assert result.instrument_version == "test-1"
        assert result.dominant_style == "مقتدرانه"
        assert result.scores == {
            "authoritative": 100,
            "authoritarian": 0,
            "permissive": 0,
        }


def test_baumrind_cannot_publish_without_scientific_gate(client, app):
    login(client, mobile="09120000001", password="AdminPass123")
    response = client.post(
        "/admin/assessments/baumrind",
        data={"action": "publish"},
        follow_redirects=True,
    )
    assert "منبع دقیق نسخه پرسش‌نامه ثبت نشده است" in response.get_data(as_text=True)
    with app.app_context():
        assert AssessmentInstrument.query.one().status == "draft"
        assert AssessmentQuestion.query.count() == 0


def scenario_topic_id(app, slug="anger"):
    with app.app_context():
        return ScenarioTopic.query.filter_by(slug=slug).one().id


def add_child_with_profile(client, name, anger_pattern):
    client.post(
        "/dashboard/children",
        data={"name": name, "birth_year": "1392", "gender": "girl"},
    )
    payload = initial_profile_payload()
    payload["anger_pattern"] = anger_pattern
    response = client.post("/dashboard/child-profile", data=payload)
    assert response.status_code == 302


def test_same_situation_is_personalized_for_each_child(client, app):
    login(client)
    topic_id = scenario_topic_id(app)

    add_child_with_profile(client, "سارا", "withdrawal")
    sara_page = client.get(f"/dashboard/scenario?topic_id={topic_id}&level=2")
    assert sara_page.status_code == 200
    assert "فضا بدهید، اما زمان بازگشت را روشن کنید" in sara_page.get_data(as_text=True)

    add_child_with_profile(client, "علی", "explosion")
    ali_page = client.get(f"/dashboard/scenario?topic_id={topic_id}&level=2")
    assert ali_page.status_code == 200
    assert "کلمات کمتر، مرز ایمنی روشن‌تر" in ali_page.get_data(as_text=True)


def test_negative_outcome_changes_the_next_recommendation(client, app):
    login(client)
    topic_id = scenario_topic_id(app)
    add_child_with_profile(client, "سارا", "withdrawal")

    response = client.post(
        "/dashboard/scenario",
        data={
            "topic_id": topic_id,
            "level": 2,
            "action": "plan_recommendation",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        run = RecommendationRun.query.one()
        run_id = run.id
        assert run.context["child_name"] == "سارا"
        assert run.rule_version == 1

    response = client.post(
        f"/dashboard/recommendations/{run_id}",
        data={
            "outcome": "worsened",
            "child_response": "escalated",
            "helpfulness": "1",
            "parent_note": "تنش بیشتر شد.",
        },
    )
    assert response.status_code == 302
    next_page = client.get(f"/dashboard/scenario?topic_id={topic_id}&level=2")
    assert "شدت مداخله را کمتر کنید" in next_page.get_data(as_text=True)
    with app.app_context():
        assert HomeActionOutcome.query.one().outcome == "worsened"
        assert RecommendationRun.query.one().status == "completed"


def test_high_severity_prioritizes_safety(client, app):
    login(client)
    client.post(
        "/dashboard/children",
        data={"name": "زهرا", "birth_year": "1391", "gender": "girl"},
    )
    topic_id = scenario_topic_id(app, "screen-time")
    page = client.get(f"/dashboard/scenario?topic_id={topic_id}&level=5")
    assert page.status_code == 200
    assert "اول ایمنی و کاهش تنش" in page.get_data(as_text=True)


def test_recommendation_is_isolated_between_parents(client, app):
    login(client)
    topic_id = scenario_topic_id(app)
    add_child_with_profile(client, "سارا", "withdrawal")
    client.post(
        "/dashboard/scenario",
        data={"topic_id": topic_id, "level": 2, "action": "plan_recommendation"},
    )
    with app.app_context():
        run_id = RecommendationRun.query.one().id
        second = User(full_name="والد دوم", mobile="09120000003", role="parent")
        second.set_password("ParentPass123")
        db.session.add(second)
        db.session.commit()
    client.post("/auth/logout")
    login(client, mobile="09120000003", password="ParentPass123")
    assert client.get(f"/dashboard/recommendations/{run_id}").status_code == 404


def test_admin_can_manage_personalization_rules(client):
    login(client, mobile="09120000001", password="AdminPass123")
    page = client.get("/admin/personalization")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "شخصی‌سازی توضیح‌پذیر" in body
    assert "ساخت مسیر شخصی‌سازی" in body


def create_weekly_plan(client, app, child_name="سارا", topic_slug="anger"):
    client.post(
        "/dashboard/children",
        data={"name": child_name, "birth_year": "1392", "gender": "girl"},
    )
    topic_id = scenario_topic_id(app, topic_slug)
    response = client.post(
        "/dashboard/journey",
        data={"topic_id": topic_id, "goal_title": f"هدف هفته {child_name}"},
    )
    assert response.status_code == 302
    with app.app_context():
        return WeeklyPlan.query.filter_by(child_id=Child.query.filter_by(name=child_name).one().id).one().id


def test_stage_four_taxonomy_and_micro_lessons_are_seeded(app):
    with app.app_context():
        assert SkillDomain.query.count() == 6
        assert MicroLesson.query.filter_by(status="published").count() == 7
        titles = {item.title for item in SkillDomain.query.all()}
        assert "خودتنظیمی والد" in titles
        assert "موقعیت ویژه، ریسک و ارجاع" in titles


def test_weekly_plan_builds_seven_coherent_actions(client, app):
    login(client)
    plan_id = create_weekly_plan(client, app)
    page = client.get(f"/dashboard/journey/{plan_id}")
    assert page.status_code == 200
    assert client.get("/dashboard/").status_code == 200
    body = page.get_data(as_text=True)
    assert "هدف هفته سارا" in body
    assert "قدم 1 از ۷" in body
    assert "مکث سه‌مرحله‌ای پیش از پاسخ" in body
    with app.app_context():
        plan = db.session.get(WeeklyPlan, plan_id)
        assert len(plan.actions) == 7
        assert [item.action_type for item in plan.actions] == [
            "lesson",
            "observe",
            "lesson",
            "scenario",
            "home_action",
            "repair",
            "review",
        ]
        assert plan.source_context["topic_slug"] == "anger"
        assert plan.progress_percent == 0


def test_daily_actions_must_be_completed_in_order(client, app):
    login(client)
    plan_id = create_weekly_plan(client, app)
    with app.app_context():
        actions = DailyAction.query.filter_by(weekly_plan_id=plan_id).order_by(DailyAction.day_index).all()
        first_id, second_id = actions[0].id, actions[1].id
    blocked = client.post(
        f"/dashboard/journey/actions/{second_id}",
        data={"confidence": "3", "parent_note": "نباید ثبت شود"},
        follow_redirects=True,
    )
    assert "قدم‌ها را به‌ترتیب انجام دهید" in blocked.get_data(as_text=True)
    response = client.post(
        f"/dashboard/journey/actions/{first_id}",
        data={"confidence": "4", "parent_note": "قبل از پاسخ مکث کردم."},
    )
    assert response.status_code == 302
    with app.app_context():
        plan = db.session.get(WeeklyPlan, plan_id)
        assert plan.completed_count == 1
        assert plan.current_action.id == second_id
        assert SkillProgress.query.one().percent == 20


def test_only_one_active_weekly_plan_per_child(client, app):
    login(client)
    plan_id = create_weekly_plan(client, app)
    topic_id = scenario_topic_id(app, "lying")
    response = client.post(
        "/dashboard/journey",
        data={"topic_id": topic_id, "goal_title": "برنامه دوم"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/dashboard/journey/{plan_id}")
    with app.app_context():
        assert WeeklyPlan.query.count() == 1


def test_week_review_closes_plan_and_allows_next_cycle(client, app):
    login(client)
    plan_id = create_weekly_plan(client, app)
    with app.app_context():
        action_ids = [
            item.id
            for item in DailyAction.query.filter_by(weekly_plan_id=plan_id)
            .order_by(DailyAction.day_index)
            .all()
        ]
    for action_id in action_ids:
        response = client.post(
            f"/dashboard/journey/actions/{action_id}",
            data={"confidence": "4", "parent_note": "قدم انجام شد."},
        )
        assert response.status_code == 302
    with app.app_context():
        assert db.session.get(WeeklyPlan, plan_id).status == "awaiting_review"
    review = client.post(
        f"/dashboard/journey/{plan_id}/review",
        data={
            "rating": "4",
            "confidence": "4",
            "relationship_change": "improved",
            "what_worked": "جمله‌های کوتاه بهتر جواب داد.",
            "next_focus": "ثبات در مرزها",
        },
    )
    assert review.status_code == 302
    with app.app_context():
        plan = db.session.get(WeeklyPlan, plan_id)
        assert plan.status == "completed"
        assert plan.review.relationship_change == "improved"
        assert PlanReview.query.count() == 1


def test_weekly_plan_is_isolated_between_parents(client, app):
    login(client)
    plan_id = create_weekly_plan(client, app)
    with app.app_context():
        action_id = DailyAction.query.filter_by(weekly_plan_id=plan_id).first().id
        second = User(full_name="والد دوم", mobile="09120000003", role="parent")
        second.set_password("ParentPass123")
        db.session.add(second)
        db.session.commit()
    client.post("/auth/logout")
    login(client, mobile="09120000003", password="ParentPass123")
    assert client.get(f"/dashboard/journey/{plan_id}").status_code == 404
    assert client.post(
        f"/dashboard/journey/actions/{action_id}", data={"confidence": "3"}
    ).status_code == 404


def test_admin_can_version_a_micro_lesson(client, app):
    login(client, mobile="09120000001", password="AdminPass123")
    with app.app_context():
        domain_id = SkillDomain.query.first().id
        module_id = MicroLesson.query.first().module_id
    payload = {
        "action": "save_lesson",
        "title": "ریزدَرس آزمایشی",
        "slug": "test-micro-lesson",
        "duration": "8",
        "domain_id": str(domain_id),
        "module_id": str(module_id),
        "objective": "تمرین یک پاسخ کوتاه و روشن در موقعیت واقعی",
        "body": "این متن آموزشی آزمایشی برای بررسی نسخه‌بندی ریزدرس در پنل مدیر است.",
        "practice": "یک جمله کوتاه بنویسید.",
        "common_pitfall": "از سخنرانی طولانی پرهیز کنید.",
        "status": "published",
    }
    first = client.post("/admin/learning-path", data=payload)
    assert first.status_code == 302
    with app.app_context():
        lesson = MicroLesson.query.filter_by(slug="test-micro-lesson").one()
        lesson_id = lesson.id
        assert lesson.version == 1
    second = client.post(
        "/admin/learning-path", data={**payload, "lesson_id": str(lesson_id)}
    )
    assert second.status_code == 302
    with app.app_context():
        assert db.session.get(MicroLesson, lesson_id).version == 2


def create_assistant_child(client, name="سارا"):
    client.post(
        "/dashboard/children",
        data={"name": name, "birth_year": "1392", "gender": "girl"},
    )


def assistant_post(client, message, conversation_id=None):
    data = {"message": message}
    if conversation_id:
        data["conversation_id"] = str(conversation_id)
    return client.post("/dashboard/assistant", data=data)


def test_safety_protocols_are_seeded_and_published(app):
    with app.app_context():
        assert SafetyProtocol.query.filter_by(status="published").count() == 3
        protocol = SafetyProtocol.query.filter_by(slug="immediate-harm-risk").one()
        assert "خودکشی" in protocol.trigger_keywords
        assert len(protocol.immediate_steps) >= 3


def test_assistant_grounded_answer_has_sources_and_child_context(client, app):
    login(client)
    create_assistant_child(client)
    response = assistant_post(client, "سارا وقتی عصبانی می‌شود داد می‌زند؛ چه کار کنم؟")
    assert response.status_code == 302
    with app.app_context():
        conversation = AssistantConversation.query.one()
        answer = AssistantMessage.query.filter_by(role="assistant").one()
        conversation_id = conversation.id
        assert answer.decision_type == "grounded"
        assert answer.topic.slug == "anger"
        assert answer.sources
        assert answer.context["child_name"] == "سارا"
        assert "برای موقعیت «خشم و پرخاشگری» با سارا" in answer.body
    page = client.get(f"/dashboard/assistant?conversation_id={conversation_id}")
    assert page.status_code == 200
    assert "پاسخ منبع‌دار" in page.get_data(as_text=True)


def test_assistant_stops_on_immediate_safety_risk(client, app):
    login(client)
    create_assistant_child(client)
    assistant_post(client, "فرزندم درباره خودکشی حرف می‌زند و چاقو برداشته است")
    with app.app_context():
        answer = AssistantMessage.query.filter_by(role="assistant").one()
        assert answer.decision_type == "safety"
        assert answer.sources[0]["kind"] == "safety_protocol"
        assert "خدمات اضطراری محل زندگی" in answer.body
        assert "شماره تماس حدس نمی‌زنم" in answer.body


def test_assistant_refuses_diagnosis_and_prescription(client, app):
    login(client)
    create_assistant_child(client)
    assistant_post(client, "برای تشخیص بیماری و دوز دارو چه پیشنهادی دارید؟")
    with app.app_context():
        answer = AssistantMessage.query.filter_by(role="assistant").one()
        assert answer.decision_type == "out_of_scope"
        assert "نمی‌توانم دارو" in answer.body
        assert answer.sources == []


def test_assistant_uses_active_weekly_plan_as_source(client, app):
    login(client)
    plan_id = create_weekly_plan(client, app)
    assistant_post(client, "وقتی سارا خشمگین می‌شود امروز چه تمرینی انجام بدهم؟")
    with app.app_context():
        answer = AssistantMessage.query.filter_by(role="assistant").one()
        plan = db.session.get(WeeklyPlan, plan_id)
        assert plan.current_action.title in answer.body
        assert any(source["kind"] == "weekly_plan" for source in answer.sources)
        assert answer.context["active_plan_id"] == plan_id


def test_assistant_conversation_and_feedback_are_isolated(client, app):
    login(client)
    create_assistant_child(client)
    assistant_post(client, "درباره عصبانیت سارا چه کار کنم؟")
    with app.app_context():
        conversation_id = AssistantConversation.query.one().id
        message_id = AssistantMessage.query.filter_by(role="assistant").one().id
        second = User(full_name="والد دوم", mobile="09120000003", role="parent")
        second.set_password("ParentPass123")
        db.session.add(second)
        db.session.commit()
    client.post("/auth/logout")
    login(client, mobile="09120000003", password="ParentPass123")
    create_assistant_child(client, "علی")
    assert client.get(
        f"/dashboard/assistant?conversation_id={conversation_id}"
    ).status_code == 404
    assert client.post(
        f"/dashboard/assistant/messages/{message_id}/feedback",
        data={"helpful": "yes"},
    ).status_code == 404


def test_parent_feedback_and_admin_protocol_versioning(client, app):
    login(client)
    create_assistant_child(client)
    assistant_post(client, "برای زمان موبایل چه مرزی بگذارم؟")
    with app.app_context():
        message_id = AssistantMessage.query.filter_by(role="assistant").one().id
    response = client.post(
        f"/dashboard/assistant/messages/{message_id}/feedback",
        data={"helpful": "yes", "note": "کوتاه و قابل اجرا بود."},
    )
    assert response.status_code == 302
    with app.app_context():
        assert AssistantFeedback.query.one().helpful is True
    client.post("/auth/logout")
    login(client, mobile="09120000001", password="AdminPass123")
    with app.app_context():
        protocol = SafetyProtocol.query.filter_by(slug="immediate-harm-risk").one()
        protocol_id = protocol.id
        payload = {
            "action": "save_protocol",
            "protocol_id": str(protocol.id),
            "title": protocol.title,
            "slug": protocol.slug,
            "priority": str(protocol.priority),
            "trigger_keywords": "\n".join(protocol.trigger_keywords),
            "response_title": protocol.response_title,
            "response_text": protocol.response_text,
            "immediate_steps": "\n".join(protocol.immediate_steps),
            "status": "published",
        }
    update = client.post("/admin/assistant-control", data=payload)
    assert update.status_code == 302
    with app.app_context():
        assert db.session.get(SafetyProtocol, protocol_id).version == 2


def test_stage_six_readiness_and_operations_dashboard(client):
    readiness = client.get("/health/ready")
    assert readiness.status_code == 200
    assert readiness.get_json()["database"] == "available"
    login(client, mobile="09120000001", password="AdminPass123")
    page = client.get("/admin/operations")
    assert page.status_code == 200
    assert "اثربخشی، حریم خصوصی" in page.get_data(as_text=True)


def test_registration_requires_and_records_versioned_consent(client, app):
    refused = client.post(
        "/auth/register",
        data={
            "full_name": "والد بدون رضایت",
            "mobile": "09121111111",
            "password": "SecurePass123",
        },
    )
    assert refused.status_code == 200
    accepted = client.post(
        "/auth/register",
        data={
            "full_name": "والد رضایت داده",
            "mobile": "09121111112",
            "password": "SecurePass123",
            "privacy_consent": "1",
        },
    )
    assert accepted.status_code == 302
    with app.app_context():
        user = User.query.filter_by(mobile="09121111112").one()
        consent = ConsentRecord.query.filter_by(user_id=user.id).one()
        assert consent.accepted is True
        assert consent.policy_version == "1405-08-07-v1"


def test_child_deletion_request_is_audited_and_isolated(client, app):
    login(client)
    client.post(
        "/dashboard/children",
        data={"name": "سارا", "birth_year": "1394", "gender": "girl"},
    )
    with app.app_context():
        child = Child.query.filter_by(name="سارا").one()
        child_id = child.id
    response = client.post(
        "/dashboard/privacy",
        data={"child_id": child_id, "confirmation": "سارا", "reason": "درخواست خانواده"},
    )
    assert response.status_code == 302
    with app.app_context():
        deletion_id = DataDeletionRequest.query.one().id
    client.post("/auth/logout")
    login(client, mobile="09120000001", password="AdminPass123")
    processed = client.post(
        f"/admin/privacy/deletion/{deletion_id}",
        data={"action": "complete", "note": "مالکیت بررسی شد"},
    )
    assert processed.status_code == 302
    with app.app_context():
        assert db.session.get(Child, child_id) is None
        assert db.session.get(DataDeletionRequest, deletion_id).status == "completed"


def test_scientific_reviewer_approves_exact_snapshot(client, app):
    with app.app_context():
        reviewer = User(full_name="ناظر علمی", mobile="09120000009", role="reviewer")
        reviewer.set_password("ReviewerPass123")
        db.session.add(reviewer)
        db.session.commit()
        protocol_id = SafetyProtocol.query.first().id
    login(client, mobile="09120000001", password="AdminPass123")
    requested = client.post(
        "/admin/scientific-review",
        data={"action": "request", "resource_type": "protocol", "resource_id": protocol_id},
    )
    assert requested.status_code == 302
    with app.app_context():
        review_id = ScientificReview.query.one().id
        fingerprint = ScientificReview.query.one().snapshot_hash
    assert client.post(
        "/admin/scientific-review",
        data={"action": "approve", "review_id": review_id},
    ).status_code == 403
    client.post("/auth/logout")
    login(client, mobile="09120000009", password="ReviewerPass123")
    approved = client.post(
        "/admin/scientific-review",
        data={
            "action": "approve",
            "review_id": review_id,
            "reviewer_note": "نسخه حاضر برای پایلوت تأیید است.",
        },
    )
    assert approved.status_code == 302
    with app.app_context():
        review = db.session.get(ScientificReview, review_id)
        assert review.status == "approved"
        assert review.snapshot_hash == fingerprint


def test_anonymous_project_report_suppresses_small_groups(client, app):
    create_sponsored_project(client)
    with app.app_context():
        project = SponsoredProject.query.filter_by(code="ORG-70").one()
        project_id, code = project.id, project.code
    login(client)
    client.post("/dashboard/projects", data={"action": "join", "code": code})
    client.post("/auth/logout")
    login(client, mobile="09120000001", password="AdminPass123")
    report = client.get(f"/admin/projects/{project_id}/impact.csv")
    text = report.get_data(as_text=True)
    assert report.status_code == 200
    assert "حفاظت حریم خصوصی" in text
    assert "09120000002" not in text
    assert "والد آزمون" not in text


def test_parent_dashboard_uses_role_aware_sidebar_and_user_header(client):
    login(client)
    response = client.get("/dashboard/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="appSidebar"' in html
    assert 'data-sidebar-toggle' in html
    assert "داشبورد من" in html
    assert "فرزندان من" in html
    assert "/auth/profile" in html
    assert "خروج امن" in html


def test_admin_dashboard_sidebar_marks_active_page(client):
    login(client, mobile="09120000001", password="AdminPass123")
    response = client.get("/admin/projects")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "پروژه‌های سازمانی" in html
    assert "کاربران" in html
    assert 'aria-current="page"' in html
    assert "داشبورد من" not in html


def test_user_can_open_and_update_own_profile(client, app):
    login(client)
    assert client.get("/auth/profile").status_code == 200
    response = client.post(
        "/auth/profile",
        data={"full_name": "والد به‌روزشده"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "پروفایل شما به‌روزرسانی شد" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(mobile="09120000002").one().full_name == "والد به‌روزشده"


def test_dashboard_css_contains_scrollable_modal_contract(client):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    assert ".modal-dialog-scrollable .modal-content>form>.modal-body" in css
    assert "overflow-y:auto" in css

