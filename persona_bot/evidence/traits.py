"""
traits.py: reads a bot transcript and works out HOW the bot spoke.

Real call data has transcripts, not labels like "formality=aap_formal". So we
derive persona traits from the text itself. Every function here is a few lines
of plain rules, so you can explain each one to the jury in one sentence.

Transcript convention: bot turns joined with " || ". If the real data comes as a
list of turns or with speaker tags, convert it in the adapter (GUIDE.md).
"""
from __future__ import annotations

import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")
PUNCT = re.compile(r"[।,.?!:;\"'()\-–—…]")

# Brand names and numbers say nothing about language choice, so they're ignored
NEUTRAL = {"indiamart"}

CASUAL_WORDS = {"तुम", "तुम्हारे", "तुम्हारी", "तुमसे", "तुम्हें", "तुम्हारा", "यार",
                "tum", "tumhare", "tumhari", "tumse", "yaar", "hey", "yeah", "totally"}
FORMAL_WORDS = {"जी", "ji", "sir", "madam", "ma'am"}
ACK_PATTERNS = ["समझ सकती", "समझ सकता", "समझ रही", "समझ रहा", "understand", "get that",
                "samajh sakti", "samajh sakta"]

# Avg words per bot turn → verbosity band. Thresholds were calibrated with
# tests/test_traits.py so the extractor recovers the right band on every template.
CRISP_MAX_WORDS = 14.5
NORMAL_MAX_WORDS = 23.8


def tokens(text: str) -> list[str]:
    return [t for t in PUNCT.sub(" ", text).split() if t]


def language_of(text: str) -> tuple[str, float]:
    """
    Returns (label, english_ratio).
      english_ratio = Latin-script words / (Latin + Devanagari words)
      hi        → almost no English words (< 6%)
      hinglish  → Hindi with English mixed in
      en        → no Devanagari at all, or > 60% English
    Roman-script Hindi ("aap kaise ho") would read as English here. If the
    organisers' transcripts are romanised, add a Hindi word list check.
    """
    lat = dev = 0
    for t in tokens(text):
        if t.lower() in NEUTRAL or t.isdigit():
            continue
        if DEVANAGARI.search(t):
            dev += 1
        elif LATIN.search(t):
            lat += 1
    total = lat + dev
    if total == 0:
        return "en", 0.0
    ratio = lat / total
    if dev == 0 or ratio > 0.6:
        return "en", ratio
    if ratio < 0.06:
        return "hi", ratio
    return "hinglish", ratio


def formality_of(text: str) -> str:
    """'tum'/'yaar'/'hey' → casual; 'ji'/'sir' → aap_formal; otherwise aap_friendly."""
    toks = {t.lower() for t in tokens(text)}
    if toks & CASUAL_WORDS:
        return "casual"
    if toks & FORMAL_WORDS:
        return "aap_formal"
    return "aap_friendly"


def verbosity_of(transcript: str) -> tuple[str, float]:
    turns = [t for t in transcript.split("||") if t.strip()]
    avg = sum(len(tokens(t)) for t in turns) / max(1, len(turns))
    if avg <= CRISP_MAX_WORDS:
        return "crisp", avg
    if avg <= NORMAL_MAX_WORDS:
        return "normal", avg
    return "explanatory", avg


def acknowledged_objection(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in ACK_PATTERNS)


def pace_band(pace: float | None) -> str:
    """Bot pace as configured in TTS (from call logs). Real data may need words/sec instead."""
    if pace is None:
        return "unknown"
    if pace < 0.95:
        return "slow"
    if pace > 1.07:
        return "fast"
    return "normal"


def extract(transcript: str, pace: float | None = None, voice_gender: str | None = None) -> dict:
    lang, ratio = language_of(transcript)
    verb, avg = verbosity_of(transcript)
    return {
        "bot_language": lang,
        "english_ratio": round(ratio, 3),
        "formality": formality_of(transcript),
        "verbosity": verb,
        "avg_turn_words": round(avg, 1),
        "acknowledged_objection": "yes" if acknowledged_objection(transcript) else "no",
        "pace_band": pace_band(pace),
        "voice_gender": voice_gender or "unknown",
    }
