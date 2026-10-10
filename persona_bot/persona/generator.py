"""
generator.py: seller file (+ evidence) → PersonaSpec, with a reason for every choice.

Decision order for every trait (this is the core idea; say it in the demo):
    1. SPECIFIC EVIDENCE: a strong finding for sellers very like this one
       (two attributes match, e.g. "mid-size traders")        → use it, cite it
    2. THIS SELLER'S OWN HISTORY: a clear signal in their past calls/profile
       (e.g. always "busy", asked what a lead is)             → rule, cite the field
    3. BROAD EVIDENCE: a strong finding for a wide group ("all traders")
    4. SAFE DEFAULT                                            → say so
Why own-history beats broad evidence: an average over thousands of different
sellers can hide sub-groups that behave the opposite way (Simpson's paradox).
What this seller did on their own calls is more relevant.

Deterministic: no randomness and no LLM here, so same seller → same persona.

Usage:  python -m persona_bot.persona.generator            (all files in data/samples/)
        python -m persona_bot.persona.generator data/samples/seller_S001.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from persona_bot.config import CONFIG, PERSONAS_DIR, SAMPLES_DIR
from persona_bot.evidence.miner import SIZE, Evidence
from persona_bot.models import (ConversationPlan, Hook, Language, LiveAdaptation, Opening,
                                PersonaSpec, Play, Reason, Seller, Tone, Voice)
from persona_bot.persona import templates as TPL

ENGLISH_RATIO = {"hi": 0.1, "hinglish": 0.4, "en": 0.95}
NOT_READY = "Not Ready / Needs Time / Early-Stage Seller"
ACCENT = {"hi": "Hindi (neutral North Indian)", "hinglish": "Urban Hinglish", "en": "Indian English"}

NAME_DEVANAGARI = {"Riya": "रिया", "Rohan": "रोहन"}


# ───────────────────────── Seller → attributes ───────────────────────────────
def seller_attrs(s: Seller) -> dict:
    """Flatten a seller into the same attribute names the evidence miner segments on."""
    langs = Counter(c.seller_language for c in s.past_calls if c.duration_sec > 0)
    objs = Counter(o for c in s.past_calls for o in c.objections if o != "none")
    spoken = [c for c in s.past_calls if c.duration_sec > 0]
    return {
        "business_type": s.business_type,
        "size": SIZE[s.turnover_band],
        "turnover_band": s.turnover_band,
        # what they actually speak on calls beats the profile setting
        "seller_language": langs.most_common(1)[0][0] if langs else s.preferred_language,
        "top_objection": objs.most_common(1)[0][0] if objs else "none",
        # helpers for rules (not segment keys)
        "_languages_seen": sorted(langs),
        "_objections": [o for o, _ in objs.most_common()],
        "_avg_turn_words": round(sum(c.avg_seller_turn_words for c in spoken) / len(spoken), 1) if spoken else None,
        # "general" (talked, no commitment) is neutral on purpose: it is not a bad ending
        "_bad_endings": sum(c.outcome in ("disconnected", "not_interested") for c in s.past_calls),
        "_n_calls": len(s.past_calls),
        # seller-level history flags (real data); synthetic sellers leave them empty
        "_frustrated": s.history.showed_frustration,
        "_asked_bot": s.history.asked_if_bot,
        "_not_ready": NOT_READY in s.history.past_objection_categories,
        # years_on_im derived from a GST year is a proxy, so it must not drive decisions
        "_years": None if s.history.years_on_im_is_proxy else s.years_on_im,
    }


# ───────────────────────── Trait deciders ────────────────────────────────────
def decide_language(s: Seller, a: dict, ev: Evidence, used: list) -> Language:
    e = ev.best(a, "bot_language")
    if e:
        used.append(e["key"])
        label, reason = e["value"], Reason(why=f"Sellers like this fix more meetings when the bot speaks {e['value']}.",
                                           source=e["key"])
    else:
        label = a["seller_language"]
        langs = a["_languages_seen"] or [s.preferred_language]
        reason = Reason(why=f"Match the seller: profile says '{s.preferred_language}', past calls were spoken in {', '.join(langs)}.",
                        source="seller.preferred_language + seller.past_calls[].seller_language")

    # Formality: we never START casual (brand safety). Casual is only reached live, if the seller goes casual first.
    allowed = ["aap_formal", "aap_friendly"]
    ef = ev.best(a, "formality", allowed=allowed)
    if ef:
        used.append(ef["key"])
        formality, fwhy, fsrc = ef["value"], f"Evidence favours {ef['value']} for this segment.", ef["key"]
    elif a["size"] == "small" or label == "hi":
        formality, fwhy, fsrc = "aap_formal", "Small or Hindi-first business: respectful 'aap…ji' is expected.", "seller.turnover_band / language"
    elif a["size"] == "large" and label == "en":
        formality, fwhy, fsrc = "aap_friendly", "Large English-first business: friendly-professional, no 'sir' every line.", "seller.turnover_band / language"
    else:
        formality, fwhy, fsrc = "aap_formal", "Safe default: formal until the seller signals otherwise.", "default"
    return Language(
        label=label, primary_code=CONFIG["language_codes"][label], hinglish_ratio=ENGLISH_RATIO[label],
        formality=formality,
        reason=Reason(why=f"{reason.why} Formality: {fwhy}", source=f"{reason.source} ; {fsrc}"))


def decide_tone(s: Seller, a: dict, ev: Evidence, used: list) -> Tone:
    whys, srcs = [], []
    # Verbosity: specific evidence → own history → broad evidence → default
    e = ev.best(a, "verbosity", level="specific")
    own_busy = a["top_objection"] == "busy" or (a["_avg_turn_words"] is not None and a["_avg_turn_words"] < 6)
    own_new = a["_not_ready"] or (a["_years"] is not None and a["_years"] <= 1) or s.engagement.app_active_days_30d < 5
    if not e and not own_busy and not own_new:
        e = ev.best(a, "verbosity", level="broad")
    if e:
        verbosity = e["value"]
        used.append(e["key"])
        whys.append(f"verbosity={verbosity}: evidence ({e['rate']:.0%} vs {e['rest_rate']:.0%} meetings)")
        srcs.append(e["key"])
    elif own_busy:
        verbosity = "crisp"
        whys.append(f"verbosity=crisp: own history, top objection '{a['top_objection']}', seller averages {a['_avg_turn_words']} words per turn")
        srcs.append("seller.past_calls[].objections / avg_seller_turn_words")
    elif own_new:
        verbosity = "explanatory"
        if a["_not_ready"]:
            whys.append(f"verbosity=explanatory: own history, past objection '{NOT_READY}' (new / needs-time seller)")
            srcs.append("seller.history.past_objection_categories")
        else:
            yrs = f"{a['_years']} yr on IM, " if a["_years"] is not None else ""
            whys.append(f"verbosity=explanatory: own history, new or low-engagement seller ({yrs}"
                        f"{s.engagement.app_active_days_30d} active days/30)")
            srcs.append("seller.years_on_im / engagement.app_active_days_30d")
    else:
        verbosity = "normal"
        whys.append("verbosity=normal: no strong signal either way")
        srcs.append("default")

    # Empathy rises with every bad past ending and with trust / lead-quality complaints
    empathy = 2 + a["_bad_endings"] + (1 if set(a["_objections"]) & {"trust", "lead_quality"} else 0)
    if a["_frustrated"]:
        empathy += 2
    empathy = max(1, min(5, empathy))
    whys.append(f"empathy={empathy}: {a['_bad_endings']} past call(s) ended badly"
                + ("; has trust/lead-quality complaints" if set(a["_objections"]) & {"trust", "lead_quality"} else "")
                + ("; showed frustration on a past call (+2), so we apologise early and watch for it" if a["_frustrated"] else ""))
    srcs.append("seller.past_calls[].outcome / objections" + (" / history.showed_frustration" if a["_frustrated"] else ""))

    # Warmth: warmer for new/small sellers (reassurance), steady for busy traders
    new_or_small = (a["_years"] is not None and a["_years"] <= 1) or a["size"] == "small"
    warmth = 3 + (1 if new_or_small else 0) + (1 if a["_asked_bot"] else 0) - (1 if verbosity == "crisp" else 0)
    warmth = max(1, min(5, warmth))
    whys.append(f"warmth={warmth}: {'new/small seller needs reassurance' if warmth > 3 else 'keep it businesslike' if warmth < 3 else 'balanced'}"
                + ("; asked if talking to a bot, so sound natural and less scripted (+1)" if a["_asked_bot"] else ""))
    srcs.append("seller.turnover_band" + (" / history.asked_if_bot" if a["_asked_bot"] else " / seller.years_on_im"))
    if s.history.years_on_im_is_proxy:
        whys.append("years_on_im (from GST year) and subscription are weak signals and were not used")
        srcs.append("weak signal: seller.years_on_im, seller.subscription")
    return Tone(warmth=warmth, empathy=empathy, verbosity=verbosity,
                reason=Reason(why="; ".join(whys), source=" ; ".join(srcs)))


def decide_voice(a: dict, lang: Language, tone: Tone, ev: Evidence, used: list) -> Voice:
    model = CONFIG["sarvam"]["tts_model"]
    whys, srcs = [], []
    eg = ev.best(a, "voice_gender", level="specific")
    if eg:
        gender = eg["value"]
        used.append(eg["key"])
        whys.append(f"gender={gender}: evidence")
        srcs.append(eg["key"])
    else:
        gender = CONFIG["scenario"]["default_gender"]
        whys.append(f"gender={gender}: past calls show no gender effect, so we keep the brand default")
        srcs.append("evidence:voice_gender=none")
    # Pace: specific evidence → follow verbosity when it came from own history → broad evidence
    ep = ev.best(a, "pace_band", level="specific")
    if not ep and "own history" not in tone.reason.why:
        ep = ev.best(a, "pace_band", level="broad")
    if ep:
        band = ep["value"]
        used.append(ep["key"])
        whys.append(f"pace={band}: evidence ({ep['rate']:.0%} vs {ep['rest_rate']:.0%})")
        srcs.append(ep["key"])
    else:
        band = {"crisp": "fast", "explanatory": "slow"}.get(tone.verbosity, "normal")
        whys.append(f"pace={band}: follows verbosity={tone.verbosity}")
        srcs.append("tone.verbosity")
    speaker = CONFIG["voices"][model][gender][lang.label]
    temperature = round(0.45 + 0.075 * (tone.warmth - 1), 2)   # warmth 1→0.45 … 5→0.75
    whys.append(f"speaker={speaker}: {gender} {lang.label} voice from catalogue; temperature={temperature} from warmth={tone.warmth}")
    srcs.append("config.voices / tone.warmth")
    return Voice(tts_model=model, speaker=speaker, gender=gender, accent=ACCENT[lang.label],
                 pace=CONFIG["pace_values"][band], pitch=None, temperature=temperature,
                 reason=Reason(why="; ".join(whys), source=" ; ".join(srcs)))


# ───────────────────────── Conversation plan ─────────────────────────────────
def build_plan(s: Seller, a: dict, voice: Voice, lang: Language, tone: Tone) -> ConversationPlan:
    bot = CONFIG["scenario"]["bot_names"][voice.gender]
    bot_spoken = bot if lang.label == "en" else NAME_DEVANAGARI.get(bot, bot)
    category = s.categories[0]
    opening = TPL.fill(TPL.opening_for(lang.label, lang.formality, tone.verbosity), voice.gender,
                       bot=bot_spoken, business=s.display_name, category=category)

    e = s.engagement
    # Hooks are always positive (untapped demand). The numbers stay in the reason as the data source, but the bot must not quote them.
    hooks = [Hook(hook=f"Mention that buyers in their area are searching for their main product ('{category}') every day.",
                  reason=Reason(why="Shows we know their business and frames the call as untapped demand (the city is not spoken: "
                                    "it is a Latin-script word).", source="seller.categories[0], seller.city"))]
    if e.leads_last_30d >= 10 and e.lead_response_rate < 0.5:
        hooks.append(Hook(hook="Buyers are already sending them enquiries and there is more demand waiting. The advisor can show how to turn "
                               "more of those enquiries into orders. Do not quote lead counts or reply rates.",
                          reason=Reason(why=f"Active buyer demand ({e.leads_last_30d} leads last month) with room to convert more, "
                                            f"framed as an opportunity (reply rate {e.lead_response_rate:.0%}).",
                                        source="engagement.leads_last_30d, lead_response_rate")))
    elif e.leads_last_30d < 10:
        hooks.append(Hook(hook="Many more buyers search for their products than currently reach them. The advisor can show how to put "
                               "their products in front of that demand. Do not quote their lead count.",
                          reason=Reason(why=f"Untapped demand is the clearest value story ({e.leads_last_30d} leads last month).",
                                        source="engagement.leads_last_30d")))
    else:
        hooks.append(Hook(hook="They are an active responder: pitch better-matched, higher-quality buyers rather than just more of them.",
                          reason=Reason(why=f"Engaged sellers care about quality over volume ({e.lead_response_rate:.0%} reply rate).",
                                        source="engagement.lead_response_rate")))
    if a["_years"] is not None and a["_years"] >= 3:
        hooks.append(Hook(hook=f"Thank them for {s.years_on_im} years with IndiaMART.",
                          reason=Reason(why="Loyalty acknowledgement builds goodwill.", source="seller.years_on_im")))

    objections = a["_objections"] + [o for o in ("busy", "not_needed") if o not in a["_objections"]]
    plays = []
    for o in objections:
        if o not in TPL.PLAYBOOK:
            continue
        seen = o in a["_objections"]
        plays.append(Play(
            objection=o,
            response=TPL.fill(TPL.PLAYBOOK[o][lang.label], voice.gender, category=category),
            reason=Reason(why="Raised by this seller before; prepared answer." if seen
                          else "Most common objection overall; always prepared.",
                          source="seller.past_calls[].objections" if seen else "default playbook")))

    escalation = [
        "If the seller asks for a human, or is frustrated on 2 turns in a row: offer an advisor callback at their chosen time and end politely.",
        "If the seller says 'stop calling' / 'band karo': confirm we will stop, apologise, and end the call.",
    ]
    if "lead_quality" in a["_objections"]:
        escalation.append("If lead quality comes up: log it as a complaint and promise the advisor will review lead settings.")
    guardrails = [
        "Never promise a specific number of leads, orders or revenue.",
        "Never quote prices. The meeting is free, and pricing is for the advisor.",
        "Never read out phone numbers, GST or personal details.",
        "Use 'tum' only if the seller uses it first; otherwise 'aap'.",
        f"Stay on the goal: {CONFIG['scenario']['goal']}",
        {"crisp": "Max 2 short sentences per turn; keep the question you ask.", "normal": "Max 2 sentences per turn.",
         "explanatory": "Max 3 short, simple sentences per turn; one idea each."}[tone.verbosity],
    ]
    if a["_asked_bot"]:
        guardrails.append("This seller once asked if they were talking to a bot: sound natural and conversational, not scripted. "
                          "If asked again, answer honestly that you are IndiaMART's AI assistant, then carry on.")
    return ConversationPlan(opening=Opening(line=opening, reason=Reason(
        why=f"{lang.label} / {lang.formality} / {tone.verbosity} template, personalised with business and category.",
        source="language, tone.verbosity, seller.display_name, seller.categories")),
        personalisation=hooks, objection_playbook=plays, escalation_rules=escalation, guardrails=guardrails)


def build_live(s: Seller, a: dict, lang: Language) -> LiveAdaptation:
    watch, why = ["interest"], ["interest: always (it's when we close)"]
    if a["top_objection"] == "busy" or (a["_avg_turn_words"] or 99) < 6:
        watch.append("rush"); why.append("rush: busy objection / short replies before")
    if a["_not_ready"] or (a["_years"] is not None and a["_years"] <= 1) or s.engagement.app_active_days_30d < 5:
        watch.append("confusion")
        why.append("confusion: past objection 'Not Ready / Needs Time / Early-Stage'" if a["_not_ready"]
                   else "confusion: new or low-engagement seller")
    if a["_frustrated"]:
        watch.append("frustration"); why.append("frustration: showed frustration on a past call")
    elif a["_bad_endings"]:
        watch.append("frustration"); why.append(f"frustration: {a['_bad_endings']} bad past ending(s)")
    if len(a["_languages_seen"]) > 1:
        watch.append("language_switch"); why.append(f"language_switch: has spoken {', '.join(a['_languages_seen'])}")
    other = [l for l in a["_languages_seen"] if l != lang.label]
    fallback = other[0] if other else ("en" if lang.label != "en" else "hinglish")
    return LiveAdaptation(watch_for=watch, fallback_language=fallback,
                          max_switches_per_call=CONFIG["live"]["max_switches_per_call"],
                          reason=Reason(why="; ".join(why) + f"; fallback language {fallback}",
                                        source="seller.past_calls, seller.engagement, seller.history"))
    # Note: the live detector watches ALL signals; 'watch_for' marks the expected ones
    # (shown in the UI and used to lower the threshold slightly for them).


# ───────────────────────── Public API ────────────────────────────────────────
def uses_synthetic_evidence(seller_id: str) -> bool:
    """evidence/persona_effects.json is mined from SYNTHETIC calls. Real sellers (ids 'R...') must not be driven by it."""
    return not seller_id.startswith("R")


def generate(seller: Seller, evidence: Evidence | None = None) -> PersonaSpec:
    if uses_synthetic_evidence(seller.seller_id):
        ev = evidence or Evidence()
    else:
        ev = Evidence({"cells": {}})       # own history and rules only, until evidence is mined from real data
    a = seller_attrs(seller)
    used: list[str] = []
    lang = decide_language(seller, a, ev, used)
    tone = decide_tone(seller, a, ev, used)
    voice = decide_voice(a, lang, tone, ev, used)
    return PersonaSpec(
        seller_id=seller.seller_id,
        segment=f"{a['size']}_{a['business_type']}_{a['seller_language']}_{a['top_objection']}",
        voice=voice, language=lang, tone=tone,
        conversation_plan=build_plan(seller, a, voice, lang, tone),
        live_adaptation=build_live(seller, a, lang),
        evidence_used=used)


def load_seller(path: Path) -> Seller:
    return Seller(**json.loads(Path(path).read_text(encoding="utf-8")))


def run(paths: list[Path] | None = None) -> list[PersonaSpec]:
    paths = paths or sorted(SAMPLES_DIR.glob("*.json"))
    ev = Evidence()
    out = []
    for p in paths:
        spec = generate(load_seller(p), ev)
        (PERSONAS_DIR / f"{spec.seller_id}.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        out.append(spec)
    return out


if __name__ == "__main__":
    specs = run([Path(p) for p in sys.argv[1:]] or None)
    for sp in specs:
        print(f"{sp.seller_id}  {sp.segment:38} lang={sp.language.label:8} {sp.language.formality:12} "
              f"verb={sp.tone.verbosity:11} pace={sp.voice.pace} spk={sp.voice.speaker:7} "
              f"emp={sp.tone.empathy} watch={sp.live_adaptation.watch_for}  evidence={len(sp.evidence_used)}")
