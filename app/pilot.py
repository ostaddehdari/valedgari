"""Deterministic, idempotent Stage 15 controlled-pilot dataset."""

import json
from datetime import date

from flask import current_app

from .extensions import db
from .models import (
    Child,
    ContractBeneficiary,
    DynamicForm,
    FormAssignment,
    Organization,
    OrganizationContract,
    ProfileRecord,
    User,
)
from .profiles import active_profile_definition, sync_role_form_to_profile


PILOT_PREFIX = "stage15-pilot"
PILOT_CONTRACTS = ("PILOT-1405-A", "PILOT-1405-B")
PILOT_MOBILE_PREFIX = "09155"

GROUP_LABELS = {
    "shared": "مشترک دو قرارداد",
    "org_a": "فقط سازمان افق",
    "org_b": "فقط سازمان همراه",
    "independent": "غیرسازمانی",
}

PROFILE_FORM_SPECS = {
    "parent": {
        "slug": "stage15-parent-profile",
        "title": "پروفایل نقش والد و سرپرست",
        "description": "فیلدهای نقش‌محور والد که مستقیماً در پروفایل یکپارچه نمایش داده می‌شوند.",
        "fields": [
            {"id": "occupation", "key": "occupation", "type": "text", "label": "شغل", "required": True},
            {"id": "education", "key": "education", "type": "dropdown", "label": "تحصیلات", "options": ["دیپلم", "کاردانی", "کارشناسی", "تحصیلات تکمیلی"]},
            {"id": "city", "key": "city", "type": "text", "label": "شهر محل سکونت"},
            {"id": "contact_time", "key": "contact_time", "type": "dropdown", "label": "زمان مناسب تماس", "options": ["صبح", "بعدازظهر", "شب"]},
            {"id": "parent_goal", "key": "parent_goal", "type": "paragraph", "label": "هدف اصلی والدگری"},
        ],
    },
    "child": {
        "slug": "stage15-child-profile",
        "title": "پروفایل نقش فرزند",
        "description": "فیلدهای فرم نقش فرزند برای پرونده رشد و مدرسه.",
        "fields": [
            {"id": "school_grade", "key": "school_grade", "type": "dropdown", "label": "پایه تحصیلی", "required": True,
             "options": ["اول", "دوم", "سوم", "چهارم", "پنجم", "ششم", "هفتم", "هشتم", "نهم"]},
            {"id": "school_name", "key": "school_name", "type": "text", "label": "نام مدرسه"},
            {"id": "strength", "key": "strength", "type": "text", "label": "نقطه قوت برجسته"},
            {"id": "trigger", "key": "trigger", "type": "text", "label": "محرک مهم"},
            {"id": "support_goal", "key": "support_goal", "type": "paragraph", "label": "هدف حمایتی فعلی"},
        ],
    },
    "organization": {
        "slug": "stage15-organization-profile",
        "title": "پروفایل نقش سازمان",
        "description": "فیلدهای قرارداد و ظرفیت خدمت در پروفایل یکپارچه سازمان.",
        "fields": [
            {"id": "organization_type", "key": "organization_type", "type": "dropdown", "label": "نوع سازمان", "required": True,
             "options": ["مدرسه", "مؤسسه آموزشی", "شرکت", "نهاد عمومی"]},
            {"id": "staff_count", "key": "staff_count", "type": "number", "label": "تعداد کارکنان"},
            {"id": "family_capacity", "key": "family_capacity", "type": "number", "label": "ظرفیت خانواده تحت پوشش"},
            {"id": "preferred_channel", "key": "preferred_channel", "type": "dropdown", "label": "کانال ارتباطی", "options": ["تلفن", "پیامک", "ایمیل"]},
            {"id": "service_goal", "key": "service_goal", "type": "paragraph", "label": "هدف قرارداد والدگری"},
        ],
    },
}


def _admin_id(actor_id=None):
    if actor_id:
        return actor_id
    admin = User.query.filter_by(role="admin").order_by(User.id).first()
    if admin:
        return admin.id
    raise RuntimeError("برای ساخت داده پایلوت ابتدا یک مدیر ایجاد کنید.")


def _profile_forms(actor_id):
    result = {}
    for role_key, spec in PROFILE_FORM_SPECS.items():
        form = DynamicForm.query.filter_by(slug=spec["slug"]).first()
        if not form:
            form = DynamicForm(
                title=spec["title"], slug=spec["slug"], description=spec["description"],
                form_type="profile", use_case=f"role_profile_{role_key}", status="published",
                schema_json=json.dumps(spec["fields"], ensure_ascii=False),
                settings_json=json.dumps({"save_draft": True, "confirmation_title": "پروفایل ذخیره شد"}, ensure_ascii=False),
                scoring_json="{}", created_by=actor_id,
            )
            db.session.add(form)
            db.session.flush()
        else:
            form.title = spec["title"]
            form.description = spec["description"]
            form.form_type = "profile"
            form.use_case = f"role_profile_{role_key}"
            form.status = "published"
            form.schema_json = json.dumps(spec["fields"], ensure_ascii=False)
        assignment = FormAssignment.query.filter_by(
            form_id=form.id, target_type="role", target_ref=role_key, status="active"
        ).first()
        if not assignment:
            assignment = FormAssignment(
                form_id=form.id, target_type="role", target_ref=role_key,
                title=spec["title"], status="active", is_required=True, created_by=actor_id,
            )
            db.session.add(assignment)
        binding = sync_role_form_to_profile(form, role_key, actor_id, spec["title"])
        db.session.flush()
        result[role_key] = (form, binding)
    return result


def _organization(name, registration_no, contact_mobile, actor_id, profile_form):
    organization = Organization.query.filter_by(registration_no=registration_no).first()
    if not organization:
        organization = Organization(registration_no=registration_no, name=name)
        db.session.add(organization)
    organization.name = name
    organization.legal_name = f"{name} (داده نمایشی پایلوت)"
    organization.contact_name = "مسئول پایلوت والدیار"
    organization.contact_mobile = contact_mobile
    organization.contact_email = f"pilot-{registration_no.lower()}@example.test"
    organization.address = "تهران، نشانی نمایشی پایلوت کنترل‌شده"
    organization.status = "active"
    organization.profile_form = profile_form
    db.session.flush()
    return organization


def _contract(organization, contract_no, actor_id):
    contract = OrganizationContract.query.filter_by(contract_no=contract_no).first()
    if not contract:
        contract = OrganizationContract(
            organization_id=organization.id, contract_no=contract_no,
            title=f"قرارداد پایلوت {organization.name}", created_by=actor_id,
        )
        db.session.add(contract)
    contract.organization_id = organization.id
    contract.status = "active"
    contract.starts_on = date(2026, 10, 1)
    contract.ends_on = date(2027, 9, 30)
    contract.services_json = json.dumps(["پروفایل رشد", "دوره والدگری", "تمرین موقعیت"], ensure_ascii=False)
    contract.terms_text = "داده‌ها نمایشی و مخصوص آزمون پذیرش استیج ۱۵ هستند."
    db.session.flush()
    return contract


def _parent_and_child(index, group):
    mobile = f"{PILOT_MOBILE_PREFIX}{index:06d}"
    user = User.query.filter_by(mobile=mobile).first()
    if not user:
        password = current_app.config.get("PILOT_DEFAULT_PASSWORD", "")
        if not password:
            raise RuntimeError(
                "برای ساخت حساب‌های پایلوت، PILOT_DEFAULT_PASSWORD را خارج از مخزن تنظیم کنید."
            )
        user = User(mobile=mobile, full_name=f"والد پایلوت {index:02d}", role="parent")
        user.set_password(password)
        db.session.add(user)
    user.full_name = f"والد پایلوت {index:02d}"
    user.national_id = f"41{index:08d}"[-10:]
    user.email = f"pilot-parent-{index:02d}@example.test"
    user.role = "parent"
    user.is_active_account = True
    db.session.flush()
    child = Child.query.filter_by(user_id=user.id, national_id=f"51{index:08d}"[-10:]).first()
    if not child:
        child = Child(
            user_id=user.id, national_id=f"51{index:08d}"[-10:],
            name=f"دانش‌آموز پایلوت {index:02d}", birth_year=1390 + (index % 6),
            gender="girl" if index % 2 else "boy",
        )
        db.session.add(child)
    child.notes = f"گروه داده نمایشی: {GROUP_LABELS[group]}"
    db.session.flush()
    return user, child


def _benefit(contract, parent, child):
    row = ContractBeneficiary.query.filter_by(
        contract_id=contract.id, user_id=parent.id, child_id=child.id
    ).first()
    if not row:
        row = ContractBeneficiary(
            contract_id=contract.id, user_id=parent.id, child_id=child.id,
            beneficiary_type="child", status="active", starts_on=contract.starts_on,
            ends_on=contract.ends_on, note="داده نمایشی استیج ۱۵",
        )
        db.session.add(row)
    else:
        row.status = "active"
        row.ended_at = None


def _record(definition, binding, subject_id, values, actor_id):
    record = ProfileRecord.query.filter_by(
        definition_id=definition.id, subject_id=subject_id
    ).first()
    payload = {f"{binding.id}:{key}": value for key, value in values.items()}
    if not record:
        record = ProfileRecord(
            definition_id=definition.id, subject_id=subject_id,
            values_json=json.dumps(payload, ensure_ascii=False), updated_by=actor_id,
        )
        db.session.add(record)
    else:
        record.values_json = json.dumps(payload, ensure_ascii=False)
        record.updated_by = actor_id


def seed_stage15_pilot(actor_id=None):
    """Create exactly 40 pilot children: 20 per contract, 10 shared, 10 independent."""
    actor_id = _admin_id(actor_id)
    forms = _profile_forms(actor_id)
    organization_form = forms["organization"][0]
    org_a = _organization("سازمان افق رشد", "PILOT-A", "02188001001", actor_id, organization_form)
    org_b = _organization("سازمان همراه خانواده", "PILOT-B", "02188001002", actor_id, organization_form)
    contract_a = _contract(org_a, PILOT_CONTRACTS[0], actor_id)
    contract_b = _contract(org_b, PILOT_CONTRACTS[1], actor_id)

    parent_def = active_profile_definition("guardian")
    child_def = active_profile_definition("child")
    org_def = active_profile_definition("organization")
    parent_binding = forms["parent"][1]
    child_binding = forms["child"][1]
    org_binding = forms["organization"][1]

    for index in range(1, 41):
        group = "shared" if index <= 10 else "org_a" if index <= 20 else "org_b" if index <= 30 else "independent"
        parent, child = _parent_and_child(index, group)
        if group in {"shared", "org_a"}:
            _benefit(contract_a, parent, child)
        if group in {"shared", "org_b"}:
            _benefit(contract_b, parent, child)
        _record(parent_def, parent_binding, parent.id, {
            "occupation": ["کارمند", "معلم", "پژوهشگر", "آزاد"][index % 4],
            "education": ["دیپلم", "کارشناسی", "تحصیلات تکمیلی"][index % 3],
            "city": "تهران", "contact_time": ["صبح", "بعدازظهر", "شب"][index % 3],
            "parent_goal": "تقویت گفت‌وگوی آرام و مرزبندی روشن در خانه",
        }, actor_id)
        _record(child_def, child_binding, child.id, {
            "school_grade": ["سوم", "چهارم", "پنجم", "ششم", "هفتم", "هشتم"][index % 6],
            "school_name": "مدرسه نمایشی والدیار", "strength": ["خلاقیت", "همدلی", "پشتکار"][index % 3],
            "trigger": ["فشار مستقیم", "تغییر ناگهانی", "خستگی"][index % 3],
            "support_goal": "افزایش همکاری و بیان هیجان بدون برچسب‌زنی",
        }, actor_id)

    _record(org_def, org_binding, org_a.id, {
        "organization_type": "مؤسسه آموزشی", "staff_count": 80, "family_capacity": 20,
        "preferred_channel": "ایمیل", "service_goal": "پایلوت مسیر رشد خانواده و گزارش اثر تجمیعی",
    }, actor_id)
    _record(org_def, org_binding, org_b.id, {
        "organization_type": "شرکت", "staff_count": 120, "family_capacity": 20,
        "preferred_channel": "تلفن", "service_goal": "افزایش مشارکت والدین در برنامه‌های رشد فرزند",
    }, actor_id)
    db.session.commit()
    return pilot_summary()


def pilot_summary():
    contracts = [OrganizationContract.query.filter_by(contract_no=number).first() for number in PILOT_CONTRACTS]
    contracts = [item for item in contracts if item]
    contract_children = {
        item.contract_no: {row.child_id for row in item.beneficiaries if row.status == "active" and row.child_id}
        for item in contracts
    }
    sets = list(contract_children.values())
    shared = len(sets[0] & sets[1]) if len(sets) == 2 else 0
    all_covered = set().union(*sets) if sets else set()
    pilot_users = User.query.filter(User.mobile.like(f"{PILOT_MOBILE_PREFIX}%")).all()
    pilot_child_ids = {child.id for user in pilot_users for child in user.children}
    return {
        "organizations": Organization.query.filter(Organization.registration_no.in_(["PILOT-A", "PILOT-B"])).count(),
        "contracts": len(contracts),
        "contract_children": {
            contract_no: len(child_ids)
            for contract_no, child_ids in contract_children.items()
        },
        "shared_children": shared,
        "covered_unique": len(all_covered),
        "independent_children": len(pilot_child_ids - all_covered),
        "total_children": len(pilot_child_ids),
        "role_profile_forms": DynamicForm.query.filter(DynamicForm.slug.in_(
            [item["slug"] for item in PROFILE_FORM_SPECS.values()]
        )).count(),
    }

