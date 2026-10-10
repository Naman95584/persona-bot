"""Trait extractor must recover every template's labels; the miner must find planted effects."""
import json

from persona_bot.config import EVIDENCE_DIR
from persona_bot.data.synth import POOLS, make_transcript
from persona_bot.evidence import traits as T
from persona_bot.evidence.miner import wilson


def test_extractor_recovers_all_54_template_combinations():
    for (lang, form) in POOLS:
        for verb in ("crisp", "normal", "explanatory"):
            for ack in (True, False):
                x = T.extract(make_transcript(lang, form, verb, ack))
                assert x["bot_language"] == lang, (lang, form, verb, ack, x)
                assert x["formality"] == form
                assert x["verbosity"] == verb
                assert (x["acknowledged_objection"] == "yes") == ack


def test_wilson_interval_is_sane():
    lo, hi = wilson(0, 10)
    assert lo == 0 and 0 < hi < 0.35          # never negative, unlike the normal approximation
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi


def test_miner_finds_planted_effects_and_rejects_gender():
    ev = json.loads((EVIDENCE_DIR / "persona_effects.json").read_text(encoding="utf-8"))
    strong = {(f["segment"], f["trait"]): f["best"] for f in ev["findings"] if f["strength"] == "strong"}
    # Planted: traders do better with crisp bots
    assert strong.get(("business_type=trader", "verbosity")) == "crisp"
    # Planted: speaking the seller's language helps
    assert strong.get(("seller_language=hinglish", "bot_language")) == "hinglish"
    # Planted: NO gender effect → no broad (single-attribute) gender finding should be strong overall
    broad_gender = [k for k in strong if k[1] == "voice_gender" and "&" not in k[0]]
    assert len(broad_gender) <= 1   # FDR 10%: allow at most one fluke
