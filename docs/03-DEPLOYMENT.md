# استقرار در `srun.ir/valedgari`

## معماری پیشنهادی

```text
Browser → HTTPS/Nginx → /valedgari/ → Gunicorn 127.0.0.1:8010 → Flask → SQLite
```

Flask با هدر `X-Forwarded-Prefix: /valedgari` لینک‌های داخلی و فایل‌های استاتیک را با مسیر صحیح تولید می‌کند.

## نصب اولیه روی سرور

```bash
ssh -T -p 2233 root@5.61.27.185
cd /var/www
git clone https://github.com/ostaddehdari/valedgari.git
cd valedgari
bash deploy/install.sh
```

اسکریپت، محیط مجازی، وابستگی‌ها، کلید تصادفی برنامه، systemd و snippet مربوط به Nginx را آماده می‌کند. قبل از reload، `nginx -t` اجرا می‌شود.

## ساخت مدیر بدون افشای رمز در history

```bash
cd /var/www/valedgari
source .venv/bin/activate
set -a; source /etc/valedgari.env; set +a
flask --app wsgi:app create-admin
```

رمز به‌صورت تعاملی و پنهان دریافت می‌شود.

## به‌روزرسانی نسخه

```bash
cd /var/www/valedgari
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart valedgari
systemctl status valedgari --no-pager
curl -fsS http://127.0.0.1:8010/health
```

## بررسی عمومی

```bash
curl -I https://srun.ir/valedgari/
journalctl -u valedgari -n 100 --no-pager
nginx -t
```

## پشتیبان‌گیری

SQLite باید قبل از کپی با فرمان داخلی خودش snapshot شود. اسکریپت زیر نسخه سازگار می‌سازد:

```bash
bash deploy/backup-db.sh
```

پیشنهاد زمان‌بندی: روزانه و نگهداری ۱۴ نسخه. بازیابی باید حداقل ماهانه در محیط جدا آزمایش شود.

## بازگشت نسخه

1. SHA نسخه سالم را از GitHub انتخاب کنید.
2. بکاپ دیتابیس قبل از بازگشت بگیرید.
3. در سرور `git checkout <sha>` و سپس نصب dependency و restart انجام دهید.
4. برای برگشت دیتابیس، ابتدا سرویس را متوقف و snapshot تأییدشده را در مسیر instance جایگزین کنید.

بازگشت کد و دیتابیس دو تصمیم جدا هستند؛ بدون بررسی migration نباید دیتابیس قدیمی جایگزین شود.

