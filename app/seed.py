from .extensions import db
from .models import ScenarioLevel, ScenarioTopic, SkillModule


SKILLS = [
    ("active-listening", "گوش‌دادن فعال", "شنیدن احساس و نیاز پشت کلمات نوجوان، بدون قضاوت عجولانه.", "fa-ear-listen", 12),
    ("empathy", "همدلی", "پاسخ‌دادن به هیجان نوجوان به‌گونه‌ای که احساس فهمیده‌شدن ایجاد شود.", "fa-heart", 10),
    ("problem-solving", "حل مسئله", "تبدیل تعارض به یک مسئله مشترک و یافتن راه‌حل قابل اجرا.", "fa-puzzle-piece", 15),
    ("motivation", "انگیزه‌سازی", "تقویت انگیزه درونی و پرهیز از پاداش و تهدید افراطی.", "fa-bolt", 13),
    ("boundaries", "مرزبندی محترمانه", "ساخت قواعد روشن، منصفانه و قابل پیگیری در خانه.", "fa-shield-heart", 11),
    ("emotion-regulation", "تنظیم هیجان والد", "مکث، نام‌گذاری هیجان و انتخاب پاسخ به‌جای واکنش فوری.", "fa-spa", 9),
]


TOPICS = [
    ("screen-time", "استفاده افراطی از موبایل", "مدیریت زمان صفحه‌نمایش بدون جنگ قدرت", "fa-mobile-screen-button"),
    ("school-drop", "افت تحصیلی", "گفت‌وگو درباره عملکرد مدرسه بدون برچسب‌زنی", "fa-graduation-cap"),
    ("anger", "خشم و پرخاشگری", "کاهش تنش و حفظ مرزهای ایمن", "fa-fire"),
    ("lying", "دروغ‌گویی", "بازسازی اعتماد و یافتن علت پنهان رفتار", "fa-mask-face"),
    ("friends", "تعارض با دوستان", "حمایت از نوجوان بدون تصاحب مسئله", "fa-user-group"),
]


LEVELS = [
    (1, "خفیف"),
    (2, "قابل توجه"),
    (3, "جدی"),
    (4, "شدید"),
    (5, "بحرانی"),
]


def seed_content():
    if SkillModule.query.count() == 0:
        for order, item in enumerate(SKILLS, 1):
            slug, title, description, icon, duration = item
            db.session.add(
                SkillModule(
                    slug=slug,
                    title=title,
                    description=description,
                    icon=icon,
                    duration=duration,
                    sort_order=order,
                )
            )

    if ScenarioTopic.query.count() == 0:
        for slug, title, description, icon in TOPICS:
            topic = ScenarioTopic(slug=slug, title=title, description=description, icon=icon)
            db.session.add(topic)
            db.session.flush()
            for level, label in LEVELS:
                topic.levels.append(
                    ScenarioLevel(
                        level=level,
                        label=label,
                        description=f"این موقعیت در سطح {label} قرار دارد؛ ابتدا شدت هیجان و ایمنی را بسنجید.",
                        recommended_action="آرام بمانید، مشاهده را بدون قضاوت بیان کنید، احساس نوجوان را بازتاب دهید و برای قدم بعدی توافق بگیرید.",
                        wrong_action="تهدید، تحقیر، مقایسه یا تصمیم‌گیری کامل به‌جای نوجوان.",
                        consequence="احتمال مقاومت، پنهان‌کاری یا فاصله عاطفی بیشتر می‌شود. این پیامد قطعی نیست و به زمینه خانواده وابسته است.",
                    )
                )
    db.session.commit()

