from .extensions import db
import json

from .models import (
    AssessmentInstrument,
    PersonalizationRule,
    ScenarioLevel,
    ScenarioTopic,
    SkillModule,
)


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
    if not AssessmentInstrument.query.filter_by(framework_slug="baumrind").first():
        db.session.add(
            AssessmentInstrument(
                framework_slug="baumrind",
                title="چارچوب سبک‌های فرزندپروری بامریند",
                version="awaiting-scientific-approval",
                status="draft",
                scoring_schema_json=json.dumps(
                    {
                        "scale_min": 1,
                        "scale_max": 5,
                        "method": "weighted_mean_percent",
                        "dimensions": {
                            "authoritative": "مقتدرانه",
                            "authoritarian": "مستبدانه",
                            "permissive": "سهل‌گیرانه",
                        },
                    },
                    ensure_ascii=False,
                ),
                disclaimer=(
                    "این نتیجه برای آموزش و خودبازنگری است و تشخیص بالینی یا برچسب ثابت "
                    "برای والد محسوب نمی‌شود."
                ),
            )
        )

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
        db.session.flush()

    if PersonalizationRule.query.count() == 0 and ScenarioTopic.query.count():
        topics = {item.slug: item for item in ScenarioTopic.query.all()}
        skills = {item.slug: item for item in SkillModule.query.all()}

        def add_rule(
            topic_slug,
            name,
            priority,
            min_severity,
            max_severity,
            conditions,
            title,
            recommendation,
            reason,
            avoid,
            home_action,
            next_step,
            skill_slug=None,
        ):
            topic = topics.get(topic_slug)
            if not topic:
                return
            skill = skills.get(skill_slug) if skill_slug else None
            db.session.add(
                PersonalizationRule(
                    topic_id=topic.id,
                    name=name,
                    status="published",
                    priority=priority,
                    min_severity=min_severity,
                    max_severity=max_severity,
                    conditions_json=json.dumps(conditions, ensure_ascii=False),
                    recommendation_title=title,
                    recommendation_text=recommendation,
                    reason_template=reason,
                    avoid_text=avoid,
                    home_action=home_action,
                    next_step_text=next_step,
                    skill_module_id=skill.id if skill else None,
                )
            )

        topic_defaults = {
            "screen-time": (
                "توافق کوتاه به‌جای جنگ قدرت",
                "مشاهده را بدون سرزنش بگویید، زمان پایان را روشن کنید و بین دو گزینه محدود حق انتخاب بدهید.",
                "تهدید ناگهانی، گرفتن فیزیکی گوشی یا تغییر قانون در اوج تنش.",
                "امروز فقط برای یک نوبت استفاده، زمان پایان و اقدام بعد از آن را با هم بنویسید.",
                "پس از اجرا میزان همکاری و شدت اعتراض را ثبت کنید.",
                "boundaries",
            ),
            "school-drop": (
                "از کنجکاوی شروع کنید، نه بازخواست",
                "ابتدا درباره سخت‌ترین بخش هفته سؤال باز بپرسید؛ سپس فقط یک مانع و یک قدم کوچک را مشخص کنید.",
                "مقایسه نمره، تهدید آینده یا حل کامل مسئله به‌جای نوجوان.",
                "یک گفت‌وگوی ده‌دقیقه‌ای بدون ارائه راه‌حل اجرا و یک مانع را یادداشت کنید.",
                "قدم بعدی را بر اساس مانع واقعی، نه حدس والد انتخاب کنید.",
                "motivation",
            ),
            "anger": (
                "اول تنظیم هیجان، بعد حل مسئله",
                "صدای خود را پایین نگه دارید، مرز ایمنی را کوتاه بگویید و گفت‌وگوی اصلی را به زمان مشخصی بعد از فروکش هیجان منتقل کنید.",
                "بحث منطقی طولانی، تحقیر، نزدیک‌شدن تهدیدآمیز یا مجبورکردن به عذرخواهی فوری.",
                "یک جمله مرزی کوتاه و زمان بازگشت به گفت‌وگو را از قبل آماده کنید.",
                "واکنش فرزند و زمان لازم برای کاهش تنش را ثبت کنید.",
                "emotion-regulation",
            ),
            "lying": (
                "فضای امن برای گفتن حقیقت بسازید",
                "به‌جای بازجویی، نگرانی خود را روشن بگویید و تأکید کنید هدف فهمیدن علت و ترمیم اعتماد است.",
                "برچسب دروغ‌گو، دام‌گذاشتن برای اعتراف یا تنبیه نامتناسب.",
                "در یک موقعیت کوچک، حقیقت‌گویی را بدون سخنرانی طولانی بازتاب دهید.",
                "بررسی کنید آیا امنیت گفتن حقیقت بیشتر شده است یا نه.",
                "empathy",
            ),
            "friends": (
                "کنار نوجوان بمانید، جای او تصمیم نگیرید",
                "احساس او را بازتاب دهید و بپرسید از شما شنیدن، فکرکردن مشترک یا کمک عملی می‌خواهد.",
                "تماس فوری با دوست یا خانواده او، قضاوت دوست یا تصاحب کامل مسئله.",
                "فقط یک بار سؤال کنید: «دوست داری فقط گوش بدهم یا با هم راه‌حل پیدا کنیم؟»",
                "نوع کمکی را که نوجوان پذیرفت ثبت کنید.",
                "active-listening",
            ),
        }

        for slug, values in topic_defaults.items():
            title, action, avoid, home_action, next_step, skill_slug = values
            add_rule(
                slug,
                f"پایه پایلوت {slug}",
                10,
                1,
                5,
                {},
                title,
                action,
                "این مسیر، قاعده پایه مصوب برای زمانی است که داده اختصاصی کافی در دسترس نیست.",
                avoid,
                home_action,
                next_step,
                skill_slug,
            )
            add_rule(
                slug,
                f"ایمنی در شدت بالا {slug}",
                250,
                4,
                5,
                {},
                "اول ایمنی و کاهش تنش",
                "بحث و آموزش را متوقف کنید، فاصله امن بسازید و اگر خطر آسیب وجود دارد از حمایت حضوری متخصص یا مسیر امدادی استفاده کنید.",
                "شدت چهار یا پنج انتخاب شده و ایمنی بر آموزش لحظه‌ای اولویت دارد.",
                "درگیری فیزیکی، تهدید متقابل یا ادامه بحث در اوج برانگیختگی.",
                "فقط ایمنی، فاصله و یک جمله آرام و روشن را اجرا کنید.",
                "پس از امن‌شدن موقعیت، نتیجه را ثبت و برای ارزیابی تخصصی تصمیم بگیرید.",
                "emotion-regulation",
            )
            add_rule(
                slug,
                f"بازتنظیم پس از نتیجه منفی {slug}",
                180,
                1,
                3,
                {"previous_outcomes": ["worsened"]},
                "شدت مداخله را کمتر کنید",
                "چون اقدام قبلی تنش را بیشتر کرده، این بار هدف را فقط کاهش تنش و شنیدن یک جمله از فرزند قرار دهید؛ حل کامل مسئله را عقب بیندازید.",
                "نتیجه ثبت‌شده اقدام قبلی نشان می‌دهد همان روش نباید بدون تعدیل تکرار شود.",
                "تکرار عین همان مداخله، افزودن فشار یا نتیجه‌گیری قطعی درباره شخصیت فرزند.",
                "یک تعامل کوتاه‌تر از پنج دقیقه اجرا و نقطه توقف را از قبل مشخص کنید.",
                "اگر دوباره تنش بیشتر شد، مسیر ارجاع یا بازبینی قاعده را انتخاب کنید.",
                "active-listening",
            )

        profile_rules = [
            (
                "anger",
                "خشم همراه با کناره‌گیری",
                140,
                {"anger_patterns": ["withdrawal"], "calming": ["quiet_space", "time"]},
                "فضا بدهید، اما زمان بازگشت را روشن کنید",
                "به {child} فرصت کوتاه خلوت بدهید و هم‌زمان با یک جمله روشن بگویید چه زمانی برای گفت‌وگوی کوتاه برمی‌گردید.",
                "سکوت ثبت‌شده او احتمالاً به زمان پردازش نیاز دارد؛ رهاکردن نامحدود هم مفید نیست.",
                "دنبال‌کردن مداوم، سؤال‌باران یا تعبیر سکوت به بی‌احترامی.",
                "یک بازه ۱۰ تا ۲۰ دقیقه‌ای و زمان بازگشت مشخص را امتحان کنید.",
                "نتیجه را با مدت آرام‌شدن و پذیرش گفت‌وگو ثبت کنید.",
                "emotion-regulation",
            ),
            (
                "anger",
                "خشم انفجاری",
                145,
                {"anger_patterns": ["explosion"]},
                "کلمات کمتر، مرز ایمنی روشن‌تر",
                "در لحظه انفجار از جمله‌های کوتاه استفاده کنید: احساس را نام ببرید، رفتار آسیب‌زا را متوقف کنید و گفت‌وگو را به بعد موکول کنید.",
                "الگوی واکنش سریع و پرصدا ثبت شده و توضیح طولانی می‌تواند محرک بیشتری بسازد.",
                "سخنرانی، اثبات حقانیت یا نزدیک‌شدن فیزیکی در اوج خشم.",
                "سه جمله کوتاه خود را پیش از موقعیت بنویسید و فقط همان‌ها را اجرا کنید.",
                "پس از آرام‌شدن، میزان اثر جمله‌های کوتاه را ثبت کنید.",
                "emotion-regulation",
            ),
            (
                "screen-time",
                "حساسیت به محدودشدن صفحه",
                145,
                {"triggers": ["screen_limit"], "calming": ["structured_choice"]},
                "پایان قابل پیش‌بینی با دو انتخاب",
                "پنج دقیقه پیش از پایان هشدار دهید و به {child} دو انتخاب محدود بدهید: پایان در زمان توافق یا یک تمدید کوتاه با جبران روشن.",
                "محدودشدن موبایل محرک ثبت‌شده است و انتخاب محدود برای او کمک‌کننده گزارش شده است.",
                "قطع ناگهانی، قانون متغیر یا چانه‌زنی بدون پایان.",
                "برای یک نوبت، هشدار پنج‌دقیقه‌ای و دو انتخاب را اجرا کنید.",
                "میزان اعتراض و پایبندی به پایان را ثبت کنید.",
                "boundaries",
            ),
            (
                "school-drop",
                "افت تحصیلی با حساسیت به انتقاد",
                140,
                {"triggers": ["criticism"], "priorities": ["school"]},
                "عملکرد را از ارزشمندی جدا کنید",
                "گفت‌وگو را با یک مشاهده خنثی و یک نقطه قوت {child} آغاز کنید؛ بعد فقط درباره یک مانع قابل تغییر سؤال کنید.",
                "انتقاد محرک تنش و مدرسه اولویت فعلی ثبت شده است.",
                "تعبیر نمره به تنبلی، بی‌آیندگی یا مقایسه با دیگران.",
                "یک مانع و یک اقدام حداکثر پانزده‌دقیقه‌ای برای فردا تعیین کنید.",
                "اجرای اقدام کوچک، نه تغییر فوری نمره، معیار پیگیری باشد.",
                "motivation",
            ),
            (
                "lying",
                "صداقت در فضای حساس به انتقاد",
                140,
                {"triggers": ["criticism"], "priorities": ["honesty"]},
                "قبل از حقیقت، امنیت رابطه را بالا ببرید",
                "به {child} بگویید حقیقت ممکن است پیامد داشته باشد، اما تحقیر و برچسب نخواهد داشت؛ سپس یک سؤال باز و کوتاه بپرسید.",
                "انتقاد محرک و صداقت اولویت خانواده ثبت شده است.",
                "بازجویی چندباره، تهدید به رسواکردن یا وعده دروغینِ بدون پیامد.",
                "یک قاعده روشن برای حقیقت‌گویی و پیامد قابل پیش‌بینی بنویسید.",
                "بررسی کنید آیا روایت کامل‌تر و پنهان‌کاری کمتر شد.",
                "empathy",
            ),
            (
                "friends",
                "تعارض دوستان همراه با کناره‌گیری",
                135,
                {"anger_patterns": ["withdrawal"], "priorities": ["friends"]},
                "دعوت آرام، بدون وادارکردن به حرف‌زدن",
                "به {child} بگویید آماده شنیدن هستید و یک زمان انتخابی برای گفت‌وگو پیشنهاد دهید؛ سکوت را فوراً با سؤال‌های بیشتر پر نکنید.",
                "کناره‌گیری الگوی ثبت‌شده و رابطه با دوستان اولویت فعلی است.",
                "وادارکردن به تعریف جزئیات، تماس بدون اجازه یا کوچک‌شمردن مسئله.",
                "دو زمان برای گفت‌وگو پیشنهاد دهید و انتخاب را به او بسپارید.",
                "ثبت کنید آیا زمان انتخابی باعث گفت‌وگوی بیشتر شد.",
                "active-listening",
            ),
        ]

        for item in profile_rules:
            slug, name, priority, conditions, title, action, reason, avoid, home, next_step, skill = item
            add_rule(
                slug,
                name,
                priority,
                1,
                3,
                conditions,
                title,
                action,
                reason,
                avoid,
                home,
                next_step,
                skill,
            )
    db.session.commit()

