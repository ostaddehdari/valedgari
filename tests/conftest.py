import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.seed import seed_content
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_content()
        admin = User(full_name="مدیر آزمون", mobile="09120000001", role="admin")
        admin.set_password("AdminPass123")
        parent = User(full_name="والد آزمون", mobile="09120000002", role="parent")
        parent.set_password("ParentPass123")
        db.session.add_all([admin, parent])
        db.session.commit()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, mobile="09120000002", password="ParentPass123"):
    return client.post("/auth/login", data={"mobile": mobile, "password": password})

