from app.extensions import db
from app.models import Child, ParentingAssessment, User

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

