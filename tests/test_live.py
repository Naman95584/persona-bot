"""Signal detector + policy: hysteresis, cooldown, idempotence, opposites, channels, scenarios, API."""
from pathlib import Path

import yaml

from persona_bot.config import ROOT, SAMPLES_DIR
from persona_bot.live.engine import new_call
from persona_bot.live.persona_policy import LiveState
from persona_bot.live.signal_detector import detect, spoken_language
from persona_bot.models import Signal
from persona_bot.persona.generator import generate, load_seller
from persona_bot.sarvam.client import MockClient


def names(text, lang="hinglish", history=None):
    return {s.name: s.confidence for s in detect(text, bot_language=lang, history=history)}


# ─── detector ───
def test_detector_basics():
    assert names("जल्दी बोलो, टाइम नहीं है")["rush"] >= 0.75
    assert names("लीड क्या होता है? समझ नहीं आया", "hi")["confusion"] >= 0.75
    assert names("kitni baar call karoge yaar")["frustration"] >= 0.75
    assert names("meeting kab hogi? sounds good")["interest"] >= 0.75
    assert "interest" not in names("not interested")              # negation guard
    assert "rush" not in names("नमस्ते")                          # greeting isn't rush
    assert names("क्या?", "hi")["confusion"] >= 0.75


def test_language_detection():
    assert spoken_language("Please share the details by email") == "en"
    assert spoken_language("मुझे अभी नहीं चाहिए") == "hi"
    assert spoken_language("haan bolo kya baat hai") == "hinglish"     # romanised Hindi
    assert "language_switch" not in names("मुझे अभी समय नहीं है", "hinglish")   # same family
    assert names("Hindi mein baat karo please", "en")["language_switch"] >= 0.9


# ─── policy ───
def state(sid="S001"):
    return LiveState("t", generate(load_seller(SAMPLES_DIR / f"seller_{sid}.json")))


def sig(name, conf, value=None):
    return Signal(name=name, confidence=conf, evidence="test", value=value)


def test_hysteresis_two_weak_turns_fire():
    st = state("S004")                   # S004 doesn't watch for confusion → no threshold discount
    assert st.step(0, [sig("confusion", 0.55)], 0) == []
    out = st.step(1, [sig("confusion", 0.55)], 1)
    assert out and out[0].signal == "confusion" and "2nd consecutive" in out[0].reason


def test_cooldown_blocks_then_allows():
    st = state()
    assert st.step(0, [sig("rush", 0.9)], 0)
    assert st.step(1, [sig("interest", 0.9)], 1) == []        # within cooldown
    assert st.step(2, [sig("interest", 0.9)], 2)              # cooldown over


def test_frustration_overrides_cooldown():
    st = state()
    st.step(0, [sig("rush", 0.9)], 0)
    out = st.step(1, [sig("frustration", 0.95)], 1)
    assert out and out[0].signal == "frustration"


def test_idempotent_and_opposites_cancel():
    st = state()
    pace0 = st.persona.voice.pace
    st.step(0, [sig("rush", 0.9)], 0)
    assert st.persona.voice.pace > pace0
    assert st.step(2, [sig("rush", 0.9)], 2) == []            # already active
    out = st.step(4, [sig("confusion", 0.9)], 4)
    assert "rush" not in st.active and out[0].change.get("cancelled") == ["rush", None]


def test_language_and_style_switch_on_same_turn():
    st = state("S003")
    out = st.step(0, [sig("language_switch", 0.85, "hi"), sig("frustration", 0.8)], 0)
    assert [e.signal for e in out] == ["language_switch", "frustration"]
    assert st.persona.language.primary_code == "hi-IN"


def test_pace_is_clamped():
    st = state()
    st.persona.voice.pace = 1.95
    st.step(0, [sig("rush", 0.9)], 0)
    assert st.persona.voice.pace <= 2.0


# ─── scenarios (the demo scripts) ───
def test_all_demo_scenarios_switch_as_expected():
    for f in sorted((ROOT / "tests" / "scenarios").glob("*.yaml")):
        sc = yaml.safe_load(f.read_text(encoding="utf-8"))
        call = new_call(sc["seller_id"], client=MockClient())
        call.start()
        for t in sc["turns"]:
            got = sorted(s["signal"] for s in call.turn(text=t["text"])["switches"])
            assert got == sorted(t.get("expect", [])), (f.name, t["text"], got)


# ─── API ───
def test_api_full_call():
    from fastapi.testclient import TestClient
    from persona_bot.web.app import app
    c = TestClient(app)
    assert len(c.get("/api/sellers").json()) >= 3
    r = c.post("/api/calls", json={"seller_id": "S001"}).json()
    assert r["bot_text"] and r["audio_b64"]
    t = c.post(f"/api/calls/{r['call_id']}/turn", data={"text": "जल्दी बोलो, time नहीं है"}).json()
    assert t["switches"][0]["signal"] == "rush"
    end = c.post(f"/api/calls/{r['call_id']}/end").json()
    assert Path(end["switch_log"]).read_text(encoding="utf-8").strip()
