"""
prompt.py: turns the LIVE persona into the LLM system prompt, rebuilt every turn.

Rebuilding every turn is what makes a mid-call switch real: when the policy sets
verbosity=crisp and adds a "seller is in a hurry" directive, the very next
reply is generated under the new instructions, and the next TTS call uses the
new pace and language. There's no hidden state in the LLM.
"""
from __future__ import annotations

from persona_bot.config import CONFIG
from persona_bot.models import PersonaSpec, Seller

SCRIPT_RULE = (
    "Write ALL Hindi in Devanagari, and write English business words in Devanagari too (टाइम, लीड्स, बायर्स, मीटिंग, एडवाइजर, स्लॉट, फ्री, मिनट, क्वालिटी, प्रोडक्ट). The ONLY Latin-script word allowed is the brand IndiaMART, and do not mix Latin and Devanagari letters in one sentence. Say the seller's product in Devanagari (e.g. 'कंट्रोल वाल्व्स') or just 'आपके प्रोडक्ट्स'; never say their business name or city out loud (say 'आपके एरिया')."
)
FRAMING_RULE = (
    "Never use negative or deficit framing: do not quote how few leads they got, their reply rate, 'zero leads', or say their profile "
    "or catalogue is weak. Always frame it as untapped demand: buyers in their area are searching for their products every day."
)
LANG_RULE = {
    "hi": "Speak natural, simple spoken Hindi. " + SCRIPT_RULE,
    "hinglish": "Speak natural Hinglish, the way urban Indian business people talk: Hindi grammar with everyday English business words. "
                + SCRIPT_RULE,
    "en": "Speak simple, clear Indian English. Short sentences.",
}
FORMALITY_RULE = {
    "aap_formal": "Always use 'aap' and add 'ji' (or 'sir/madam' in English). Respectful.",
    "aap_friendly": "Use 'aap', friendly and professional, without 'ji/sir' in every line.",
    "casual": "The seller is casual. You may be relaxed, but stay polite.",
}
VERBOSITY_RULE = {
    "crisp": "Reply in one or two SHORT sentences (max ~20 words): answer first, then your question. Never drop the question you are asking.",
    "normal": "Reply in at most 2 short sentences.",
    "explanatory": "Reply in at most 3 short, simple sentences, one idea each. Use an everyday example if useful.",
}


def system_prompt(p: PersonaSpec, seller: Seller, directives: list[str]) -> str:
    bot = CONFIG["scenario"]["bot_names"][p.voice.gender]
    plan = p.conversation_plan
    plays = "\n".join(f"- If '{x.objection}': {x.response}" for x in plan.objection_playbook)
    hooks = "\n".join(f"- {h.hook}" for h in plan.personalisation)
    cats = ", ".join(seller.categories)
    if p.language.label != "en":            # product names are Latin-script data: the bot says "आपके प्रोडक्ट्स" instead
        for c in seller.categories:
            hooks = hooks.replace(f"'{c}'", "'आपके प्रोडक्ट्स'").replace(c, "आपके प्रोडक्ट्स")
        cats = "products you do not need to name"
    live = "\n".join(f"- {d}" for d in reversed(directives)) or "- (none yet)"
    return f"""You are {bot}, a {p.voice.gender} voice agent calling from {CONFIG['scenario']['company']}.
You are on a PHONE CALL with a {seller.business_type}{' in ' + seller.city if p.language.label == 'en' else ''} selling {cats}.
GOAL: {CONFIG['scenario']['goal']}

LANGUAGE: {LANG_RULE[p.language.label]}
FORMALITY: {FORMALITY_RULE[p.language.formality]}
LENGTH: {VERBOSITY_RULE[p.tone.verbosity]}
FRAMING: {FRAMING_RULE}
TONE: warmth {p.tone.warmth}/5, empathy {p.tone.empathy}/5. {"Acknowledge feelings before answering." if p.tone.empathy >= 4 else "Be businesslike."}

USE THESE FACTS (don't recite them all; weave in one at a time):
{hooks}

OBJECTION PLAYBOOK (adapt the wording, keep the meaning):
{plays}

ESCALATION:
{chr(10).join('- ' + e for e in plan.escalation_rules)}

GUARDRAILS:
{chr(10).join('- ' + g for g in plan.guardrails)}

LIVE ADJUSTMENTS (the seller's current state; the most recent is most important):
{live}

OUTPUT FORMAT: Only the exact words you will SAY. No stage directions, no emojis, no markdown, no lists, no quotes.
If the seller agrees to a time, confirm it in one sentence and thank them."""
