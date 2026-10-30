import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from .extensions import db
from .models import (
    CommerceAuditLog,
    CourseEnrollment,
    CourseInvoice,
    CourseOrder,
    CourseOrderItem,
    IntegrationSetting,
    PaymentAllocation,
    PaymentTransaction,
    ProjectMembership,
    SmsOutbox,
    SponsoredProject,
    utcnow,
)


ORDER_STATUSES = {"draft", "awaiting_payment", "paid", "failed", "cancelled", "refunded"}
PAYMENT_MODES = {"disabled", "sandbox", "production"}
SMS_EVENTS = {
    "course_enrolled": "ثبت‌نام دوره",
    "purchase_success": "خرید موفق",
    "course_completed": "تکمیل دوره",
    "course_reminder": "یادآوری دوره",
    "payment_failed": "خطای پرداخت",
}


class CommerceError(RuntimeError):
    pass


class GatewayError(CommerceError):
    pass


class SmsError(CommerceError):
    pass


def _secret_material():
    source = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    root = hashlib.sha256(b"valedgari-commerce-v1\0" + source).digest()
    return hmac.new(root, b"encryption", hashlib.sha256).digest(), hmac.new(
        root, b"authentication", hashlib.sha256
    ).digest()


def seal_secret(value):
    """Encrypt then authenticate a short integration secret without storing plaintext."""
    if not value:
        return ""
    enc_key, mac_key = _secret_material()
    nonce = os.urandom(16)
    plain = value.encode("utf-8")
    stream = bytearray()
    counter = 0
    while len(stream) < len(plain):
        stream.extend(
            hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        )
        counter += 1
    cipher = bytes(a ^ b for a, b in zip(plain, stream))
    versioned = b"v1" + nonce + cipher
    tag = hmac.new(mac_key, versioned, hashlib.sha256).digest()
    return "v1." + base64.urlsafe_b64encode(nonce + cipher + tag).decode("ascii")


def open_secret(value):
    if not value:
        return ""
    if not value.startswith("v1."):
        raise CommerceError("نسخه ذخیره‌سازی Secret معتبر نیست.")
    try:
        packed = base64.urlsafe_b64decode(value[3:].encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise CommerceError("Secret ذخیره‌شده قابل خواندن نیست.") from exc
    if len(packed) < 49:
        raise CommerceError("Secret ذخیره‌شده ناقص است.")
    nonce, cipher, tag = packed[:16], packed[16:-32], packed[-32:]
    enc_key, mac_key = _secret_material()
    expected = hmac.new(mac_key, b"v1" + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise CommerceError("صحت Secret ذخیره‌شده تأیید نشد.")
    stream = bytearray()
    counter = 0
    while len(stream) < len(cipher):
        stream.extend(
            hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return bytes(a ^ b for a, b in zip(cipher, stream)).decode("utf-8")


def setting(key, default=""):
    row = IntegrationSetting.query.filter_by(key=key).first()
    return row.value if row and not row.is_secret else default


def secret_setting(key):
    row = IntegrationSetting.query.filter_by(key=key, is_secret=True).first()
    if not row or not row.encrypted_value:
        return ""
    return open_secret(row.encrypted_value)


def save_setting(key, value, actor_id=None, secret=False):
    row = IntegrationSetting.query.filter_by(key=key).first()
    if not row:
        row = IntegrationSetting(key=key)
        db.session.add(row)
    row.updated_by = actor_id
    row.is_secret = bool(secret)
    if secret:
        if value:
            row.encrypted_value = seal_secret(value)
            row.secret_hint = value[-4:] if len(value) >= 4 else "••••"
        row.value = ""
    else:
        row.value = str(value or "")
        row.encrypted_value = ""
        row.secret_hint = ""
    return row


def setting_hint(key):
    row = IntegrationSetting.query.filter_by(key=key, is_secret=True).first()
    return row.secret_hint if row else ""


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if key not in {"merchant_id", "api_key", "token"}}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def audit(action, order=None, actor_id=None, status="success", details=None):
    row = CommerceAuditLog(
        order_id=order.id if order else None,
        actor_id=actor_id,
        action=action,
        status=status,
        details_json=json.dumps(_json_safe(details or {}), ensure_ascii=False),
    )
    db.session.add(row)
    return row


def _release_support(order, reason):
    if order.allocation and order.allocation.status == "reserved":
        order.allocation.status = "cancelled"
        order.allocation.note = str(reason)[:500]


def _number(prefix):
    return f"{prefix}-{utcnow():%Y%m%d}-{secrets.token_hex(4).upper()}"


def _project_accepts_course(project, course):
    values = {str(item).strip().lower() for item in project.eligible_services if str(item).strip()}
    if not values:
        return True
    candidates = {
        "*",
        "all_courses",
        "همه دوره‌ها",
        "دوره‌ها",
        course.slug.lower(),
        course.title.strip().lower(),
        f"course:{course.id}",
    }
    return bool(values & candidates)


def eligible_supports(user_id, child, course):
    now = utcnow().date()
    rows = []
    memberships = ProjectMembership.query.filter(
        ProjectMembership.user_id == user_id,
        ProjectMembership.status.in_(["active", "pending"]),
    ).all()
    for membership in memberships:
        project = membership.project
        if project.status != "active" or project.organization.status != "active":
            continue
        if project.starts_on and now < project.starts_on:
            continue
        if project.ends_on and now > project.ends_on:
            continue
        if project.contract and project.contract.status != "active":
            continue
        if not _project_accepts_course(project, course):
            continue
        gross, organization_amount, parent_amount = project.calculate_split(course.price_toman)
        if project.subsidy_cap_per_parent_toman:
            already_reserved = sum(
                allocation.organization_amount_toman
                for allocation in membership.allocations
                if allocation.status not in {"cancelled", "refunded"}
            )
            remaining_cap = max(0, project.subsidy_cap_per_parent_toman - already_reserved)
            organization_amount = min(organization_amount, remaining_cap)
            parent_amount = gross - organization_amount
        if project.remaining_budget_toman is not None and project.remaining_budget_toman < organization_amount:
            continue
        rows.append(
            {
                "membership": membership,
                "project": project,
                "gross": gross,
                "organization": organization_amount,
                "parent": parent_amount,
                "child": child,
            }
        )
    return sorted(rows, key=lambda item: (item["organization"], -item["parent"]), reverse=True)


def _invoice_for(order):
    if order.invoice:
        return order.invoice
    invoice = CourseInvoice(
        invoice_no=_number("INV"),
        order_id=order.id,
        status="issued",
        gross_amount_toman=order.gross_amount_toman,
        discount_amount_toman=order.discount_amount_toman,
        organization_amount_toman=order.organization_amount_toman,
        payable_amount_toman=order.payable_amount_toman,
    )
    db.session.add(invoice)
    order.invoice = invoice
    return invoice


def create_course_order(user, child, course, project_id=None):
    if course.status != "published":
        raise CommerceError("این دوره در حال حاضر قابل خرید نیست.")
    child_id = child.id if child else None
    existing_enrollment = CourseEnrollment.query.filter_by(
        course_id=course.id, user_id=user.id, child_id=child_id
    ).filter(CourseEnrollment.status.in_(["active", "completed"])).first()
    if existing_enrollment:
        return existing_enrollment.order, existing_enrollment
    existing_order = CourseOrder.query.join(CourseOrderItem).filter(
        CourseOrder.user_id == user.id,
        CourseOrder.child_id == child_id,
        CourseOrderItem.course_id == course.id,
        CourseOrder.status.in_(["draft", "awaiting_payment"]),
        CourseOrder.expires_at > utcnow(),
    ).order_by(CourseOrder.created_at.desc()).first()
    if existing_order and (project_id is None or existing_order.support_project_id == project_id):
        return existing_order, None
    if existing_order:
        existing_order.status = "cancelled"
        existing_order.cancelled_at = utcnow()
        if existing_order.invoice:
            existing_order.invoice.status = "void"
        if existing_order.allocation and existing_order.allocation.status == "reserved":
            existing_order.allocation.status = "cancelled"
            existing_order.allocation.note = "جایگزینی با شیوه پرداخت جدید"
        audit("order_replaced", existing_order, user.id, details={"new_support_project_id": project_id})

    support = None
    supports = eligible_supports(user.id, child, course)
    if project_id == -1:
        support = None
    elif project_id:
        support = next((item for item in supports if item["project"].id == project_id), None)
        if not support:
            raise CommerceError("طرح حمایت انتخاب‌شده برای این دوره یا خانواده معتبر نیست.")
    elif supports:
        support = supports[0]

    gross = max(0, course.price_toman)
    organization_amount = support["organization"] if support else 0
    payable = max(0, gross - organization_amount)
    order = CourseOrder(
        order_no=_number("ORD"),
        user_id=user.id,
        child_id=child_id,
        status="draft",
        gross_amount_toman=gross,
        organization_amount_toman=organization_amount,
        payable_amount_toman=payable,
        support_project_id=support["project"].id if support else None,
        pricing_snapshot_json=json.dumps(
            {
                "course_id": course.id,
                "course_version": course.version,
                "course_title": course.title,
                "price_toman": gross,
                "support_project_id": support["project"].id if support else None,
                "support_name": support["project"].name if support else "",
                "organization_name": support["project"].organization.name if support else "",
            },
            ensure_ascii=False,
        ),
        expires_at=utcnow() + timedelta(minutes=30),
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(
        CourseOrderItem(
            order_id=order.id,
            course_id=course.id,
            title_snapshot=course.title,
            unit_price_toman=gross,
            line_total_toman=gross,
        )
    )
    if support:
        allocation = PaymentAllocation(
            membership_id=support["membership"].id,
            service_name=f"دوره: {course.title}",
            gross_amount_toman=gross,
            organization_amount_toman=organization_amount,
            parent_amount_toman=payable,
            status="reserved",
            note=f"رزرو سفارش {order.order_no}",
        )
        db.session.add(allocation)
        db.session.flush()
        order.allocation_id = allocation.id
    _invoice_for(order)
    audit(
        "order_created",
        order,
        user.id,
        details={"course_id": course.id, "payable": payable, "organization": organization_amount},
    )
    db.session.flush()
    return order, None


def queue_sms(event_type, recipient, payload, unique_key, message=""):
    if event_type not in SMS_EVENTS:
        raise SmsError("نوع رویداد پیامکی پشتیبانی نمی‌شود.")
    existing = SmsOutbox.query.filter_by(unique_key=unique_key).first()
    if existing:
        return existing
    pattern_code = setting(f"ippanel.pattern.{event_type}")
    row = SmsOutbox(
        unique_key=unique_key,
        event_type=event_type,
        recipient=recipient,
        pattern_code=pattern_code,
        message=message[:1000],
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        status="queued",
        next_attempt_at=utcnow(),
    )
    db.session.add(row)
    return row


def complete_order(order, transaction=None):
    if order.status == "paid":
        enrollment = CourseEnrollment.query.filter_by(order_id=order.id).first()
        return enrollment
    if order.status in {"cancelled", "refunded"}:
        raise CommerceError("سفارش لغوشده یا بازپرداخت‌شده قابل تکمیل نیست.")
    now = utcnow()
    order.status = "paid"
    order.paid_at = now
    invoice = _invoice_for(order)
    invoice.status = "free" if order.gross_amount_toman == 0 else "paid"
    invoice.paid_at = now
    if order.allocation:
        order.allocation.status = "parent_paid"
        order.allocation.parent_paid_at = now
        order.allocation.membership.status = "active"
    item = order.items[0]
    enrollment = CourseEnrollment.query.filter_by(
        course_id=item.course_id, user_id=order.user_id, child_id=order.child_id
    ).first()
    if not enrollment:
        enrollment = CourseEnrollment(
            course_id=item.course_id,
            user_id=order.user_id,
            child_id=order.child_id,
            order_id=order.id,
            status="active",
            source="free" if order.gross_amount_toman == 0 else ("sponsored" if order.organization_amount_toman else "purchase"),
            price_snapshot_toman=order.gross_amount_toman,
        )
        db.session.add(enrollment)
    else:
        enrollment.order_id = order.id
        if enrollment.status not in {"active", "completed"}:
            enrollment.status = "active"
    if transaction:
        transaction.status = "verified"
        transaction.verified_at = now
    audit(
        "order_paid",
        order,
        order.user_id,
        details={"transaction_id": transaction.id if transaction else None, "invoice": invoice.invoice_no},
    )
    queue_sms(
        "course_enrolled",
        order.user.mobile,
        {"name": order.user.full_name, "course": item.title_snapshot, "order": order.order_no},
        f"course-enrolled:{order.id}",
        message=f"ثبت‌نام شما در دوره «{item.title_snapshot}» انجام شد.",
    )
    if order.gross_amount_toman > 0:
        queue_sms(
            "purchase_success",
            order.user.mobile,
            {"name": order.user.full_name, "course": item.title_snapshot, "invoice": invoice.invoice_no},
            f"purchase-success:{order.id}",
            message=f"پرداخت دوره «{item.title_snapshot}» با موفقیت ثبت شد.",
        )
    db.session.flush()
    return enrollment


def cancel_order(order, actor_id=None, reason="لغو توسط کاربر"):
    if order.status == "paid":
        raise CommerceError("سفارش پرداخت‌شده از مسیر بازپرداخت مدیریت می‌شود.")
    if order.status in {"cancelled", "refunded"}:
        return order
    order.status = "cancelled"
    order.cancelled_at = utcnow()
    if order.invoice:
        order.invoice.status = "void"
    if order.allocation and order.allocation.status == "reserved":
        order.allocation.status = "cancelled"
        order.allocation.note = reason[:500]
    for transaction in order.transactions:
        if transaction.status not in {"verified", "refunded"}:
            transaction.status = "cancelled"
    audit("order_cancelled", order, actor_id, details={"reason": reason})
    return order


def refund_order(order, actor_id=None, note=""):
    if order.status != "paid":
        raise CommerceError("فقط سفارش پرداخت‌شده قابل ثبت بازپرداخت است.")
    now = utcnow()
    order.status = "refunded"
    order.refunded_at = now
    order.invoice.status = "refunded"
    order.invoice.refunded_at = now
    if order.allocation:
        order.allocation.status = "refunded"
        order.allocation.note = note[:500]
    enrollment = CourseEnrollment.query.filter_by(order_id=order.id).first()
    if enrollment and enrollment.status != "completed":
        enrollment.status = "refunded"
    verified = next((item for item in order.transactions if item.status == "verified"), None)
    if verified:
        verified.status = "refunded"
    audit("order_refunded", order, actor_id, details={"note": note})
    return order


def _post_json(url, payload, headers=None, timeout=15):
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")[:1000]
        except Exception:
            body = ""
        raise CommerceError(f"سرویس بیرونی با کد {exc.code} پاسخ داد: {body}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise CommerceError("ارتباط امن با سرویس بیرونی برقرار نشد.") from exc


def _zarinpal_urls(mode):
    if mode == "sandbox":
        root = "https://sandbox.zarinpal.com/pg/v4/payment"
        start = "https://sandbox.zarinpal.com/pg/StartPay/"
    else:
        root = "https://payment.zarinpal.com/pg/v4/payment"
        start = "https://payment.zarinpal.com/pg/StartPay/"
    return f"{root}/request.json", f"{root}/verify.json", start


def initiate_payment(order, callback_url):
    if order.payable_amount_toman <= 0:
        return None, ""
    mode = setting("zarinpal.mode", current_app.config.get("PAYMENT_MODE", "disabled"))
    if mode not in PAYMENT_MODES or mode == "disabled":
        raise GatewayError("درگاه پرداخت هنوز توسط مدیر فعال نشده است.")
    merchant_id = secret_setting("zarinpal.merchant_id") or current_app.config.get("PAYMENT_MERCHANT_ID", "")
    if not merchant_id:
        raise GatewayError("شناسه پذیرنده زرین‌پال تنظیم نشده است.")
    existing = next(
        (item for item in order.transactions if item.status in {"initiated", "redirected"} and item.authority),
        None,
    )
    if existing:
        _request_url, _verify_url, start = _zarinpal_urls(mode)
        return existing, f"{start}{existing.authority}"
    attempt = len(order.transactions) + 1
    transaction = PaymentTransaction(
        order_id=order.id,
        provider="zarinpal",
        idempotency_key=f"zarinpal:{order.id}:{attempt}",
        amount_toman=order.payable_amount_toman,
        status="initiated",
        attempt_no=attempt,
        request_json=json.dumps({"order_no": order.order_no, "callback_url": callback_url}, ensure_ascii=False),
    )
    db.session.add(transaction)
    db.session.flush()
    if current_app.config.get("PAYMENT_FAKE_GATEWAY"):
        response = {"data": {"code": 100, "authority": f"TEST{order.id:08d}{attempt:02d}"}}
    else:
        request_url, _verify_url, _start = _zarinpal_urls(mode)
        try:
            response = _post_json(
                request_url,
                {
                    "merchant_id": merchant_id,
                    "amount": order.payable_amount_toman * 10,
                    "callback_url": callback_url,
                    "description": f"خرید دوره والدیار - {order.order_no}",
                    "metadata": {"mobile": order.user.mobile, "order_id": str(order.id)},
                },
            )
        except CommerceError as exc:
            transaction.status = "failed"
            transaction.error_message = str(exc)[:500]
            order.status = "failed"
            _release_support(order, str(exc))
            audit("payment_request_failed", order, order.user_id, "failed", {"reason": str(exc)})
            raise GatewayError(str(exc)) from exc
    data = response.get("data") or {}
    code = int(data.get("code") or 0)
    authority = str(data.get("authority") or "")
    transaction.response_json = json.dumps(_json_safe(response), ensure_ascii=False)
    transaction.provider_code = str(code)
    if code != 100 or not authority:
        transaction.status = "failed"
        transaction.error_message = "زرین‌پال Authority معتبر برنگرداند."
        order.status = "failed"
        _release_support(order, transaction.error_message)
        audit("payment_request_failed", order, order.user_id, "failed", {"code": code})
        raise GatewayError(transaction.error_message)
    transaction.authority = authority
    transaction.status = "redirected"
    order.status = "awaiting_payment"
    audit("payment_requested", order, order.user_id, details={"transaction_id": transaction.id, "authority": authority})
    _request_url, _verify_url, start = _zarinpal_urls(mode)
    return transaction, f"{start}{authority}"


def test_zarinpal_connection(callback_url):
    mode = setting("zarinpal.mode", current_app.config.get("PAYMENT_MODE", "disabled"))
    merchant_id = secret_setting("zarinpal.merchant_id") or current_app.config.get("PAYMENT_MERCHANT_ID", "")
    if mode not in {"sandbox", "production"} or not merchant_id:
        raise GatewayError("حالت درگاه و Merchant ID را پیش از آزمون اتصال کامل کنید.")
    if current_app.config.get("PAYMENT_FAKE_GATEWAY"):
        return {"code": 100, "authority": "TEST-CONNECTION"}
    request_url, _verify_url, _start = _zarinpal_urls(mode)
    response = _post_json(
        request_url,
        {
            "merchant_id": merchant_id,
            "amount": 10000,
            "callback_url": callback_url,
            "description": "آزمون اتصال والدیار - بدون تکمیل پرداخت",
        },
    )
    data = response.get("data") or {}
    code = int(data.get("code") or 0)
    if code != 100 or not data.get("authority"):
        raise GatewayError(f"زرین‌پال اتصال را با کد {code} نپذیرفت.")
    return {"code": code, "authority": str(data["authority"])}


def verify_payment(transaction):
    if transaction.status == "verified":
        return transaction
    if transaction.status not in {"redirected", "initiated"}:
        raise GatewayError("این تراکنش در وضعیت قابل تأیید نیست.")
    mode = setting("zarinpal.mode", current_app.config.get("PAYMENT_MODE", "disabled"))
    merchant_id = secret_setting("zarinpal.merchant_id") or current_app.config.get("PAYMENT_MERCHANT_ID", "")
    if current_app.config.get("PAYMENT_FAKE_GATEWAY"):
        response = {"data": {"code": 100, "ref_id": f"REF-{transaction.id}", "card_pan": "0000-****-****-0000"}}
    else:
        if mode == "disabled" or not merchant_id:
            raise GatewayError("تنظیمات درگاه برای Verify کامل نیست.")
        _request_url, verify_url, _start = _zarinpal_urls(mode)
        try:
            response = _post_json(
                verify_url,
                {
                    "merchant_id": merchant_id,
                    "amount": transaction.amount_toman * 10,
                    "authority": transaction.authority,
                },
            )
        except CommerceError as exc:
            transaction.error_message = str(exc)[:500]
            audit("payment_verify_deferred", transaction.order, transaction.order.user_id, "failed", {"reason": str(exc)})
            raise GatewayError(str(exc)) from exc
    data = response.get("data") or {}
    code = int(data.get("code") or 0)
    transaction.response_json = json.dumps(_json_safe(response), ensure_ascii=False)
    transaction.provider_code = str(code)
    if code not in {100, 101}:
        transaction.status = "failed"
        transaction.error_message = f"تأیید پرداخت با کد {code} ناموفق بود."
        transaction.order.status = "failed"
        _release_support(transaction.order, transaction.error_message)
        audit("payment_verify_failed", transaction.order, transaction.order.user_id, "failed", {"code": code})
        raise GatewayError(transaction.error_message)
    transaction.reference_id = str(data.get("ref_id") or "")
    transaction.card_pan = str(data.get("card_pan") or "")[:40]
    transaction.status = "verified"
    transaction.verified_at = utcnow()
    complete_order(transaction.order, transaction)
    return transaction


def _e164(mobile):
    digits = "".join(character for character in str(mobile) if character.isdigit())
    if digits.startswith("0"):
        return "+98" + digits[1:]
    if digits.startswith("98"):
        return "+" + digits
    return "+" + digits


def process_sms(job):
    if job.status == "sent":
        return job
    if setting("ippanel.enabled", "0") != "1":
        raise SmsError("ارسال پیامک در تنظیمات غیرفعال است.")
    token = secret_setting("ippanel.api_token")
    sender = setting("ippanel.from_number")
    if not token or not sender:
        raise SmsError("API Token یا شماره ارسال IPPanel کامل نیست.")
    job.attempts += 1
    try:
        if job.pattern_code:
            payload = {
                "sending_type": "pattern",
                "from_number": sender,
                "code": job.pattern_code,
                "recipients": [_e164(job.recipient)],
                "params": job.payload,
            }
        else:
            payload = {
                "sending_type": "webservice",
                "from_number": sender,
                "message": job.message,
                "params": {"recipients": [_e164(job.recipient)]},
            }
        if current_app.config.get("SMS_FAKE_PROVIDER"):
            response = {"data": {"message_outbox_ids": [job.id]}, "meta": {"status": True}}
        else:
            response = _post_json(
                "https://edge.ippanel.com/v1/api/send",
                payload,
                headers={"Authorization": token},
            )
        meta = response.get("meta") or {}
        ids = (response.get("data") or {}).get("message_outbox_ids") or []
        if meta.get("status") is False or not ids:
            raise SmsError("IPPanel شناسه Outbox معتبر برنگرداند.")
        job.status = "sent"
        job.sent_at = utcnow()
        job.provider_message_id = str(ids[0])
        job.last_error = ""
    except CommerceError as exc:
        job.status = "failed" if job.attempts >= 5 else "retry"
        job.last_error = str(exc)[:500]
        job.next_attempt_at = utcnow() + timedelta(minutes=min(60, 2 ** job.attempts))
        raise
    return job


def reconciliation_issues():
    issues = []
    for order in CourseOrder.query.order_by(CourseOrder.created_at.desc()).all():
        verified = [item for item in order.transactions if item.status == "verified"]
        enrollment = CourseEnrollment.query.filter_by(order_id=order.id).first()
        if order.status == "paid" and order.payable_amount_toman > 0 and not verified:
            issues.append((order, "سفارش پرداخت‌شده بدون تراکنش Verify"))
        if verified and order.status != "paid":
            issues.append((order, "تراکنش Verify شده ولی سفارش پرداخت‌شده نیست"))
        if order.status == "paid" and not enrollment:
            issues.append((order, "سفارش پرداخت‌شده بدون ثبت‌نام دوره"))
        if order.invoice and order.invoice.payable_amount_toman != order.payable_amount_toman:
            issues.append((order, "عدم تطابق مبلغ فاکتور و سفارش"))
    return issues
