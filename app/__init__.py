import os

import click
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, ProductionConfig
from .extensions import csrf, db, login_manager
from .models import User
from .seed import seed_content


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=False)
    if config_object:
        app.config.from_object(config_object)
    elif os.getenv("FLASK_ENV") == "production":
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
    )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .parent import bp as parent_bp
    from .admin import bp as admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(admin_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "script-src 'self' https://code.jquery.com https://cdn.jsdelivr.net;",
        )
        return response

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.cli.command("create-admin")
    @click.option("--mobile", prompt="شماره موبایل مدیر")
    @click.option("--name", prompt="نام مدیر", default="مدیر والدیار")
    @click.password_option(prompt="رمز عبور", confirmation_prompt=True)
    def create_admin(mobile, name, password):
        from .security import normalize_mobile, valid_mobile

        mobile = normalize_mobile(mobile)
        if not valid_mobile(mobile):
            raise click.ClickException("شماره موبایل معتبر نیست.")
        user = User.query.filter_by(mobile=mobile).first()
        if not user:
            user = User(mobile=mobile, full_name=name, role="admin")
            db.session.add(user)
        user.full_name = name
        user.role = "admin"
        user.set_password(password)
        db.session.commit()
        click.echo("حساب مدیر ایجاد یا به‌روزرسانی شد.")

    with app.app_context():
        db.create_all()
        seed_content()

    return app

