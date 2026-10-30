import json
import random
from datetime import date

from .models import (
    ParentingStyleDefinition,
    ScenarioNarrative,
    ScenarioNarrativeAttempt,
    ScenarioReaction,
    SkillModule,
)


SCENARIO_CONTRACT = "valedgari-scenario-v1"
REQUIRED_STYLE_CODES = {"authoritative", "authoritarian", "permissive", "uninvolved"}


def bounded_score(value):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def estimated_child_age(child, today=None):
    today = today or date.today()
    year = int(child.birth_year or 0)
    if year > 1900:
        return max(0, today.year - year)
    # Persian birth years are used by the current product. This approximation is
    # enough for content filtering; exact age is not presented as a clinical fact.
    persian_year = today.year - 621 if today.month >= 3 else today.year - 622
    return max(0, persian_year - year)


def narrative_publish_errors(narrative):
    errors = []
    if len((narrative.title or "").strip()) < 3:
        errors.append("عنوان روایت کامل نیست.")
    if len((narrative.context_text or "").strip()) < 20:
        errors.append("متن زمینه روایت باید دست‌کم ۲۰ نویسه باشد.")
    if narrative.child_age_min < 0 or narrative.child_age_max < narrative.child_age_min:
        errors.append("بازه سنی روایت معتبر نیست.")
    reactions = {item.style.code: item for item in narrative.reactions if item.style.is_active}
    missing = REQUIRED_STYLE_CODES - set(reactions)
    if missing:
        errors.append("برای انتشار، واکنش هر چهار سبک پایه الزامی است.")
    for code in sorted(REQUIRED_STYLE_CODES & set(reactions)):
        reaction = reactions[code]
        if len((reaction.reaction_text or "").strip()) < 10:
            errors.append(f"متن واکنش سبک {reaction.style.title} کامل نیست.")
        if not reaction.short_term_consequence.strip():
            errors.append(f"پیامد کوتاه‌مدت سبک {reaction.style.title} ثبت نشده است.")
        if not reaction.long_term_consequence.strip():
            errors.append(f"پیامد بلندمدت سبک {reaction.style.title} ثبت نشده است.")
        if not reaction.retry_guidance.strip():
            errors.append(f"راهنمای تلاش مجدد سبک {reaction.style.title} ثبت نشده است.")
    return errors


def option_order(narrative, user_id, child_id, attempt_count=0):
    ids = [item.id for item in narrative.reactions if item.style.is_active]
    seed = f"{narrative.id}:{user_id}:{child_id}:{attempt_count // 2}"
    random.Random(seed).shuffle(ids)
    return ids


def reaction_options(narrative, ordered_ids):
    reaction_map = {item.id: item for item in narrative.reactions if item.style.is_active}
    return [reaction_map[item_id] for item_id in ordered_ids if item_id in reaction_map]


def choose_narrative(user_id, child, topic_id, level):
    age = estimated_child_age(child)
    base = ScenarioNarrative.query.filter(
        ScenarioNarrative.topic_id == topic_id,
        ScenarioNarrative.level == level,
        ScenarioNarrative.status == "published",
        ScenarioNarrative.child_age_min <= age,
        ScenarioNarrative.child_age_max >= age,
    )
    attempted = {
        item[0]
        for item in ScenarioNarrativeAttempt.query.with_entities(
            ScenarioNarrativeAttempt.narrative_id
        ).filter_by(user_id=user_id, child_id=child.id).all()
    }
    candidates = base.order_by(ScenarioNarrative.id).all()
    fresh = [item for item in candidates if item.id not in attempted]
    pool = fresh or candidates
    if not pool:
        return None, []
    attempt_count = ScenarioNarrativeAttempt.query.filter_by(
        user_id=user_id, child_id=child.id
    ).count()
    narrative = pool[attempt_count % len(pool)]
    return narrative, option_order(narrative, user_id, child.id, attempt_count)


def feedback_for(reaction):
    present = SkillModule.query.filter(SkillModule.id.in_(reaction.present_skill_ids)).all()
    missing = SkillModule.query.filter(SkillModule.id.in_(reaction.missing_skill_ids)).all()
    return {
        "style": reaction.style,
        "score": reaction.scientific_score,
        "present_skills": present,
        "missing_skills": missing,
        "short_term": reaction.short_term_consequence,
        "long_term": reaction.long_term_consequence,
        "retry": reaction.retry_guidance,
    }


def skill_score_summary(user_id, child_id):
    attempts = ScenarioNarrativeAttempt.query.filter_by(
        user_id=user_id, child_id=child_id
    ).order_by(ScenarioNarrativeAttempt.created_at).all()
    totals = {}
    for attempt in attempts:
        reaction = attempt.selected_reaction
        for skill_id in reaction.present_skill_ids:
            item = totals.setdefault(skill_id, {"present": 0, "missing": 0})
            item["present"] += 1
        for skill_id in reaction.missing_skill_ids:
            item = totals.setdefault(skill_id, {"present": 0, "missing": 0})
            item["missing"] += 1
    skills = {item.id: item for item in SkillModule.query.filter(SkillModule.id.in_(totals)).all()} if totals else {}
    return [
        {
            "skill": skills[skill_id],
            "present": values["present"],
            "missing": values["missing"],
            "percent": round(values["present"] / max(1, values["present"] + values["missing"]) * 100),
        }
        for skill_id, values in totals.items()
        if skill_id in skills
    ]


def narrative_to_contract(narrative):
    return {
        "contract": SCENARIO_CONTRACT,
        "narratives": [
            {
                "topic_slug": narrative.topic.slug,
                "level": narrative.level,
                "title": narrative.title,
                "context": narrative.context_text,
                "age_min": narrative.child_age_min,
                "age_max": narrative.child_age_max,
                "child_quote": narrative.child_quote,
                "source_note": narrative.source_note,
                "reactions": [
                    {
                        "style": item.style.code,
                        "text": item.reaction_text,
                        "present_skills": [
                            skill.slug
                            for skill in SkillModule.query.filter(
                                SkillModule.id.in_(item.present_skill_ids)
                            ).all()
                        ],
                        "missing_skills": [
                            skill.slug
                            for skill in SkillModule.query.filter(
                                SkillModule.id.in_(item.missing_skill_ids)
                            ).all()
                        ],
                        "short_term": item.short_term_consequence,
                        "long_term": item.long_term_consequence,
                        "retry": item.retry_guidance,
                        "score": item.scientific_score,
                    }
                    for item in narrative.reactions
                ],
            }
        ],
    }


def validate_contract(payload, topics_by_slug):
    errors = []
    normalized = []
    if not isinstance(payload, dict) or payload.get("contract") != SCENARIO_CONTRACT:
        return [], [f"قرارداد JSON باید {SCENARIO_CONTRACT} باشد."]
    rows = payload.get("narratives")
    if not isinstance(rows, list) or not rows:
        return [], ["فهرست narratives خالی یا نامعتبر است."]
    styles = {item.code: item for item in ParentingStyleDefinition.query.filter_by(is_active=True).all()}
    skills = {item.slug: item for item in SkillModule.query.all()}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"روایت {index} ساختار شیء ندارد.")
            continue
        topic = topics_by_slug.get(str(row.get("topic_slug", "")))
        try:
            level = int(row.get("level", 0))
            age_min = int(row.get("age_min", 6))
            age_max = int(row.get("age_max", 18))
        except (TypeError, ValueError):
            level = age_min = age_max = -1
        reaction_rows = row.get("reactions", [])
        reaction_map = {
            item.get("style"): item
            for item in reaction_rows
            if isinstance(item, dict) and item.get("style") in styles
        }
        if not topic:
            errors.append(f"موضوع روایت {index} یافت نشد.")
        if level not in range(1, 6):
            errors.append(f"سطح روایت {index} باید بین ۱ تا ۵ باشد.")
        if age_min < 0 or age_max < age_min:
            errors.append(f"بازه سنی روایت {index} معتبر نیست.")
        if len(str(row.get("context", "")).strip()) < 20:
            errors.append(f"متن زمینه روایت {index} کوتاه است.")
        if REQUIRED_STYLE_CODES - set(reaction_map):
            errors.append(f"روایت {index} باید هر چهار واکنش پایه را داشته باشد.")
        normalized.append(
            {
                "topic": topic,
                "level": level,
                "title": str(row.get("title", "")).strip()[:180],
                "context_text": str(row.get("context", "")).strip(),
                "child_age_min": age_min,
                "child_age_max": age_max,
                "child_quote": str(row.get("child_quote", "")).strip()[:700],
                "source_note": str(row.get("source_note", "")).strip()[:700],
                "reactions": [
                    {
                        "style": styles[code],
                        "reaction_text": str(reaction_map.get(code, {}).get("text", "")).strip(),
                        "present_skill_ids": [
                            skills[slug].id
                            for slug in reaction_map.get(code, {}).get("present_skills", [])
                            if slug in skills
                        ],
                        "missing_skill_ids": [
                            skills[slug].id
                            for slug in reaction_map.get(code, {}).get("missing_skills", [])
                            if slug in skills
                        ],
                        "short_term_consequence": str(reaction_map.get(code, {}).get("short_term", "")).strip(),
                        "long_term_consequence": str(reaction_map.get(code, {}).get("long_term", "")).strip(),
                        "retry_guidance": str(reaction_map.get(code, {}).get("retry", "")).strip(),
                        "scientific_score": bounded_score(
                            reaction_map.get(code, {}).get("score", 0)
                        ),
                    }
                    for code in sorted(REQUIRED_STYLE_CODES)
                    if code in styles
                ],
            }
        )
    return normalized, errors
