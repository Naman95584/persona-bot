"""
signal_detector.py: reads ONE seller turn and says how the seller feels right now.

Five signals (from the deck): frustration, confusion, interest, language_switch, rush.

How it works (rules mode, the default):
  * Lexicons: phrases in Devanagari, romanised Hindi and English, each with a
    weight (strong 0.8 / medium 0.5 / weak 0.3). Matched weights add up to a
    confidence, capped at 0.95.
  * Features: very short replies (rush), speaking fast (rush), one-word "kya?"
    (confusion), repeated refusals across turns (frustration), and a language
    change vs. the bot's current language (language_switch).

Why rules first, LLM optional?
  * Rules run in < 1 ms. An LLM adds ~0.5–1.5 s to every turn, and voice
    latency is 20% of the score.
  * Rules are explainable: the switch log can quote the exact words that
    triggered a switch ("kitni baar call karoge").
  * "hybrid" mode (config live.detector_mode) adds an LLM opinion for turns the
    rules find ambiguous. See engine.py.
"""
from __future__ import annotations

import re

from persona_bot.evidence.traits import language_of, tokens
from persona_bot.models import Signal

STRONG, MED, WEAK = 0.8, 0.5, 0.3

LEXICON: dict[str, list[tuple[str, float]]] = {
    "rush": [
        ("jaldi", MED), ("जल्दी", MED), ("time nahi", STRONG), ("टाइम नहीं", STRONG), ("समय नहीं", STRONG),
        ("busy", MED), ("बिज़ी", MED), ("बिजी", MED), ("baad mein", MED), ("बाद में", MED),
        ("short mein", STRONG), ("शॉर्ट में", STRONG), ("seedha bolo", STRONG), ("सीधा बोलो", STRONG),
        ("सीधे बोलिए", STRONG), ("point pe aao", STRONG), ("पॉइंट पर", STRONG), ("जल्दी बोलो", STRONG),
        ("jaldi bolo", STRONG), ("meeting mein", MED), ("मीटिंग में हूँ", MED), ("driving", MED),
        ("quick", WEAK), ("quickly", MED), ("make it quick", STRONG), ("in a hurry", STRONG),
        ("no time", STRONG), ("get to the point", STRONG), ("haan haan", MED), ("हाँ हाँ", MED),
        ("aage bolo", MED), ("आगे बोलो", MED),
    ],
    "confusion": [
        ("samajh nahi", STRONG), ("समझ नहीं", STRONG), ("samjha nahi", STRONG), ("समझा नहीं", STRONG),
        ("kya matlab", STRONG), ("क्या मतलब", STRONG), ("matlab", MED), ("मतलब", MED),
        ("kya bola", MED), ("क्या बोला", MED), ("phir se", MED), ("फिर से बोलिए", STRONG), ("फिर से", MED),
        ("dobara", MED), ("दोबारा", MED), ("kya hota hai", STRONG), ("क्या होता है", STRONG),
        ("lead kya", STRONG), ("लीड क्या", STRONG), ("kaun bol", MED), ("कौन बोल", MED),
        ("what do you mean", STRONG), ("didn't understand", STRONG), ("don't understand", STRONG),
        ("not clear", STRONG), ("pardon", MED), ("come again", MED), ("what is a lead", STRONG),
    ],
    "frustration": [
        ("kitni baar", STRONG), ("कितनी बार", STRONG), ("pareshan", STRONG), ("परेशान", STRONG),
        ("band karo", STRONG), ("बंद करो", STRONG), ("mat karo", MED), ("मत करो", MED),
        ("roz roz", STRONG), ("रोज़ रोज़", STRONG), ("रोज रोज", STRONG), ("har din", MED), ("हर दिन", MED),
        ("bakwas", STRONG), ("बकवास", STRONG), ("faltu", STRONG), ("फालतू", STRONG), ("फ़ालतू", STRONG),
        ("time waste", STRONG), ("टाइम वेस्ट", STRONG), ("bola na", MED), ("बोला ना", MED), ("बोल दिया", MED),
        ("nahi chahiye", MED), ("नहीं चाहिए", MED), ("dimag", MED), ("दिमाग", MED),
        ("stop calling", STRONG), ("don't call", STRONG), ("irritating", STRONG), ("annoying", STRONG),
        ("fed up", STRONG), ("already told", STRONG), ("waste of time", STRONG), ("useless", MED),
        ("not interested", MED), ("again and again", STRONG), ("so many times", STRONG),
    ],
    "interest": [
        ("kitna", WEAK), ("कितना", WEAK), ("कितनी लीड", STRONG), ("kitne leads", STRONG), ("kaise", WEAK),
        ("कैसे", WEAK), ("kaise milenge", STRONG), ("कैसे मिलेंगे", STRONG), ("batao", WEAK), ("बताइए", WEAK),
        ("बताओ", WEAK), ("accha", WEAK), ("अच्छा", WEAK), ("theek hai", MED), ("ठीक है", MED),
        ("haan bolo", MED), ("हाँ बोलिए", MED), ("कल", WEAK), ("slot", MED), ("meeting kab", STRONG),
        ("मीटिंग कब", STRONG), ("interested", MED), ("sounds good", STRONG), ("tell me more", STRONG),
        ("how does it work", STRONG), ("how many leads", STRONG), ("what's the benefit", STRONG),
        ("okay go on", MED), ("benefit", MED), ("फायदा", MED), ("फ़ायदा", MED), ("fayda", MED),
    ],
}
# "not interested" must not count as interest
NEGATED_INTEREST = ["not interested", "नहीं चाहिए", "nahi chahiye", "interested nahi", "interest nahi"]

LANG_REQUEST = [
    (re.compile(r"(hindi|हिंदी|हिन्दी)\s*(mein|में|me)", re.I), "hi"),
    (re.compile(r"(speak|talk|bolo|baat).{0,15}(in )?english|english\s*(mein|में|me|please)", re.I), "en"),
]

ROMAN_HINDI = {"hai", "hain", "nahi", "nahin", "kya", "aap", "mujhe", "abhi", "baad", "mein", "bolo", "karo",
               "samajh", "theek", "haan", "ji", "kitni", "baar", "kaise", "kab", "bhai", "accha", "matlab",
               "kal", "aaj", "chahiye", "hoon", "ho", "raha", "rahi", "tha", "kar", "ke", "ka", "ki", "ko",
               "se", "par", "bhi", "toh", "to", "yeh", "woh", "kaun", "kyun", "bataiye", "batao", "jaldi"}
ACKS = {"haan", "ha", "ok", "okay", "hmm", "ji", "हाँ", "हां", "जी", "हम्म", "ओके", "yes", "accha", "अच्छा",
        # greetings are not "short = rushed"
        "namaste", "नमस्ते", "hello", "hi", "हेलो", "हैलो", "हलो", "bolo", "बोलो", "बोलिए", "who", "speaking"}


def spoken_language(text: str, stt_language: str | None = None) -> str:
    """hi | hinglish | en. Uses the script ratio, plus a romanised-Hindi word check for typed input."""
    label, _ = language_of(text)
    if label == "en":
        words = [w.lower() for w in tokens(text)]
        hits = sum(w in ROMAN_HINDI for w in words)
        if words and (hits >= 2 or hits / len(words) >= 0.3):
            return "hinglish"
        if stt_language and stt_language.startswith("hi") and hits:
            return "hinglish"
    return label


def same_family(a: str, b: str) -> bool:
    """Hindi and Hinglish are one family; switching between them is not worth a persona change."""
    fam = {"hi": "hindi", "hinglish": "hindi", "en": "english"}
    return fam[a] == fam[b]


def detect(text: str, *, bot_language: str, history: list[str] | None = None,
           stt_language: str | None = None, audio_seconds: float | None = None) -> list[Signal]:
    """
    text          seller's words this turn (from STT, or typed in the UI)
    bot_language  the bot's CURRENT language (after earlier switches)
    history       the seller's previous turns, oldest first
    Returns signals with confidence ≥ 0.3, strongest first.
    """
    history = history or []
    low = text.lower().strip()
    words = tokens(low)
    out: dict[str, Signal] = {}

    def add(name: str, conf: float, why: str, value: str | None = None):
        if name in out:
            out[name].confidence = min(0.95, out[name].confidence + conf)
            out[name].evidence += f"; {why}"
        else:
            out[name] = Signal(name=name, confidence=min(0.95, conf), evidence=why, value=value)

    # 1. Lexicons
    negated = any(n in low for n in NEGATED_INTEREST)
    for name, phrases in LEXICON.items():
        if name == "interest" and negated:
            continue
        for phrase, w in phrases:
            if phrase in low:
                add(name, w, f'said "{phrase}"')

    # 2. Features
    if 0 < len(words) <= 2 and low.rstrip("?").strip() in {"kya", "क्या", "what", "huh", "haan?", "हैं", "sorry"}:
        add("confusion", STRONG, "one-word 'what?'")
    elif 0 < len(words) <= 3 and not set(words) & ACKS and "?" not in low:
        add("rush", WEAK, f"very short reply ({len(words)} words)")
    if audio_seconds and audio_seconds > 0.5 and len(words) / audio_seconds > 3.5:
        add("rush", WEAK, f"speaking fast ({len(words) / audio_seconds:.1f} words/s)")
    refusals = sum(any(r in t.lower() for r in ("nahi", "नहीं", "no ", "not ")) for t in history[-2:] + [text])
    if refusals >= 3:
        add("frustration", MED, "refused 3 turns in a row")
    if "?" in text and any(w in low for w in ("kitn", "कितन", "kaise", "कैसे", "how", "kab", "कब", "when")) and not negated:
        add("interest", WEAK, "asked a question about how/how much/when")

    # 3. Language switch
    for rx, lang in LANG_REQUEST:
        if rx.search(text) and not same_family(lang, bot_language):
            add("language_switch", 0.95, f"asked to speak {lang}", value=lang)
            break
    else:
        lang = spoken_language(text, stt_language)
        if len(words) >= 3 and not same_family(lang, bot_language):
            conf = 0.85 if len(words) >= 6 else 0.6   # short turns are ambiguous; need a second turn
            add("language_switch", conf, f"seller spoke {lang} while bot speaks {bot_language}", value=lang)

    return sorted(out.values(), key=lambda s: -s.confidence)
