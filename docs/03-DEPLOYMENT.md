# راهنمای نصب صفر تا صد والدیار

این راهنما برای نصب یکپارچه همه استیج‌های ۱ تا ۱۵ روی `https://srun.ir/valedgari/` است. شاخه `main` آخرین نسخه یکپارچه را نصب می‌کند.

## ۱) پیش‌نیازها

- Ubuntu 22.04 یا 24.04 با دسترسی `root`
- رکورد DNS دامنه `srun.ir` روی IP سرور
- server block فعال Nginx برای `srun.ir` و گواهی HTTPS معتبر
- دسترسی خروجی سرور به GitHub و مخازن Ubuntu
- حداقل 1 GB RAM و 2 GB فضای آزاد برای پایلوت

```text
مرورگر → HTTPS/Nginx → /valedgari/ → Gunicorn :8010 → Flask → SQLite
```

## ۲) نصب اولیه روی سرور

از رایانه خود وارد سرور شوید:

```bash
ssh -T -p 2233 root@5.61.27.185
```

سپس داخل سرور اجرا کنید:

```bash
apt-get update
apt-get install -y git
install -d -m 755 /var/www
cd /var/www
git clone https://github.com/ostaddehdari/valedgari.git
cd /var/www/valedgari
VALEDGARI_NGINX_VHOST=/etc/nginx/sites-enabled/unified-gateway bash deploy/install.sh
```

اسکریپت به‌صورت idempotent محیط Python، دیتابیس، secret، Gunicorn، systemd، Nginx، بکاپ روزانه، مانور بازیابی هفتگی و health check پنج‌دقیقه‌ای را آماده می‌کند.

نسخه پشتیبان تنظیمات Nginx در `/var/backups/valedgari/nginx/` ذخیره می‌شود و هرگز داخل `sites-enabled` قرار نمی‌گیرد.

اگر server block دامنه خودکار پیدا نشد، این خط را داخل بلوک `server` مربوط به `srun.ir` اضافه کنید:

```nginx
include /etc/nginx/snippets/valedgari.conf;
```

سپس:

```bash
nginx -t
systemctl reload nginx
```

## ۳) ساخت حساب مدیر و ناظر علمی

رمزها تعاملی هستند و وارد history نمی‌شوند:

```bash
cd /var/www/valedgari
source .venv/bin/activate
set -a; source /etc/valedgari.env; set +a
flask --app wsgi:app create-admin
flask --app wsgi:app create-reviewer
```

مدیر محتوا را آماده و برای بررسی ارسال می‌کند؛ حساب ناظر علمی مستقل همان snapshot را تأیید یا رد می‌کند.

## ۴) تست بعد از نصب

```bash
systemctl status valedgari --no-pager
systemctl list-timers 'valedgari-*' --all
curl -fsS http://127.0.0.1:8010/health/ready
curl -fsS http://127.0.0.1:8010/health/release
curl -I https://srun.ir/valedgari/
journalctl -u valedgari -n 100 --no-pager
```

خروجی readiness باید `status: ok` و `database: available` داشته باشد.

## ۵) نصب محلی برای بررسی قبل از سرور

```bash
git clone https://github.com/ostaddehdari/valedgari.git
cd valedgari
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
flask --app wsgi:app create-admin
flask --app wsgi:app run --debug
```

سپس `http://127.0.0.1:5000` را باز و تست‌ها را اجرا کنید:

```bash
pytest -q
```

## ۶) تنظیمات production

فایل `/etc/valedgari.env` فقط برای root قابل خواندن است:

```dotenv
FLASK_ENV=production
SECRET_KEY=generated-secret
DATABASE_URL=sqlite:////var/www/valedgari/instance/valedgari.db
APP_VERSION=stage-15
AUTO_CREATE_SCHEMA=0
ADMIN_PAGE_SIZE=50
EXPORT_ROW_LIMIT=5000
REQUIRE_SCIENTIFIC_APPROVAL=1
ANONYMOUS_REPORT_MIN_GROUP=5
PAYMENT_PROVIDER=manual
PAYMENT_MERCHANT_ID=
PAYMENT_MODE=disabled
PUBLIC_BASE_URL=https://srun.ir/valedgari
```

تا زمان دریافت Credential، `PAYMENT_MODE=disabled` بماند. Merchant ID زرین‌پال و Token پیامک از صفحه «تنظیم سرویس‌ها» به‌صورت رمز‌شده ثبت می‌شوند و نباید در Git یا Log قرار گیرند. پس از دریافت کلید، ابتدا Sandbox و پیام آزمایشی IPPanel اجرا و سپس Production فعال شود.

پس از تغییر env:

```bash
systemctl restart valedgari
```

## ۷) به‌روزرسانی نسخه

```bash
cd /var/www/valedgari
git pull --ff-only
VALEDGARI_SEED_PILOT=1 bash deploy/release.sh
```

## ۸) بکاپ و مانور بازیابی

اجرای دستی:

```bash
systemctl start valedgari-backup.service
systemctl start valedgari-restore-test.service
journalctl -u valedgari-backup.service -u valedgari-restore-test.service -n 100 --no-pager
```

فایل‌ها در `/var/backups/valedgari/` با دسترسی root و پسوند `.db.gz.enc` ذخیره می‌شوند. کلید مستقل `/etc/valedgari-backup.key` است و نباید همراه backup کپی شود. مانور بازیابی، آخرین backup را فقط در `/tmp` رمزگشایی می‌کند، integrity و تعداد جدول‌ها را می‌سنجد و به دیتابیس production دست نمی‌زند.

## ۹) بازگشت نسخه

1. SHA نسخه سالم و فایل backup رمزگذاری‌شده قبل از انتشار را انتخاب کنید.
2. با تأیید صریح اجرا کنید:

```bash
VALEDGARI_ROLLBACK_CONFIRM=ROLLBACK bash deploy/rollback.sh <GOOD_SHA> /var/backups/valedgari/<BACKUP>.db.gz.enc
```

3. readiness، گزارش مالی و تعداد ذی‌نفعان را پس از بازگشت کنترل کنید.

کد و دیتابیس دو rollback مستقل‌اند. backup قدیمی را بدون بررسی schema روی دیتابیس جاری جایگزین نکنید.

## ۱۰) عیب‌یابی سریع

```bash
journalctl -u valedgari -f
journalctl -u nginx -n 100 --no-pager
nginx -t
ss -lntp | grep 8010
systemctl restart valedgari
curl -v http://127.0.0.1:8010/health/ready
```

- خطای 502: سرویس و پورت 8010 را بررسی کنید.
- خطای 404 زیر `/valedgari`: include مربوط به Nginx و `X-Forwarded-Prefix` را بررسی کنید.
- خطای permission دیتابیس: مالک پوشه `instance` باید `www-data:www-data` باشد.
- خطای scientific gate: یک حساب reviewer بسازید و همان نسخه محتوا را در کارتابل تأیید کنید.
