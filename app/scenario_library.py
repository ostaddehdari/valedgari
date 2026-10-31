"""Idempotent Stage 15 professional scenario draft library.

The generated narratives are complete enough for scientific review, but remain
drafts. Crisis levels organize educational content and are not diagnoses.
"""

import json

from .extensions import db
from .models import (
    ParentingStyleDefinition,
    ScenarioNarrative,
    ScenarioReaction,
    ScenarioTopic,
    SkillModule,
)


LIBRARY_PREFIX = "stage15-professional"
REQUIRED_STYLES = ("authoritative", "authoritarian", "permissive", "uninvolved")

LEVEL_COPY = {
    1: ("سطحی", "برای نخستین بار یا به‌صورت پراکنده دیده شده و هنوز اختلال مهمی در روال روزانه ایجاد نکرده است"),
    2: ("آشکار", "در چند نوبت تکرار شده و بر همکاری یا آرامش یک بخش از روز اثر قابل مشاهده گذاشته است"),
    3: ("پیش‌رونده", "در حال تبدیل‌شدن به یک الگوی پایدار است و هم‌زمان بر رابطه، مدرسه یا خواب اثر می‌گذارد"),
    4: ("قوی / خطرناک", "شدت تعارض بالاست؛ پیش از آموزش باید ایمنی، حمایت یک بزرگسال امن و ارزیابی حضوری در نظر گرفته شود"),
    5: ("عمیق", "الگو مزمن یا همراه با نشانه خطر است؛ آموزش عمومی کافی نیست و ارزیابی تخصصی حضوری اولویت دارد"),
}

# Two distinct, concrete settings per topic. The level copy supplies the graded
# intensity while these profiles keep the 250 drafts varied and recognizable.
TOPIC_CASES = {
    "screen-time": (("پایان زمان توافق‌شده بازی آنلاین", "فقط همین دست را تمام کنم؛ شما اصلاً نمی‌فهمید وسط بازی نمی‌شود رفت."), ("موبایل در زمان خواب و افت انرژی صبح", "همه دوستانم شب آنلاین‌اند؛ اگر گوشی را بدهم از جمع جا می‌مانم.")),
    "school-drop": (("کارنامه‌ای با افت ناگهانی در دو درس", "می‌دانم نمره‌ام بد شده؛ لطفاً دوباره مقایسه‌ام نکنید."), ("پیام مدرسه درباره کاهش مشارکت کلاسی", "حوصله کلاس را ندارم و حس می‌کنم هر کاری کنم فایده ندارد.")),
    "anger": (("کوبیدن در پس از یک محدودیت خانگی", "الان با من حرف نزنید؛ اگر ادامه بدهید بدتر می‌شوم."), ("فریاد در جریان اختلاف با خواهر یا برادر", "همیشه طرف او را می‌گیرید و اصلاً حرف من را نمی‌شنوید.")),
    "lying": (("پنهان‌کردن نتیجه آزمون از والد", "می‌ترسیدم بگویم چون فکر کردم فقط عصبانی می‌شوید."), ("گفتن محل متفاوت برای رفت‌وآمد عصر", "اگر راستش را می‌گفتم مطمئن بودم اجازه نمی‌دادید.")),
    "friends": (("حذف‌شدن از گروه دوستان مدرسه", "نمی‌خواهم دخالت کنید؛ فقط خیلی احساس تنهایی می‌کنم."), ("دعوا با دوست صمیمی پس از انتشار یک پیام", "هم عصبانی‌ام هم دلم می‌خواهد دوباره با او حرف بزنم.")),
    "sleep-routine": (("بیدارماندن تا نیمه‌شب در روزهای مدرسه", "شب تنها زمانی است که کسی از من چیزی نمی‌خواهد."), ("خواب طولانی عصر و دشواری بیدارشدن صبح", "واقعاً خسته‌ام؛ با زنگ هم نمی‌توانم از تخت بلند شوم.")),
    "homework-resistance": (("شروع‌نکردن تکلیف با وجود نزدیک‌شدن موعد", "نمی‌دانم از کجا شروع کنم و هر بار بیشتر گیج می‌شوم."), ("رهاکردن تکلیف دشوار پس از چند دقیقه", "وقتی جوابش را بلد نیستم حس می‌کنم خیلی ضعیفم.")),
    "sibling-conflict": (("برداشتن وسیله شخصی بدون اجازه", "هر بار وسایلم را برمی‌دارد و هیچ‌کس جدی نمی‌گیرد."), ("رقابت بر سر توجه والد در مهمانی", "فقط وقتی او حرف می‌زند همه گوش می‌دهند.")),
    "disrespect": (("استفاده از لحن تحقیرآمیز هنگام درخواست والد", "وقتی مدام تکرار می‌کنید از کوره در می‌روم."), ("قطع‌کردن گفت‌وگو با ناسزا پس از مخالفت", "حس کردم هیچ اختیاری ندارم و فقط می‌خواستم بحث تمام شود.")),
    "household-rules": (("بازگشت دیرتر از ساعت توافق‌شده", "زمان از دستم رفت؛ فکر کردم اگر زنگ بزنم دعوا می‌شود."), ("انجام‌ندادن سهم کار خانه", "برنامه‌ام شلوغ بود و قانون خانه همیشه یک‌طرفه به نظر می‌رسد.")),
    "spending": (("خرج‌کردن تمام پول توجیبی در ابتدای ماه", "آن لحظه خیلی می‌خواستمش و فکر نکردم بعداً پول لازم دارم."), ("خرید درون‌برنامه‌ای بدون هماهنگی", "همه هم‌تیمی‌ها خریدند و می‌ترسیدم از گروه عقب بمانم.")),
    "eating": (("ردکردن غذای خانواده و تنش سر میز", "وقتی درباره مقدار غذایم حرف می‌زنید بیشتر عصبی می‌شوم."), ("حذف مکرر وعده صبحانه پیش از مدرسه", "صبح اشتها ندارم و از حرف‌زدن درباره وزنم خسته‌ام.")),
    "isolation": (("ماندن طولانی در اتاق پس از مدرسه", "فعلاً انرژی حرف‌زدن ندارم؛ فقط می‌خواهم تنها باشم."), ("ردکردن دیدارهای خانوادگی و دوستان", "کنار بقیه بودن خسته‌ام می‌کند و نمی‌دانم چه بگویم.")),
    "anxiety": (("نگرانی شدید پیش از ارائه کلاسی", "قلبم تند می‌زند و مطمئنم جلوی همه خراب می‌کنم."), ("پرسش‌های تکراری درباره امنیت اعضای خانواده", "اگر جوابم را ندهید ذهنم بدترین اتفاق را می‌سازد.")),
    "peer-pressure": (("دعوت دوستان به کاری خلاف قانون مدرسه", "اگر نه بگویم مسخره‌ام می‌کنند و دیگر دعوتم نمی‌کنند."), ("فشار گروه برای انتشار عکس خصوصی", "نمی‌خواهم بفرستم، ولی می‌ترسم بگویند بچه‌ام.")),
    "bullying": (("پیام‌های تحقیرآمیز تکراری در گروه کلاس", "اگر به مدرسه بگویید شاید بیشتر سراغم بیایند."), ("هل‌دادن و تهدید در مسیر بازگشت", "نمی‌خواهم فردا بروم؛ حس می‌کنم هیچ‌جا امن نیست.")),
    "romantic-relations": (("ناراحتی پس از قطع یک رابطه عاطفی", "لطفاً نگویید بچگانه است؛ برای من واقعاً مهم بود."), ("اختلاف والد و نوجوان درباره مرزهای دیدار", "می‌خواهم به من اعتماد کنید و درباره قانون با من حرف بزنید.")),
    "online-safety": (("دریافت پیام تهدیدآمیز از حساب ناشناس", "می‌ترسم اگر بلاکش کنم عکس‌هایم را پخش کند."), ("درخواست اطلاعات یا تصویر خصوصی در چت", "اول فکر کردم دوستم است؛ حالا نمی‌دانم چطور بیرون بیایم.")),
    "substance-risk": (("پیداشدن وسیله مشکوک در کیف نوجوان", "مال من نیست؛ اگر بازجویی کنید دیگر هیچ‌چیز نمی‌گویم."), ("بازگشت از جمع دوستان با تغییر واضح رفتار", "فقط یک بار بود؛ نمی‌خواهم با تهدید همه‌چیز بدتر شود.")),
    "self-harm-signals": (("دیدن نوشته‌ای درباره بی‌ارزشی و نخواستن ادامه", "نمی‌دانم می‌خواهم چه کار کنم؛ فقط خیلی خسته‌ام."), ("مشاهده زخم‌های توضیح‌داده‌نشده روی دست", "قول نمی‌دهم تکرار نشود؛ الان به کمک نیاز دارم، نه دعوا.")),
    "truancy": (("غیبت پنهانی از یک کلاس خاص", "در آن کلاس تحقیر می‌شوم و نمی‌دانستم چطور بگویم."), ("نرفتن چندروزه به مدرسه با شکایت جسمی", "فکر رفتن حالم را بد می‌کند؛ فقط تنبل نیستم.")),
    "stealing": (("برداشتن پول از کیف یکی از اعضای خانه", "می‌ترسیدم درخواست کنم و جواب نه بشنوم."), ("برداشتن وسیله همکلاسی و پنهان‌کردن آن", "همه چیزهای بهتری دارند؛ می‌خواستم یک بار من هم داشته باشم.")),
    "responsibility": (("رهاکردن وسایل و کارهای شخصی برای دیگران", "وقتی چند کار را با هم می‌گویید گیج می‌شوم و هیچ‌کدام را شروع نمی‌کنم."), ("فراموش‌کردن تعهد گروهی یا خانوادگی", "یادم رفت، ولی وقتی می‌گویید بی‌مسئولیتم دیگر انگیزه جبران ندارم.")),
    "body-image": (("اجتناب از عکس و مقایسه بدن با دیگران", "هر بار عکس خودم را می‌بینم فقط ایرادهایم را می‌بینم."), ("پیروی سخت‌گیرانه از توصیه‌های ظاهری شبکه اجتماعی", "اگر شبیه آن‌ها نباشم حس می‌کنم هیچ‌کس دوستم ندارد.")),
    "career-choice": (("اصرار خانواده بر رشته‌ای متفاوت از علاقه نوجوان", "می‌ترسم آینده‌ام را برای خواسته دیگران زندگی کنم."), ("سردرگمی میان چند مسیر تحصیلی و شغلی", "هنوز مطمئن نیستم؛ فشار برای تصمیم فوری بیشتر گیجم می‌کند.")),
}


def _skill_ids(skills, *slugs):
    return [skills[slug].id for slug in slugs if slug in skills]


def _reaction_payload(style, topic, quote, level, target_slug, skills):
    safety = level >= 4
    target = target_slug if target_slug in skills else "problem-solving"
    base_present = [target, "active-listening", "empathy", "emotion-regulation"]
    all_core = ["active-listening", "empathy", "problem-solving", "boundaries", "emotion-regulation"]
    if style == "authoritative":
        response = (
            f"والد پس از مکث می‌گوید: «می‌شنوم که این موقعیت برایت سخت شده. اول می‌خواهم مطمئن شوم امنی؛ "
            f"بعد بدون سرزنش درباره {topic.title} و یک قدم کوچک و روشن با هم تصمیم می‌گیریم.»"
        ) if safety else (
            f"والد با مکث و لحن آرام می‌گوید: «از حرفت می‌فهمم الان تحت فشار هستی. درباره {topic.title} "
            "یک مرز روشن داریم؛ بیا نیاز هر دو طرف را بگوییم و یک راه‌حل کوتاه و قابل بازبینی بسازیم.»"
        )
        return response, base_present, [], (
            "احتمال کاهش تنش و بیشترشدن آمادگی نوجوان برای گفت‌وگو وجود دارد؛ نتیجه به زمینه و زمان‌بندی وابسته است."
        ), (
            "با تکرار این الگو ممکن است اعتماد، خودتنظیمی و مشارکت در حل مسئله تقویت شود؛ این پیامد قطعی نیست."
        ), (
            "ابتدا یک بازتاب کوتاه بگویید، سپس فقط یک مرز یا قدم ایمنی را روشن کنید و زمان بازبینی مشخص بگذارید."
        ), 95
    if style == "authoritarian":
        return (
            f"والد با صدای بلند می‌گوید: «درباره {topic.title} بحثی نداریم؛ همین حالا اطاعت کن وگرنه مجازات می‌شوی.»"
        ), ["boundaries"], ["active-listening", "empathy", "emotion-regulation", "problem-solving"], (
            "ممکن است رفتار برای مدتی متوقف شود، اما احتمال ترس، خشم یا پنهان‌کاری بیشتر می‌شود."
        ), (
            "در تکرار طولانی ممکن است فاصله عاطفی و اطاعت ظاهری جای یادگیری تصمیم‌گیری را بگیرد؛ این نتیجه قطعی نیست."
        ), (
            "تهدید را متوقف کنید، شدت صدای خود را پایین بیاورید، تجربه نوجوان را بازتاب دهید و پیامد مرتبط را کوتاه بیان کنید."
        ), 25
    if style == "permissive":
        return (
            f"والد برای جلوگیری از ناراحتی می‌گوید: «می‌دانم سخت است؛ درباره {topic.title} هر طور خودت راحتی عمل کن.»"
        ), ["active-listening", "empathy"], ["boundaries", "problem-solving"], (
            "ممکن است تنش همان لحظه کم شود، اما مرز و انتظار رفتاری همچنان مبهم می‌ماند."
        ), (
            "اگر پیگیری شکل نگیرد، احتمال تکرار الگو و دشواری در پذیرش پیامدهای طبیعی بیشتر می‌شود؛ قطعی نیست."
        ), (
            "همدلی را نگه دارید و بلافاصله پس از آن یک مرز قابل اجرا، دو انتخاب محدود و زمان پیگیری تعیین کنید."
        ), 40
    return (
        f"والد بدون پیگیری می‌گوید: «الان وقت این حرف‌ها را ندارم؛ مسئله {topic.title} را خودت حل کن.»"
    ), [], all_core, (
        "احتمال دارد گفت‌وگو قطع شود و نوجوان احساس تنهایی یا بی‌اهمیت‌بودن کند."
    ), (
        "در صورت تکرار، فاصله رابطه و رفتارهای پنهانی ممکن است افزایش یابد؛ این پیامد تضمین‌شده نیست."
    ), (
        "به گفت‌وگو برگردید، مسئولیت قطع ارتباط را بپذیرید، یک سؤال باز بپرسید و برای پیگیری زمان مشخص بگذارید."
    ), 10


def seed_professional_scenario_library():
    """Create two review-ready drafts for every topic at every crisis level."""
    topics = {item.slug: item for item in ScenarioTopic.query.all()}
    skills = {item.slug: item for item in SkillModule.query.all()}
    styles = {
        item.code: item
        for item in ParentingStyleDefinition.query.filter(
            ParentingStyleDefinition.code.in_(REQUIRED_STYLES)
        ).all()
    }
    missing_topics = sorted(set(TOPIC_CASES) - set(topics))
    missing_styles = sorted(set(REQUIRED_STYLES) - set(styles))
    if missing_topics or missing_styles or not skills:
        raise RuntimeError(
            "پیش‌نیاز کتابخانه روایت کامل نیست؛ ابتدا داده پایه مهارت، موقعیت و سبک‌ها را ایجاد کنید. "
            f"missing_topics={missing_topics} missing_styles={missing_styles}"
        )

    target_slugs = {}
    for topic in topics.values():
        if topic.catalog_profile and topic.catalog_profile.target_skill:
            target_slugs[topic.slug] = topic.catalog_profile.target_skill.slug
        elif topic.skills:
            target_slugs[topic.slug] = topic.skills[0].slug
        else:
            target_slugs[topic.slug] = "problem-solving"

    narratives_created = reactions_created = 0
    seeded = {}
    for topic_slug, cases in TOPIC_CASES.items():
        topic = topics[topic_slug]
        for variant, (setting, quote) in enumerate(cases, 1):
            for level, (level_title, level_detail) in LEVEL_COPY.items():
                marker = f"{LIBRARY_PREFIX}:{topic_slug}:v{variant}:l{level}"
                narrative = ScenarioNarrative.query.filter(
                    ScenarioNarrative.topic_id == topic.id,
                    ScenarioNarrative.level == level,
                    ScenarioNarrative.source_note.like(f"{marker}%"),
                ).first()
                if not narrative:
                    context = (
                        f"در موقعیت «{setting}»، نوجوان {quote!r} می‌گوید. این نشانه در سطح {level_title} "
                        f"سازمان‌دهی شده است؛ {level_detail}. والد باید پیش از نتیجه‌گیری، زمینه، تکرار رفتار، "
                        "اثر آن بر عملکرد و ایمنی را بررسی کند. این سطح تشخیص بالینی نیست."
                    )
                    narrative = ScenarioNarrative(
                        topic_id=topic.id,
                        level=level,
                        title=f"{setting} · سطح {level_title}"[:180],
                        context_text=context,
                        child_age_min=11,
                        child_age_max=18,
                        child_quote=quote,
                        status="draft",
                        source_note=marker,
                    )
                    db.session.add(narrative)
                    db.session.flush()
                    narratives_created += 1
                seeded[(topic_slug, variant, level)] = narrative
                existing_styles = {item.style.code for item in narrative.reactions}
                for style_code in REQUIRED_STYLES:
                    if style_code in existing_styles:
                        continue
                    text, present, missing, short, long, retry, score = _reaction_payload(
                        style_code,
                        topic,
                        quote,
                        level,
                        target_slugs[topic_slug],
                        skills,
                    )
                    db.session.add(
                        ScenarioReaction(
                            narrative_id=narrative.id,
                            style_id=styles[style_code].id,
                            reaction_text=text,
                            present_skill_ids_json=json.dumps(
                                _skill_ids(skills, *present), ensure_ascii=False
                            ),
                            missing_skill_ids_json=json.dumps(
                                _skill_ids(skills, *missing), ensure_ascii=False
                            ),
                            short_term_consequence=short,
                            long_term_consequence=long,
                            retry_guidance=retry,
                            scientific_score=score,
                        )
                    )
                    reactions_created += 1
    db.session.flush()

    # Rebuild only the navigation fields for this managed library; narrative and
    # reaction copy remains untouched after an editor changes it.
    for (topic_slug, variant, level), narrative in seeded.items():
        previous = seeded.get((topic_slug, variant, level - 1))
        growth = seeded.get((topic_slug, variant, level - 1))
        fall = seeded.get((topic_slug, variant, level + 1))
        narrative.previous_narrative_id = previous.id if previous else None
        narrative.growth_next_narrative_id = growth.id if growth else None
        narrative.fall_next_narrative_id = fall.id if fall else None

    db.session.commit()
    total_narratives = ScenarioNarrative.query.filter(
        ScenarioNarrative.source_note.like(f"{LIBRARY_PREFIX}:%")
    ).count()
    narrative_ids = [item.id for item in seeded.values()]
    total_reactions = ScenarioReaction.query.filter(
        ScenarioReaction.narrative_id.in_(narrative_ids)
    ).count()
    missing_cells = 0
    for topic_slug in TOPIC_CASES:
        for level in LEVEL_COPY:
            if not all((topic_slug, variant, level) in seeded for variant in (1, 2)):
                missing_cells += 1
    return {
        "topics": len(TOPIC_CASES),
        "levels": len(LEVEL_COPY),
        "variants_per_level": 2,
        "narratives_created": narratives_created,
        "narratives_total": total_narratives,
        "reactions_created": reactions_created,
        "reactions_total": total_reactions,
        "missing_cells": missing_cells,
        "status": "draft",
    }
