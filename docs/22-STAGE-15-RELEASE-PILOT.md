# تحویل استیج ۱۵ — مهاجرت، سخت‌سازی و پایلوت انتشار

## نتیجه تحویل

استیج ۱۵ مسیر توسعه را به یک نسخه قابل انتشار تبدیل می‌کند: schema با Flask-Migrate نسخه‌دار است، داده‌های قدیمی پروفایل حفظ می‌شوند، کارهای سنگین صف و Retry دارند، backup رمزگذاری می‌شود و release دارای health gate و rollback صریح است.

## داده پایلوت قطعی

| گروه | تعداد | قرارداد اول | قرارداد دوم |
|---|---:|:---:|:---:|
| مشترک | ۱۰ | ✓ | ✓ |
| اختصاصی سازمان افق رشد | ۱۰ | ✓ | — |
| اختصاصی سازمان همراه خانواده | ۱۰ | — | ✓ |
| غیرسازمانی | ۱۰ | — | — |
| جمع یکتای دانش‌آموزان | ۴۰ | ۲۰ عضو | ۲۰ عضو |

Seed تکرارپذیر است؛ اجرای دوباره سازمان، قرارداد، والد، فرزند، عضویت یا پروفایل تکراری نمی‌سازد.

همین Seed پنج دوره نمایشی با تصویر محلی مرتبط می‌سازد و برای والد با شماره
`09130134985` یک سفارش، فاکتور، تراکنش پرداخت‌شده و ثبت‌نام دوره ایجاد می‌کند.
این خرید کاملاً نمایشی است و به درگاه واقعی ارسال نمی‌شود.

```bash
read -rsp 'Pilot password: ' PILOT_DEFAULT_PASSWORD
export PILOT_DEFAULT_PASSWORD
flask --app wsgi:app seed-stage15-pilot
unset PILOT_DEFAULT_PASSWORD
```

## پروفایل نقش‌محور

سه فرم منتشرشده برای نقش‌های `parent`، `child` و `organization` ساخته می‌شوند. هر تخصیص نقش به‌طور خودکار به `ProfileDefinition` و `ProfileFormBinding` متناظر وصل می‌شود. بنابراین فیلدهای فرم، همان فیلدهای پروفایل هستند و داده آزمایشی نیز در `ProfileRecord` ذخیره می‌شود.

## عملیات انتشار

فایل‌های CSS و JavaScript محلی با fingerprint محتوایی در URL منتشر می‌شوند. بنابراین
پس از هر انتشار، مرورگر نسخه جدید هدر و پوسته داشبورد را دریافت می‌کند و cache بلندمدت
Nginx باعث نمایش رابط قدیمی نمی‌شود.

1. backup سازگار SQLite و رمزگذاری AES-256 ایجاد می‌شود.
2. دیتابیس بدون Migration استیج ۶ با افزودن ستون‌ها و جدول‌های غایب، بدون حذف داده reconcile می‌شود.
3. وابستگی‌ها نصب و Migration اجرا می‌شود.
4. داده قدیمی پروفایل و پروژه‌های سازمانی بدون overwrite منتقل می‌شود.
5. در صورت فعال بودن `VALEDGARI_SEED_PILOT=1`، پایلوت همگام می‌شود.
6. سرویس restart و `/health/release` بررسی می‌شود.

```bash
VALEDGARI_SEED_PILOT=1 bash deploy/release.sh
```

پس از انتشار، revision و داده‌های نمایشی را بررسی کنید:

```bash
curl -fsS http://127.0.0.1:8010/health/release

sqlite3 /var/www/valedgari/instance/valedgari.db \
  "SELECT version_num FROM alembic_version;"

sqlite3 /var/www/valedgari/instance/valedgari.db \
  "SELECT u.mobile, o.order_no, o.status FROM course_orders o JOIN users u ON u.id=o.user_id WHERE u.mobile='09130134985';"
```

revision مورد انتظار این انتشار `31c0d2e4f5a6` است.

در production مقدار `PILOT_DEFAULT_PASSWORD` باید از قبل در فایل root-only `/etc/valedgari.env` ثبت شده باشد و نباید در خط فرمان قرار گیرد.

## کنترل‌های استیج ۱۵

- ماتریس مرکزی مجوز و مالکیت خانواده
- تشخیص MIME/امضای واقعی و نمونه بدافزار برای upload خصوصی
- حذف password، token، merchant id و authorization از Log
- Index مسیر زمانی خانواده و پاسخ‌های فرم، Pagination و سقف Export
- صف idempotent برای گزارش قرارداد، Import، اعلان و اسکن فایل
- timer یک‌دقیقه‌ای صف، backup روزانه و restore drill هفتگی
- Migration تازه‌نصب و مسیر upgrade دیتابیس موجود
- پل یک‌باره و idempotent برای ارتقای مستقیم SQLite استیج ۶ و حفظ داده‌های قبلی
- smoke test مستقل دیتابیس، revision و شکست‌های terminal صف

فعال‌سازی درگاه واقعی، پیامک واقعی و محتوای علمی استاندارد همچنان به Credential و تأیید تخصصی جداگانه نیاز دارد.
