"""Persona specs: valid, every choice has a reason, demo sellers are distinct (a scored metric)."""
import json

from persona_bot.config import ROOT, SAMPLES_DIR
from persona_bot.persona.generator import generate, load_seller


def _spec(sid):
    return generate(load_seller(SAMPLES_DIR / f"seller_{sid}.json"))


def test_every_choice_has_a_reason():
    for f in SAMPLES_DIR.glob("seller_*.json"):
        p = generate(load_seller(f))
        for part in (p.voice, p.language, p.tone, p.live_adaptation, p.conversation_plan.opening):
            assert part.reason.why and part.reason.source
        for x in p.conversation_plan.personalisation + p.conversation_plan.objection_playbook:
            assert x.reason.why and x.reason.source


def test_deterministic():
    assert _spec("S001").model_dump() == _spec("S001").model_dump()


def test_demo_sellers_are_distinct():
    a, b, c = _spec("S001"), _spec("S002"), _spec("S003")
    assert (a.tone.verbosity, b.tone.verbosity) == ("crisp", "explanatory")
    assert a.voice.pace > b.voice.pace                     # rushed trader faster than confused manufacturer
    assert {a.language.label, b.language.label, c.language.label} == {"hinglish", "hi", "en"}
    assert c.tone.empathy >= 4                             # history of irritation
    assert "language_switch" in c.live_adaptation.watch_for


def test_never_starts_casual():
    for f in SAMPLES_DIR.glob("seller_*.json"):
        assert generate(load_seller(f)).language.formality != "casual"


def test_spec_has_json_schema_required_fields():
    schema = json.loads((ROOT / "schemas" / "persona_spec.schema.json").read_text())
    d = _spec("S003").model_dump()
    for k in schema["required"]:
        assert k in d
    for k in schema["properties"]["voice"]["required"]:
        assert k in d["voice"]
