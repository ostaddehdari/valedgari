from .extensions import db
import json

from .models import (
    AssessmentInstrument,
    Course,
    CourseChapter,
    CourseSkillMembership,
    CourseTopicMembership,
    CourseUnit,
    CrisisLevelDefinition,
    MicroLesson,
    ParentingStyleDefinition,
    PersonalizationRule,
    ProfileDefinition,
    ScenarioLevel,
    ScenarioTopic,
    ScenarioTopicProfile,
    SafetyProtocol,
    SkillDomain,
    SkillDomainMembership,
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
    ("screen-time", "استفاده افراطی از موبایل", "مدیریت زمان صفحه‌نمایش بدون جنگ قدرت", "fa-mobile-screen-button", "سبک زندگی دیجیتال", "boundaries"),
    ("school-drop", "افت تحصیلی", "گفت‌وگو درباره عملکرد مدرسه بدون برچسب‌زنی", "fa-graduation-cap", "تحصیل", "motivation"),
    ("anger", "خشم و پرخاشگری", "کاهش تنش و حفظ مرزهای ایمن", "fa-fire", "هیجان", "emotion-regulation"),
    ("lying", "دروغ‌گویی", "بازسازی اعتماد و یافتن علت پنهان رفتار", "fa-mask-face", "اعتماد", "empathy"),
    ("friends", "تعارض با دوستان", "حمایت از نوجوان بدون تصاحب مسئله", "fa-user-group", "روابط همسالان", "active-listening"),
    ("sleep-routine", "بی‌نظمی خواب", "ساخت روال خواب با مشارکت نوجوان", "fa-moon", "سبک زندگی", "boundaries"),
    ("homework-resistance", "مقاومت در برابر تکلیف", "شناخت مانع شروع و قدم کوچک", "fa-book-open", "تحصیل", "motivation"),
    ("sibling-conflict", "تعارض خواهر و برادر", "داوری نکردن و آموزش حل تعارض", "fa-people-arrows", "روابط خانوادگی", "problem-solving"),
    ("disrespect", "گفتار بی‌احترام", "حفظ شأن دوطرف و مرز گفت‌وگو", "fa-comment-slash", "ارتباط", "boundaries"),
    ("household-rules", "مقاومت در برابر قوانین خانه", "بازنگری قانون و پیامد مرتبط", "fa-house-lock", "مرزبندی", "boundaries"),
    ("spending", "خرج‌کردن و پول توجیبی", "آموزش انتخاب و پیامد مالی", "fa-wallet", "مسئولیت", "problem-solving"),
    ("eating", "تعارض درباره غذا", "پرهیز از شرم و ساخت انتخاب سالم", "fa-utensils", "سلامت روزمره", "empathy"),
    ("isolation", "کناره‌گیری و انزوا", "حفظ حضور امن بدون فشار", "fa-door-closed", "پیوند عاطفی", "active-listening"),
    ("anxiety", "نگرانی و اضطراب", "همراهی با هیجان و قدم قابل کنترل", "fa-cloud", "هیجان", "empathy"),
    ("peer-pressure", "فشار همسالان", "تمرین نه‌گفتن و تصمیم مستقل", "fa-users-rays", "روابط همسالان", "problem-solving"),
    ("bullying", "قلدری و آزار همسالان", "ایمنی، ثبت شواهد و حمایت بزرگسال", "fa-shield", "ایمنی", "problem-solving"),
    ("romantic-relations", "روابط عاطفی نوجوان", "گفت‌وگوی محترمانه درباره مرز و امنیت", "fa-heart", "روابط", "active-listening"),
    ("online-safety", "ایمنی در فضای مجازی", "حریم خصوصی و واکنش به تهدید آنلاین", "fa-user-shield", "ایمنی دیجیتال", "boundaries"),
    ("substance-risk", "خطر مصرف مواد", "اولویت ایمنی، گفت‌وگو و ارجاع", "fa-triangle-exclamation", "ریسک", "emotion-regulation"),
    ("self-harm-signals", "نشانه‌های آسیب به خود", "توقف آموزش عادی و فعال‌سازی حمایت تخصصی", "fa-life-ring", "ریسک", "emotion-regulation"),
    ("truancy", "غیبت از مدرسه", "یافتن علت و برنامه بازگشت", "fa-school-circle-xmark", "تحصیل", "problem-solving"),
    ("stealing", "برداشتن مال دیگران", "ترمیم، مسئولیت و بررسی نیاز زمینه‌ای", "fa-hand", "اعتماد", "problem-solving"),
    ("responsibility", "بی‌مسئولیتی در کارهای شخصی", "تقسیم کار و پیگیری بدون کنترل افراطی", "fa-list-check", "مسئولیت", "motivation"),
    ("body-image", "نگرانی از ظاهر و بدن", "گفت‌وگوی بدون قضاوت و شرم", "fa-person", "هویت", "empathy"),
    ("career-choice", "تعارض بر سر آینده و رشته", "شناخت ارزش‌ها و تصمیم مشارکتی", "fa-compass", "آینده", "active-listening"),
]


LEVELS = [
    (1, "سطحی"),
    (2, "آشکار"),
    (3, "پیش‌رونده"),
    (4, "قوی / خطرناک"),
    (5, "عمیق"),
]


CRISIS_LEVELS = [
    (1, "surface", "سطحی", "#4f9d7d", "رفتار پراکنده و کم‌اثر که با گفت‌وگوی کوتاه قابل مدیریت است.", ["تکرار کم", "تنش پایین", "اختلال محدود"]),
    (2, "visible", "آشکار", "#7a9b43", "الگوی رفتاری قابل مشاهده که به توافق روشن و پیگیری نیاز دارد.", ["تکرار قابل مشاهده", "اعتراض کلامی", "اثر کوتاه بر روال"]),
    (3, "progressive", "پیش‌رونده", "#d09a32", "الگو در حال تثبیت است و بر چند بخش زندگی اثر می‌گذارد.", ["افزایش تکرار", "افت همکاری", "اثر بر خواب یا مدرسه"]),
    (4, "strong-risky", "قوی / خطرناک", "#d66a3c", "تنش یا رفتار شدید است و ارزیابی ایمنی باید مقدم باشد.", ["تهدید یا پرخاش", "اختلال جدی", "نیاز به حمایت بزرگسال"]),
    (5, "deep", "عمیق", "#a93f55", "مسئله عمیق، مزمن یا همراه با خطر است و آموزش عمومی کافی نیست.", ["خطر آسیب", "گسست شدید عملکرد", "نیاز به ارجاع تخصصی"]),
]


PARENTING_STYLES = [
    ("authoritative", "مقتدرانه", "گرمی رابطه همراه با مرز روشن و مشارکت متناسب با سن.", ["همدلی", "مرز روشن", "گفت‌وگو", "پیامد مرتبط"], "#176254"),
    ("authoritarian", "مستبدانه", "کنترل و اطاعت بالا با گفت‌وگو و انعطاف کم.", ["دستور", "تنبیه", "کنترل بالا", "گفت‌وگوی کم"], "#a44848"),
    ("permissive", "سهل‌گیرانه", "گرمی بالا با مرز و پیگیری ناکافی.", ["پذیرش", "مرز کم", "پیگیری کم", "اجتناب از تعارض"], "#c48a2b"),
    ("uninvolved", "غافلانه", "درگیری عاطفی و نظارت اندک یا پاسخ‌گویی نامنظم.", ["فاصله", "نظارت کم", "پاسخ‌گویی کم", "عدم پیگیری"], "#697a76"),
]


SKILL_DOMAINS = [
    ("parent-self-regulation", "خودتنظیمی والد", "مکث، شناخت هیجان و انتخاب پاسخ پیش از واکنش.", "fa-spa"),
    ("connection", "ارتباط و پیوند عاطفی", "شنیدن، همدلی و ساخت احساس امنیت در رابطه.", "fa-heart"),
    ("boundaries", "مرزبندی، قانون و پیامد", "قواعد روشن، انتخاب محدود و پیامد قابل پیش‌بینی.", "fa-shield-heart"),
    ("development-motivation", "شناخت رشد و انگیزه", "دیدن نیاز رشدی و تقویت انگیزه درونی نوجوان.", "fa-seedling"),
    ("problem-conflict", "حل مسئله و تعارض", "تبدیل اختلاف به مسئله مشترک و توافق کوچک.", "fa-puzzle-piece"),
    ("risk-referral", "موقعیت ویژه، ریسک و ارجاع", "تشخیص مرز آموزش، اولویت ایمنی و مراجعه به حمایت تخصصی.", "fa-life-ring"),
]


DOMAIN_SKILLS = {
    "parent-self-regulation": ["emotion-regulation"],
    "connection": ["active-listening", "empathy"],
    "boundaries": ["boundaries"],
    "development-motivation": ["motivation"],
    "problem-conflict": ["problem-solving"],
    "risk-referral": ["emotion-regulation"],
}


MICRO_LESSONS = [
    ("pause-before-response", "parent-self-regulation", "emotion-regulation", "مکث سه‌مرحله‌ای پیش از پاسخ", "والد بتواند میان محرک و واکنش چند ثانیه فاصله بسازد.", "توقف کنید، یک بازدم آرام انجام دهید و فقط احساس خود را نام ببرید؛ سپس یک جمله کوتاه انتخاب کنید.", "امروز پیش از یک پاسخ دشوار، سه ثانیه مکث و یک بازدم آرام را تمرین کنید.", "مکث را به سکوت تنبیهی یا بی‌اعتنایی طولانی تبدیل نکنید."),
    ("reflect-before-solve", "connection", "active-listening", "پیش از راه‌حل، بازتاب بدهید", "والد بتواند یک احساس یا نیاز را بدون قضاوت بازتاب دهد.", "بازتاب یعنی حدس محترمانه از تجربه فرزند: «به نظر می‌آید این اتفاق واقعاً خسته‌ات کرده». بعد مکث کنید.", "در یک گفت‌وگوی پنج‌دقیقه‌ای فقط یک بازتاب دقیق بگویید و سؤال پشت سؤال نپرسید.", "بازتاب را با «اما» یا نصیحت فوری خنثی نکنید."),
    ("name-the-feeling", "connection", "empathy", "نام‌گذاری هیجان بدون برچسب", "والد هیجان را از شخصیت و ارزشمندی فرزند جدا کند.", "درباره حالت همین لحظه حرف بزنید، نه هویت ثابت: «الان عصبانی به نظر می‌رسی» به‌جای «تو همیشه عصبی هستی».", "یک جمله هیجانی بدون واژه‌های همیشه، هیچ‌وقت و تو آدمِ... بسازید.", "حدس خود را حقیقت قطعی اعلام نکنید؛ امکان اصلاح به فرزند بدهید."),
    ("clear-kind-boundary", "boundaries", "boundaries", "مرز کوتاه، روشن و محترمانه", "والد بتواند مرز را بدون تهدید و سخنرانی بیان کند.", "مرز مؤثر سه جزء دارد: رفتار قابل قبول، زمان یا محدوده روشن، و پیامد قابل پیش‌بینی و مرتبط.", "یک قانون خانه را در کمتر از پانزده کلمه بازنویسی کنید.", "در اوج تعارض قانون تازه نسازید یا پیامد نامرتبط تعیین نکنید."),
    ("small-motivation-step", "development-motivation", "motivation", "انگیزه با قدم کوچک", "والد نتیجه بزرگ را به یک اقدام کوچک و قابل شروع تبدیل کند.", "به‌جای پرسیدن «چرا انجام ندادی؟» مانع شروع را پیدا کنید و قدمی انتخاب کنید که در پانزده دقیقه انجام شود.", "یک کار عقب‌افتاده را به اولین قدم حداکثر پانزده‌دقیقه‌ای تبدیل کنید.", "پاداش بزرگ یا تهدید را جایگزین فهم مانع واقعی نکنید."),
    ("shared-problem", "problem-conflict", "problem-solving", "مسئله مشترک، نه نبرد دو نفر", "والد و نوجوان بتوانند مسئله را بدون مقصرسازی تعریف کنند.", "دو نیاز را کنار هم بنویسید: نیاز والد و نیاز نوجوان. سپس یک راه‌حل آزمایشی کوتاه برای هر دو انتخاب کنید.", "یک تعارض را با جمله «چطور می‌توانیم هم... و هم...» بازنویسی کنید.", "راه‌حل از پیش تعیین‌شده را با ظاهر سؤال به فرزند تحمیل نکنید."),
    ("safety-first", "risk-referral", "emotion-regulation", "وقتی آموزش باید متوقف شود", "والد بداند در خطر فوری، ایمنی بر گفت‌وگو و آموزش مقدم است.", "اگر احتمال آسیب به خود یا دیگری وجود دارد، بحث را متوقف، فاصله امن ایجاد و از حمایت حضوری تخصصی یا امدادی استفاده کنید.", "شماره‌ها و دو فرد امن خانواده را برای موقعیت ضروری از قبل مشخص کنید.", "در بحران وارد بحث اثبات حقانیت، تنبیه یا مهار فیزیکی بدون آموزش نشوید."),
]


COURSE_SEEDS = [
    {
        "slug": "pause-before-reaction",
        "title": "آرامش پیش از واکنش",
        "subtitle": "یک مسیر کوتاه برای تنظیم هیجان والد در لحظه‌های دشوار",
        "description": "در این دوره یاد می‌گیرید پیش از پاسخ تکانه‌ای مکث کنید، هیجان خود را نام‌گذاری کنید و گفت‌وگو را در زمان امن ادامه دهید.",
        "level": "foundation",
        "price": 0,
        "skills": ["emotion-regulation"],
        "topics": ["anger"],
        "styles": ["general", "authoritarian"],
        "featured": True,
        "chapters": [
            ("شناخت لحظه تنش", [("چرخه محرک تا واکنش", "text", "محرک، برداشت، هیجان و پاسخ را از هم جدا کنید. هدف این نیست که خشم حذف شود؛ هدف ساختن فاصله‌ای کوتاه برای انتخاب پاسخ است."), ("تمرین مکث سه‌مرحله‌ای", "text", "توقف، یک بازدم آرام و نام‌گذاری هیجان؛ سپس فقط یک جمله کوتاه و محترمانه بگویید.")]),
            ("انتقال به خانه", [("برنامه یک موقعیت واقعی", "text", "یک موقعیت پرتکرار را انتخاب کنید و جمله جایگزین خود را پیش از رخ‌دادن آن بنویسید.")]),
        ],
    },
    {
        "slug": "active-listening-course",
        "title": "گوش‌دادن فعال به نوجوان",
        "subtitle": "شنیدن احساس و نیاز، پیش از ارائه راه‌حل",
        "description": "دوره‌ای کاربردی برای بازتاب احساس، سؤال باز و جلوگیری از نصیحت زودهنگام در گفت‌وگوهای روزمره.",
        "level": "foundation",
        "price": 390000,
        "skills": ["active-listening", "empathy"],
        "topics": ["school-drop", "friends"],
        "styles": ["authoritative", "general"],
        "featured": True,
        "chapters": [
            ("شنیدن بدون قضاوت", [("سه مانع شنیدن", "text", "بازجویی، راه‌حل فوری و مقایسه سه مانع رایج شنیدن هستند."), ("بازتاب دقیق", "text", "یک احساس یا نیاز را به صورت حدس محترمانه بازتاب دهید و فرصت اصلاح بدهید.")]),
        ],
    },
    {
        "slug": "respectful-boundaries",
        "title": "مرزبندی محترمانه در خانه",
        "subtitle": "قانون روشن، انتخاب محدود و پیامد مرتبط",
        "description": "برای خانواده‌هایی که می‌خواهند بدون تهدید و جنگ قدرت، مرزهای قابل پیش‌بینی و قابل پیگیری بسازند.",
        "level": "intermediate",
        "price": 490000,
        "skills": ["boundaries", "problem-solving"],
        "topics": ["screen-time", "lying"],
        "styles": ["authoritative", "permissive"],
        "featured": True,
        "chapters": [
            ("ساخت قانون قابل اجرا", [("قانون کوتاه و روشن", "text", "قانون را درباره رفتار قابل مشاهده و در کمتر از پانزده کلمه بنویسید."), ("پیامد مرتبط", "text", "پیامد باید از قبل قابل پیش‌بینی، مرتبط با رفتار و بدون تحقیر باشد.")]),
        ],
    },
]


SAFETY_PROTOCOLS = [
    (
        "immediate-harm-risk",
        "خطر فوری آسیب به خود یا دیگری",
        ["خودکشی", "خودکشی می", "خودزنی", "آسیب به خود", "می‌کشم", "میکشم", "بکشم", "کشتن", "چاقو", "اسلحه", "تهدید جدی"],
        "الان ایمنی از آموزش مهم‌تر است",
        "در این وضعیت ادامه گفت‌وگوی آموزشی کافی نیست. اگر خطر فوری یا ابزار آسیب وجود دارد، فرزند را تنها نگذارید، فاصله امن ایجاد کنید و همین حالا از خدمات اضطراری محل زندگی یا یک متخصص حضوری کمک بگیرید.",
        ["بحث و سرزنش را متوقف کنید.", "ابزار آسیب را فقط در صورت امن‌بودن از دسترس دور کنید.", "یک بزرگسال امن دیگر را در جریان بگذارید.", "برای کمک حضوری فوری اقدام کنید."],
        300,
    ),
    (
        "violence-abuse-risk",
        "خشونت یا آزار جدی",
        ["کتک شدید", "آزار جنسی", "تجاوز", "حبس", "شکنجه", "فرار از خانه", "امن نیست", "کتکم می‌زند", "من را می‌زند"],
        "این موضوع به حمایت تخصصی و ایمنی نیاز دارد",
        "این نشانه‌ها فراتر از یک تمرین والدگری روزمره‌اند. ابتدا امنیت کودک یا نوجوان را تأمین کنید و برای ارزیابی حضوری از خدمات حمایتی، متخصص واجد صلاحیت یا خدمات اضطراری محل زندگی کمک بگیرید.",
        ["کودک را برای توضیح فوری تحت فشار نگذارید.", "موضوع را محرمانه اما بدون پنهان‌کردن خطر ثبت کنید.", "با فرد یا مرکز حمایت‌کننده معتبر تماس بگیرید."],
        250,
    ),
    (
        "medical-emergency",
        "فوریت پزشکی یا روان‌پزشکی",
        ["بیهوش", "تشنج", "اوردوز", "مصرف قرص", "توهم شدید", "نفس نمی", "مسموم"],
        "برای فوریت پزشکی اقدام کنید",
        "این سامانه برای ارزیابی فوریت پزشکی طراحی نشده است. منتظر پاسخ آنلاین نمانید و با خدمات اضطراری محل زندگی یا نزدیک‌ترین مرکز درمانی تماس بگیرید.",
        ["وضعیت تنفس و هوشیاری را بررسی کنید.", "اطلاعات ماده یا داروی مصرف‌شده را نگه دارید.", "راهنمایی اپراتور خدمات اضطراری را دنبال کنید."],
        280,
    ),
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

    if SafetyProtocol.query.count() == 0:
        for item in SAFETY_PROTOCOLS:
            slug, title, keywords, response_title, response_text, steps, priority = item
            db.session.add(
                SafetyProtocol(
                    slug=slug,
                    title=title,
                    trigger_keywords_json=json.dumps(keywords, ensure_ascii=False),
                    response_title=response_title,
                    response_text=response_text,
                    immediate_steps_json=json.dumps(steps, ensure_ascii=False),
                    status="published",
                    priority=priority,
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

    for slug, title, description, icon, _domain, _skill_slug in TOPICS:
        topic = ScenarioTopic.query.filter_by(slug=slug).first()
        if not topic:
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
        else:
            topic.title = title
            topic.description = description
            topic.icon = icon
            existing_levels = {item.level: item for item in topic.levels}
            for level, label in LEVELS:
                if level in existing_levels:
                    existing_levels[level].label = label
                else:
                    db.session.add(
                        ScenarioLevel(
                            topic_id=topic.id,
                            level=level,
                            label=label,
                            description=f"این موقعیت در سطح {label} قرار دارد؛ ابتدا شدت هیجان و ایمنی را بسنجید.",
                        )
                    )
    db.session.flush()

    if CrisisLevelDefinition.query.count() == 0:
        for order, item in enumerate(CRISIS_LEVELS, 1):
            level, code, title, color, description, markers = item
            db.session.add(
                CrisisLevelDefinition(
                    level=level,
                    code=code,
                    title=title,
                    color=color,
                    description=description,
                    behavioral_markers_json=json.dumps(markers, ensure_ascii=False),
                    sort_order=order,
                )
            )

    if ParentingStyleDefinition.query.count() == 0:
        for order, item in enumerate(PARENTING_STYLES, 1):
            code, title, description, traits, color = item
            db.session.add(
                ParentingStyleDefinition(
                    code=code,
                    title=title,
                    description=description,
                    traits_json=json.dumps(traits, ensure_ascii=False),
                    color=color,
                    sort_order=order,
                )
            )
    db.session.flush()

    topics = {item.slug: item for item in ScenarioTopic.query.all()}
    skills = {item.slug: item for item in SkillModule.query.all()}
    for order, item in enumerate(TOPICS, 1):
        slug, _title, _description, _icon, domain, skill_slug = item
        topic = topics.get(slug)
        if topic:
            profile = ScenarioTopicProfile.query.filter_by(topic_id=topic.id).first()
            if not profile:
                db.session.add(
                    ScenarioTopicProfile(
                        topic_id=topic.id,
                        domain=domain,
                        target_skill_id=skills.get(skill_slug).id if skills.get(skill_slug) else None,
                        status="active",
                        sort_order=order,
                    )
                )
            else:
                profile.domain = domain
                profile.target_skill_id = skills.get(skill_slug).id if skills.get(skill_slug) else None
                profile.sort_order = order
    db.session.flush()

    if SkillDomain.query.count() == 0:
        db.session.flush()
        modules = {item.slug: item for item in SkillModule.query.all()}
        domains = {}
        for order, item in enumerate(SKILL_DOMAINS, 1):
            slug, title, description, icon = item
            domain = SkillDomain(
                slug=slug,
                title=title,
                description=description,
                icon=icon,
                sort_order=order,
            )
            db.session.add(domain)
            db.session.flush()
            domains[slug] = domain
            for skill_order, skill_slug in enumerate(DOMAIN_SKILLS.get(slug, []), 1):
                module = modules.get(skill_slug)
                if module:
                    db.session.add(
                        SkillDomainMembership(
                            domain_id=domain.id,
                            module_id=module.id,
                            learning_level=("safety" if slug == "risk-referral" else "foundation"),
                            sort_order=skill_order,
                        )
                    )
        db.session.flush()

    if MicroLesson.query.count() == 0:
        domains = {item.slug: item for item in SkillDomain.query.all()}
        modules = {item.slug: item for item in SkillModule.query.all()}
        for order, item in enumerate(MICRO_LESSONS, 1):
            slug, domain_slug, module_slug, title, objective, body, practice, pitfall = item
            if domain_slug not in domains or module_slug not in modules:
                continue
            db.session.add(
                MicroLesson(
                    domain_id=domains[domain_slug].id,
                    module_id=modules[module_slug].id,
                    slug=slug,
                    title=title,
                    objective=objective,
                    body=body,
                    practice=practice,
                    common_pitfall=pitfall,
                    duration=7,
                    status="published",
                    sort_order=order,
                )
            )
        db.session.flush()

    if Course.query.count() == 0:
        modules = {item.slug: item for item in SkillModule.query.all()}
        topics = {item.slug: item for item in ScenarioTopic.query.all()}
        for course_order, item in enumerate(COURSE_SEEDS, 1):
            course = Course(
                slug=item["slug"],
                title=item["title"],
                subtitle=item["subtitle"],
                description=item["description"],
                instructor_name="تیم علمی والدیار",
                level=item["level"],
                duration_minutes=sum(
                    7 for _chapter_title, units in item["chapters"] for _unit in units
                ),
                price_toman=item["price"],
                style_tags_json=json.dumps(item["styles"], ensure_ascii=False),
                status="published",
                version=1,
                is_featured=item["featured"],
                sort_order=course_order,
            )
            db.session.add(course)
            db.session.flush()
            for skill_order, skill_slug in enumerate(item["skills"]):
                skill = modules.get(skill_slug)
                if skill:
                    db.session.add(
                        CourseSkillMembership(
                            course_id=course.id,
                            skill_id=skill.id,
                            is_primary=skill_order == 0,
                            sort_order=skill_order,
                        )
                    )
            for topic_slug in item["topics"]:
                topic = topics.get(topic_slug)
                if topic:
                    db.session.add(
                        CourseTopicMembership(course_id=course.id, topic_id=topic.id)
                    )
            for chapter_order, (chapter_title, units) in enumerate(item["chapters"], 1):
                chapter = CourseChapter(
                    course_id=course.id,
                    title=chapter_title,
                    sort_order=chapter_order,
                )
                db.session.add(chapter)
                db.session.flush()
                for unit_order, (unit_title, unit_type, body) in enumerate(units, 1):
                    db.session.add(
                        CourseUnit(
                            chapter_id=chapter.id,
                            title=unit_title,
                            unit_type=unit_type,
                            body=body,
                            duration_minutes=7,
                            is_preview=course_order == 1 and chapter_order == 1 and unit_order == 1,
                            sort_order=unit_order,
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
    for profile_type, title in (
        ("organization", "پروفایل سازمان"),
        ("guardian", "پروفایل والد / سرپرست"),
        ("child", "پروفایل فرزند"),
    ):
        if not ProfileDefinition.query.filter_by(profile_type=profile_type).first():
            db.session.add(
                ProfileDefinition(
                    profile_type=profile_type,
                    title=title,
                    version=1,
                    status="active",
                )
            )
    db.session.commit()

