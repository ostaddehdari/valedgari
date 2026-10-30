from urllib.parse import urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db
from .models import ConsentRecord, User
from .security import normalize_mobile, valid_mobile


bp = Blueprint("auth", __name__, url_prefix="/auth")


def safe_next_url(target):
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target or ""))
    return test_url.scheme in ("http", "https") and host_url.netloc == test_url.netloc


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        endpoint = (
            "admin.dashboard"
            if current_user.is_admin
            else ("admin.scientific_review" if current_user.is_reviewer else "parent.dashboard")
        )
        return redirect(url_for(endpoint))

    if request.method == "POST":
        mobile = normalize_mobile(request.form.get("mobile"))
        password = request.form.get("password", "")
        user = User.query.filter_by(mobile=mobile).first()
        if not user or not user.check_password(password):
            flash("شماره موبایل یا رمز عبور درست نیست.", "danger")
        elif not user.is_active:
            flash("این حساب غیرفعال شده است. با پشتیبانی تماس بگیرید.", "warning")
        else:
            login_user(user, remember=request.form.get("remember") == "1")
            target = request.args.get("next")
            if target and safe_next_url(target):
                return redirect(target)
            endpoint = (
                "admin.dashboard"
                if user.is_admin
                else ("admin.scientific_review" if user.is_reviewer else "parent.dashboard")
            )
            return redirect(url_for(endpoint))
    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("parent.dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        mobile = normalize_mobile(request.form.get("mobile"))
        password = request.form.get("password", "")
        errors = []
        if len(name) < 3:
            errors.append("نام و نام خانوادگی را کامل وارد کنید.")
        if not valid_mobile(mobile):
            errors.append("شماره موبایل باید با ۰۹ شروع شود و ۱۱ رقم باشد.")
        if len(password) < 8:
            errors.append("رمز عبور باید حداقل ۸ نویسه باشد.")
        if request.form.get("privacy_consent") != "1":
            errors.append("پذیرش سیاست حریم خصوصی برای ساخت پرونده کودک الزامی است.")
        if User.query.filter_by(mobile=mobile).first():
            errors.append("برای این شماره موبایل قبلاً حساب ساخته شده است.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            user = User(full_name=name, mobile=mobile, role="parent")
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(
                ConsentRecord(
                    user_id=user.id,
                    policy_version="1405-08-07-v1",
                    source="registration",
                )
            )
            db.session.commit()
            login_user(user, remember=True)
            flash("حساب والدین با موفقیت ساخته شد؛ حالا اولین فرزند را اضافه کنید.", "success")
            return redirect(url_for("parent.children"))
    return render_template("auth/register.html")


@bp.post("/logout")
def logout():
    logout_user()
    flash("با موفقیت از حساب خارج شدید.", "info")
    return redirect(url_for("main.index"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if len(full_name) < 3:
            flash("نام و نام خانوادگی را کامل وارد کنید.", "danger")
        else:
            current_user.full_name = full_name
            db.session.commit()
            flash("پروفایل شما به‌روزرسانی شد.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html")

