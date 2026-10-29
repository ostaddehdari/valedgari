import re
from functools import wraps

from flask import abort
from flask_login import current_user


MOBILE_PATTERN = re.compile(r"^09\d{9}$")


def normalize_mobile(value):
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    value = (value or "").translate(translation).replace(" ", "").replace("-", "")
    if value.startswith("+98"):
        value = "0" + value[3:]
    elif value.startswith("98"):
        value = "0" + value[2:]
    return value


def valid_mobile(value):
    return bool(MOBILE_PATTERN.fullmatch(normalize_mobile(value)))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def scientific_staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_staff:
            abort(403)
        return view(*args, **kwargs)

    return wrapped

