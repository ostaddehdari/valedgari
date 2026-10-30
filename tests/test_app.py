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
    ContractBeneficiary,
    DataDeletionRequest,
    DailyAction,
    DynamicForm,
    FormResponse,
    GuardianRelationship,
    HomeActionOutcome,
    MicroLesson,
    Organization,
    OrganizationAuditLog,
    OrganizationContract,
    ParentingAssessment,
    ParentingStyleAssessment,
    PaymentAllocation,
    ProjectAuditLog,
    ProjectMembership,
    ProfileDefinition,
    ProfileFormBinding,
    ProfileRecord,
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
    assert "طرح‌های حمایت" in html
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


def create_stage_eight_organization(client, app, name="سازمان مستقل"):
    login(client, mobile="09120000001", password="AdminPass123")
    response = client.post(
        "/admin/organizations",
        data={
            "name": name,
            "legal_name": "شرکت مستقل نمونه",
            "registration_no": "",
            "contact_name": "مسئول قرارداد",
            "contact_mobile": "09121112222",
            "status": "active",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        return Organization.query.filter_by(name=name).one().id


def create_stage_eight_contract(client, app, organization_id, status="active", contract_no="CNT-1405-01"):
    response = client.post(
        f"/admin/organizations/{organization_id}",
        data={
            "action": "create_contract",
            "title": "قرارداد آموزش والدین",
            "contract_no": contract_no,
            "status": status,
            "starts_on": "2026-10-01",
            "ends_on": "2027-10-01",
            "total_amount_toman": "10000000",
            "amount_paid_toman": "3000000",
            "body_text": "متن قرارداد نمونه",
            "terms_text": "شرایط اجرای خدمات مجازی",
            "commitments_text": "تعهد سازمان و والدیار",
            "services": "دوره والدگری\nسنجش اولیه",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        return OrganizationContract.query.filter_by(contract_no=contract_no).one().id


def test_stage_eight_organization_is_created_without_implicit_contract(client, app):
    organization_id = create_stage_eight_organization(client, app)
    response = client.get("/admin/organizations")
    assert response.status_code == 200
    assert "سازمان مستقل" in response.get_data(as_text=True)
    profile = client.get(f"/admin/organizations/{organization_id}")
    assert profile.status_code == 200
    assert "قرارداد جدید" in profile.get_data(as_text=True)
    with app.app_context():
        organization = db.session.get(Organization, organization_id)
        assert organization.contracts == []
        assert organization.projects == []
        assert OrganizationAuditLog.query.filter_by(action="organization_created").count() == 1


def test_organization_without_members_can_be_deleted_but_covered_one_cannot(client, app):
    empty_id = create_stage_eight_organization(client, app, name="سازمان قابل حذف")
    deleted = client.post(
        f"/admin/organizations/{empty_id}",
        data={"action": "delete_organization", "confirmation": "سازمان قابل حذف"},
    )
    assert deleted.status_code == 302
    with app.app_context():
        assert db.session.get(Organization, empty_id) is None
        assert OrganizationAuditLog.query.filter_by(action="organization_deleted").count() == 1

    unused_id = create_stage_eight_organization(client, app, name="سازمان قرارداد بدون مصرف")
    create_stage_eight_contract(client, app, unused_id)
    removed_unused = client.post(
        f"/admin/organizations/{unused_id}",
        data={"action": "delete_organization", "confirmation": "سازمان قرارداد بدون مصرف"},
    )
    assert removed_unused.status_code == 302
    with app.app_context():
        assert db.session.get(Organization, unused_id) is None

    protected_id = create_stage_eight_organization(client, app, name="سازمان دارای ذی‌نفع")
    contract_id = create_stage_eight_contract(client, app, protected_id, contract_no="CNT-1405-02")
    with app.app_context():
        parent_id = User.query.filter_by(mobile="09120000002").one().id
    client.post(
        f"/admin/contracts/{contract_id}",
        data={"action": "add_beneficiary", "user_id": parent_id, "beneficiary_type": "family"},
    )
    blocked = client.post(
        f"/admin/organizations/{protected_id}",
        data={"action": "delete_organization", "confirmation": "سازمان دارای ذی‌نفع"},
        follow_redirects=True,
    )
    assert "قابل حذف نیست" in blocked.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Organization, protected_id) is not None


def test_organization_profile_can_use_form_builder_fields(client, app):
    organization_id = create_stage_eight_organization(client, app)
    with app.app_context():
        admin = User.query.filter_by(role="admin").one()
        profile_form = DynamicForm(
            title="فرم پروفایل سازمان",
            slug="organization-profile",
            status="published",
            schema_json=json.dumps(
                [{"id": "sector", "type": "text", "label": "حوزه فعالیت", "required": True}],
                ensure_ascii=False,
            ),
            created_by=admin.id,
        )
        db.session.add(profile_form)
        db.session.commit()
        form_id = profile_form.id
    updated = client.post(
        f"/admin/organizations/{organization_id}",
        data={
            "action": "update_organization",
            "name": "سازمان مستقل",
            "legal_name": "شرکت مستقل نمونه",
            "registration_no": "",
            "status": "active",
            "profile_form_id": form_id,
        },
    )
    assert updated.status_code == 302
    saved = client.post(
        f"/admin/organizations/{organization_id}",
        data={"action": "save_dynamic_profile", "profile_sector": "فناوری آموزشی"},
    )
    assert saved.status_code == 302
    with app.app_context():
        organization = db.session.get(Organization, organization_id)
        assert organization.profile_form_id == form_id
        assert organization.profile_data["sector"] == "فناوری آموزشی"


def test_contract_beneficiary_links_parent_and_child(client, app):
    organization_id = create_stage_eight_organization(client, app)
    contract_id = create_stage_eight_contract(client, app, organization_id)
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        child = Child(user_id=parent.id, name="سارا", birth_year=1393, gender="girl")
        db.session.add(child)
        db.session.commit()
        parent_id, child_id = parent.id, child.id
    response = client.post(
        f"/admin/contracts/{contract_id}",
        data={
            "action": "add_beneficiary",
            "user_id": parent_id,
            "child_id": child_id,
            "beneficiary_type": "child",
        },
    )
    assert response.status_code == 302
    page = client.get(f"/admin/contracts/{contract_id}")
    assert page.status_code == 200
    assert "ذی‌نفعان قرارداد" in page.get_data(as_text=True)
    with app.app_context():
        beneficiary = ContractBeneficiary.query.one()
        contract = db.session.get(OrganizationContract, contract_id)
        assert beneficiary.parent.mobile == "09120000002"
        assert beneficiary.child.name == "سارا"
        assert [item.name for item in contract.covered_children] == ["سارا"]


def test_contract_support_plan_metrics_and_archive_preserve_history(client, app):
    organization_id = create_stage_eight_organization(client, app)
    contract_id = create_stage_eight_contract(client, app, organization_id)
    created = client.post(
        f"/admin/contracts/{contract_id}",
        data={
            "action": "create_support_plan",
            "name": "طرح هفتاد سی کارکنان",
            "code": "STAGE8-70",
            "status": "active",
            "pricing_model": "percent",
            "service_price_toman": "1000000",
            "organization_share_percent": "70",
            "organization_fixed_toman": "0",
            "subsidy_cap_per_parent_toman": "0",
            "total_budget_toman": "7000000",
            "capacity": "20",
            "eligible_services": "دوره والدگری",
        },
    )
    assert created.status_code == 302
    archived = client.post(
        f"/admin/contracts/{contract_id}", data={"action": "archive_contract"}
    )
    assert archived.status_code == 302
    with app.app_context():
        contract = db.session.get(OrganizationContract, contract_id)
        project = SponsoredProject.query.filter_by(code="STAGE8-70").one()
        assert project.contract_id == contract.id
        assert contract.status == "archived"
        assert contract.archived_at is not None
        assert project.status == "closed"


def test_organization_report_contains_covered_child(client, app):
    organization_id = create_stage_eight_organization(client, app)
    contract_id = create_stage_eight_contract(client, app, organization_id)
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        child = Child(user_id=parent.id, name="علی", birth_year=1391, gender="boy")
        db.session.add(child)
        db.session.commit()
        parent_id, child_id = parent.id, child.id
    client.post(
        f"/admin/contracts/{contract_id}",
        data={"action": "add_beneficiary", "user_id": parent_id, "child_id": child_id, "beneficiary_type": "child"},
    )
    report = client.get(f"/admin/organizations/{organization_id}/export.csv")
    assert report.status_code == 200
    text = report.get_data(as_text=True)
    assert "علی" in text
    assert "09120000002" in text


def test_stage_nine_seeds_three_independent_profile_definitions(app):
    with app.app_context():
        definitions = ProfileDefinition.query.filter_by(status="active").all()
        assert {item.profile_type for item in definitions} == {
            "organization",
            "guardian",
            "child",
        }
        assert all(item.version == 1 for item in definitions)
        assert len({item.id for item in definitions}) == 3


def test_profile_schema_only_binds_published_form_and_saves_guardian_fields(client, app):
    with app.app_context():
        admin = User.query.filter_by(role="admin").one()
        published = DynamicForm(
            title="اطلاعات تکمیلی والد",
            slug="guardian-extra",
            status="published",
            schema_json=json.dumps(
                [
                    {"id": "job", "type": "text", "label": "شغل", "required": True},
                    {"id": "education", "type": "select", "label": "تحصیلات", "options": ["دیپلم", "دانشگاهی"]},
                ],
                ensure_ascii=False,
            ),
            created_by=admin.id,
        )
        draft = DynamicForm(
            title="فرم پیش‌نویس",
            slug="guardian-draft",
            status="draft",
            schema_json=json.dumps([{"id": "x", "type": "text", "label": "X"}]),
            created_by=admin.id,
        )
        db.session.add_all([published, draft])
        db.session.commit()
        definition = ProfileDefinition.query.filter_by(
            profile_type="guardian", status="active"
        ).one()
        definition_id, published_id, draft_id = definition.id, published.id, draft.id

    login(client, mobile="09120000001", password="AdminPass123")
    rejected = client.post(
        "/admin/profile-schemas",
        data={
            "action": "bind_form",
            "definition_id": definition_id,
            "form_id": draft_id,
            "section_title": "نباید متصل شود",
        },
        follow_redirects=True,
    )
    assert "فقط فرم منتشرشده" in rejected.get_data(as_text=True)
    accepted = client.post(
        "/admin/profile-schemas",
        data={
            "action": "bind_form",
            "definition_id": definition_id,
            "form_id": published_id,
            "section_title": "اطلاعات شغلی",
            "section_key": "work",
            "sort_order": "2",
        },
    )
    assert accepted.status_code == 302
    client.post("/auth/logout")

    login(client)
    page = client.get("/auth/profile")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "اطلاعات شغلی" in html
    with app.app_context():
        binding = ProfileFormBinding.query.filter_by(
            definition_id=definition_id, form_id=published_id
        ).one()
        binding_id = binding.id
        job_input = f"profile_{binding_id}_job"
        education_input = f"profile_{binding_id}_education"
        parent_id = User.query.filter_by(mobile="09120000002").one().id
    saved = client.post(
        "/auth/profile",
        data={
            "action": "save_profile",
            job_input: "روان‌شناس",
            education_input: "دانشگاهی",
        },
    )
    assert saved.status_code == 302
    with app.app_context():
        record = ProfileRecord.query.filter_by(
            definition_id=definition_id, subject_id=parent_id
        ).one()
        assert record.values[f"{binding_id}:job"] == "روان‌شناس"
        assert record.values[f"{binding_id}:education"] == "دانشگاهی"


def test_new_profile_version_clones_bindings_and_archives_previous(client, app):
    with app.app_context():
        admin = User.query.filter_by(role="admin").one()
        form = DynamicForm(
            title="فرم فرزند",
            slug="child-profile-form",
            status="published",
            schema_json=json.dumps([{"id": "interest", "type": "text", "label": "علاقه"}]),
            created_by=admin.id,
        )
        db.session.add(form)
        db.session.flush()
        definition = ProfileDefinition.query.filter_by(
            profile_type="child", status="active"
        ).one()
        binding = ProfileFormBinding(
            definition_id=definition.id,
            form_id=form.id,
            section_key="identity",
            section_title="شناخت فرزند",
            sort_order=1,
        )
        db.session.add(binding)
        db.session.flush()
        parent = User.query.filter_by(mobile="09120000002").one()
        child = Child(user_id=parent.id, name="آرین", birth_year=1392, gender="boy")
        db.session.add(child)
        db.session.flush()
        db.session.add(
            ProfileRecord(
                definition_id=definition.id,
                subject_id=child.id,
                values_json=json.dumps({f"{binding.id}:interest": "نقاشی"}, ensure_ascii=False),
            )
        )
        db.session.commit()
        old_id, child_id = definition.id, child.id
    login(client, mobile="09120000001", password="AdminPass123")
    response = client.post(
        "/admin/profile-schemas",
        data={"action": "new_version", "profile_type": "child"},
    )
    assert response.status_code == 302
    with app.app_context():
        old = db.session.get(ProfileDefinition, old_id)
        new = ProfileDefinition.query.filter_by(
            profile_type="child", status="active"
        ).one()
        assert old.status == "archived"
        assert new.version == 2
        assert len(new.bindings) == 1
        assert new.bindings[0].section_title == "شناخت فرزند"
        migrated = ProfileRecord.query.filter_by(
            definition_id=new.id, subject_id=child_id
        ).one()
        assert migrated.values[f"{new.bindings[0].id}:interest"] == "نقاشی"
        assert migrated.record_version == 2


def test_multiple_guardians_and_child_profile_idor(client, app):
    login(client)
    client.post(
        "/dashboard/children",
        data={
            "name": "زهرا",
            "birth_year": "1392",
            "gender": "girl",
            "relationship_type": "mother",
        },
    )
    client.post("/auth/logout")
    with app.app_context():
        father = User(full_name="پدر زهرا", mobile="09120000003", role="parent")
        father.set_password("FatherPass123")
        stranger = User(full_name="والد بیگانه", mobile="09120000004", role="parent")
        stranger.set_password("StrangerPass123")
        db.session.add_all([father, stranger])
        db.session.commit()
        child = Child.query.filter_by(name="زهرا").one()
        child_id = child.id

    login(client, mobile="09120000001", password="AdminPass123")
    added = client.post(
        f"/admin/children/{child_id}/profile",
        data={
            "action": "add_guardian",
            "mobile": "09120000003",
            "relationship_type": "father",
            "access_level": "full",
            "status": "active",
        },
    )
    assert added.status_code == 302
    client.post("/auth/logout")
    login(client, mobile="09120000003", password="FatherPass123")
    allowed = client.get(f"/dashboard/children/{child_id}/profile")
    assert allowed.status_code == 200
    assert "پروفایل زهرا" in allowed.get_data(as_text=True)
    client.post("/auth/logout")
    login(client, mobile="09120000004", password="StrangerPass123")
    assert client.get(f"/dashboard/children/{child_id}/profile").status_code == 404


def test_owner_guardian_cannot_be_revoked_but_secondary_can(client, app):
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        secondary = User(full_name="سرپرست دوم", mobile="09120000005", role="parent")
        secondary.set_password("SecondPass123")
        child = Child(user_id=parent.id, name="علی", birth_year=1391, gender="boy")
        db.session.add_all([secondary, child])
        db.session.flush()
        owner_link = GuardianRelationship(
            child_id=child.id,
            guardian_id=parent.id,
            relationship_type="mother",
            access_level="full",
            status="active",
        )
        second_link = GuardianRelationship(
            child_id=child.id,
            guardian_id=secondary.id,
            relationship_type="guardian",
            access_level="full",
            status="active",
        )
        db.session.add_all([owner_link, second_link])
        db.session.commit()
        child_id, owner_link_id, second_link_id = child.id, owner_link.id, second_link.id
    login(client, mobile="09120000001", password="AdminPass123")
    blocked = client.post(
        f"/admin/children/{child_id}/profile",
        data={"action": "revoke_guardian", "relationship_id": owner_link_id},
        follow_redirects=True,
    )
    assert "مالک اصلی" in blocked.get_data(as_text=True)
    revoked = client.post(
        f"/admin/children/{child_id}/profile",
        data={"action": "revoke_guardian", "relationship_id": second_link_id},
    )
    assert revoked.status_code == 302
    with app.app_context():
        assert db.session.get(GuardianRelationship, owner_link_id).status == "active"
        assert db.session.get(GuardianRelationship, second_link_id).status == "revoked"


def test_admin_directory_searches_national_id_and_links_profiles(client, app):
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        parent.national_id = "0012345678"
        child = Child(
            user_id=parent.id,
            name="نگار",
            national_id="0098765432",
            birth_year=1393,
            gender="girl",
        )
        db.session.add(child)
        db.session.commit()
        parent_id, child_id = parent.id, child.id
    login(client, mobile="09120000001", password="AdminPass123")
    parent_page = client.get("/admin/users?q=0012345678")
    child_page = client.get("/admin/users?q=0098765432")
    assert parent_page.status_code == child_page.status_code == 200
    assert f'/admin/guardians/{parent_id}' in parent_page.get_data(as_text=True)
    assert f'/admin/children/{child_id}/profile' in child_page.get_data(as_text=True)


def test_parent_cannot_open_admin_profile_routes(client, app):
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        child = Child(user_id=parent.id, name="سارا", birth_year=1392, gender="girl")
        db.session.add(child)
        db.session.commit()
        parent_id, child_id = parent.id, child.id
    login(client)
    assert client.get("/admin/profile-schemas").status_code == 403
    assert client.get(f"/admin/guardians/{parent_id}").status_code == 403
    assert client.get(f"/admin/children/{child_id}/profile").status_code == 403


def test_admin_and_parent_unified_profile_pages_render(client, app):
    with app.app_context():
        parent = User.query.filter_by(mobile="09120000002").one()
        child = Child(user_id=parent.id, name="رها", birth_year=1394, gender="girl")
        db.session.add(child)
        db.session.commit()
        parent_id, child_id = parent.id, child.id
    login(client, mobile="09120000001", password="AdminPass123")
    guardian_page = client.get(f"/admin/guardians/{parent_id}")
    child_page = client.get(f"/admin/children/{child_id}/profile")
    assert guardian_page.status_code == child_page.status_code == 200
    assert "پروفایل والد/سرپرست" in guardian_page.get_data(as_text=True)
    assert "والدین و سرپرستان" in child_page.get_data(as_text=True)
    client.post("/auth/logout")
    login(client)
    self_page = client.get("/auth/profile")
    family_page = client.get(f"/dashboard/children/{child_id}/profile")
    assert self_page.status_code == family_page.status_code == 200
    assert "پرونده یکپارچه" in self_page.get_data(as_text=True)
    assert "پروفایل رها" in family_page.get_data(as_text=True)

