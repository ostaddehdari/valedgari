import json
import os

import click
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, ProductionConfig
from .extensions import csrf, db, login_manager, migrate
from .models import OperationalEvent, User
from .security import SecretRedactionFilter
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
    migrate.init_app(app, db, directory="migrations")
    app.logger.addFilter(SecretRedactionFilter())

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

    @app.cli.command("process-sms")
    @click.option("--limit", default=50, type=click.IntRange(1, 500))
    def process_sms_queue(limit):
        """Process due IPPanel jobs; safe to run repeatedly from cron/systemd."""
        from .commerce import SmsError, process_sms
        from .models import SmsOutbox, utcnow

        jobs = SmsOutbox.query.filter(
            SmsOutbox.status.in_(["queued", "retry"]),
            (SmsOutbox.next_attempt_at.is_(None)) | (SmsOutbox.next_attempt_at <= utcnow()),
        ).order_by(SmsOutbox.created_at).limit(limit).all()
        sent = failed = 0
        for job in jobs:
            try:
                process_sms(job)
                db.session.commit()
                sent += 1
            except SmsError:
                db.session.commit()
                failed += 1
        click.echo(f"processed={len(jobs)} sent={sent} failed={failed}")

    @app.cli.command("create-reviewer")
    @click.option("--mobile", prompt="شماره موبایل ناظر علمی")
    @click.option("--name", prompt="نام ناظر علمی")
    @click.password_option(prompt="رمز عبور", confirmation_prompt=True)
    def create_reviewer(mobile, name, password):
        from .security import normalize_mobile, valid_mobile

        mobile = normalize_mobile(mobile)
        if not valid_mobile(mobile):
            raise click.ClickException("شماره موبایل معتبر نیست.")
        user = User.query.filter_by(mobile=mobile).first()
        if not user:
            user = User(mobile=mobile, full_name=name, role="reviewer")
            db.session.add(user)
        user.full_name = name
        user.role = "reviewer"
        user.set_password(password)
        db.session.commit()
        click.echo("حساب مستقل ناظر علمی ایجاد یا به‌روزرسانی شد.")

    @app.cli.command("record-operation")
    @click.option("--event-type", required=True)
    @click.option("--status", type=click.Choice(["success", "warning", "failed"]), required=True)
    @click.option("--details", default="{}")
    def record_operation(event_type, status, details):
        try:
            payload = json.loads(details)
        except ValueError as exc:
            raise click.ClickException("details باید JSON معتبر باشد.") from exc
        db.session.add(
            OperationalEvent(
                event_type=event_type,
                status=status,
                details_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.session.commit()
        click.echo("رویداد عملیاتی ثبت شد.")

    @app.cli.command("doctor")
    def doctor():
        from sqlalchemy import text

        db.session.execute(text("SELECT 1"))
        click.echo(f"database=ok version={app.config['APP_VERSION']}")

    @app.cli.command("seed-stage15-pilot")
    def seed_stage15_pilot_command():
        """Create/update the deterministic controlled-pilot dataset."""
        from .pilot import seed_stage15_pilot

        summary = seed_stage15_pilot()
        click.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True))

    @app.cli.command("migrate-stage15-data")
    def migrate_stage15_data_command():
        """Idempotently move legacy role/profile data to Stage 15 profiles."""
        from .data_migration import migrate_stage15_data

        actor = User.query.filter_by(role="admin").order_by(User.id).first()
        result = migrate_stage15_data(actor.id if actor else None)
        click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))

    @app.cli.command("upgrade-legacy-stage6")
    def upgrade_legacy_stage6_command():
        """Safely bridge an unversioned Stage 6 SQLite database to Stage 15."""
        from .legacy_upgrade import upgrade_legacy_stage6_schema

        result = upgrade_legacy_stage6_schema(db.engine, db.metadata)
        click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))

    @app.cli.command("process-jobs")
    @click.option("--limit", default=50, type=click.IntRange(1, 500))
    def process_background_jobs(limit):
        """Process queued reports, imports, notifications and file scans."""
        from .jobs import process_jobs

        click.echo(json.dumps(process_jobs(limit), ensure_ascii=False, sort_keys=True))

    with app.app_context():
        if app.config.get("AUTO_CREATE_SCHEMA", True):
            db.create_all()
            seed_content()

    return app

