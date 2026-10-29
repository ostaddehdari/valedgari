from app.extensions import db
from app.models import (
    Child,
    Organization,
    ParentingAssessment,
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

