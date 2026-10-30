import re
import logging
from functools import wraps

from flask import abort
from flask_login import current_user

from .permissions import has_permission


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
        if not has_permission(current_user, "*"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def scientific_staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not (
            has_permission(current_user, "scientific.review")
            or has_permission(current_user, "*")
        ):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


SENSITIVE_LOG_PATTERN = re.compile(
    r"(?i)(secret(?:_key)?|api[_-]?token|merchant[_-]?id|password|authorization)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def redact_sensitive_text(value):
    return SENSITIVE_LOG_PATTERN.sub(r"\1\2[REDACTED]", str(value))


class SecretRedactionFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact_sensitive_text(record.getMessage())
        record.args = ()
        return True

