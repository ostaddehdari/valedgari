import json

from app.extensions import db
from app.models import (
    AssessmentInstrument,
    AssessmentQuestion,
    Child,
    ChildProfileSnapshot,
    Organization,
    ParentingAssessment,
    ParentingStyleAssessment,
    PaymentAllocation,
    ProjectAuditLog,
    ProjectMembership,
    SponsoredProject,
    User,
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

