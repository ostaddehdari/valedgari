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

```bash
read -rsp 'Pilot password: ' PILOT_DEFAULT_PASSWORD
export PILOT_DEFAULT_PASSWORD
flask --app wsgi:app seed-stage15-pilot
unset PILOT_DEFAULT_PASSWORD
```

## پروفایل نقش‌محور

سه فرم منتشرشده برای نقش‌های `parent`، `child` و `organization` ساخته می‌شوند. هر تخصیص نقش به‌طور خودکار به `ProfileDefinition` و `ProfileFormBinding` متناظر وصل می‌شود. بنابراین فیلدهای فرم، همان فیلدهای پروفایل هستند و داده آزمایشی نیز در `ProfileRecord` ذخیره می‌شود.

## عملیات انتشار

1. backup سازگار SQLite و رمزگذاری AES-256 ایجاد می‌شود.
2. دیتابیس بدون Migration استیج ۶ با افزودن ستون‌ها و جدول‌های غایب، بدون حذف داده reconcile می‌شود.
3. وابستگی‌ها نصب و Migration اجرا می‌شود.
4. داده قدیمی پروفایل و پروژه‌های سازمانی بدون overwrite منتقل می‌شود.
5. در صورت فعال بودن `VALEDGARI_SEED_PILOT=1`، پایلوت همگام می‌شود.
6. سرویس restart و `/health/release` بررسی می‌شود.

```bash
VALEDGARI_SEED_PILOT=1 bash deploy/release.sh
```

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
