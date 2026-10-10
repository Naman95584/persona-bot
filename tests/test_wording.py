"""Wording rules: positive demand framing (no deficit numbers) and one script per sentence in Hindi / Hinglish."""
import re

from persona_bot.config import SAMPLES_DIR
from persona_bot.live.engine import devanagari_guard, has_deficit_framing, hide_product_names, new_call
from persona_bot.live.prompt import system_prompt
from persona_bot.persona import templates as TPL
from persona_bot.persona.generator import generate, load_seller
from persona_bot.sarvam.client import MockClient


def test_deficit_framing_is_detected():
    for bad in ("पिछले महीने आपको सिर्फ 2 leads मिली थीं", "Sir, you got only 3 leads last month", "आपकी zero leads आई थीं",
                "आपका reply rate बहुत कम है", "पिछले महीने कोई भी leads नहीं आई", "आपके 31% reply हुए"):
        assert has_deficit_framing(bad), bad
    for good in ("आपके एरिया में बायर्स रोज़ सर्च कर रहे हैं", "Buyers in your area search every day",
                 "बस 15 मिनट की फ्री मीटिंग है", "No sir, this meeting is completely free."):
        assert not has_deficit_framing(good), good


def test_leaked_english_words_become_devanagari_but_the_brand_stays():
    out = devanagari_guard("IndiaMART के advisor के साथ 15 minute का free slot, sir", "hinglish")
    assert out == "IndiaMART के एडवाइजर के साथ 15 मिनट का फ्री स्लॉट, सर"
    assert devanagari_guard("Our advisor is free", "en") == "Our advisor is free"


def test_latin_product_names_are_hidden_in_hindi_replies():
    out = hide_product_names("आपके 'Circuit Board' के बायर्स रोज़ सर्च कर रहे हैं", ["Circuit Board"], "hinglish")
    assert "Circuit" not in out and "प्रोडक्ट्स" in out and "'" not in out
    assert hide_product_names("Circuit Board buyers", ["Circuit Board"], "en") == "Circuit Board buyers"


def _latin(line):
    line = re.sub(r"\{[a-z_]+\}", "", line)
    return [w for w in re.findall(r"[A-Za-z]+", line) if w != "IndiaMART"]


def test_hindi_and_hinglish_template_lines_use_one_script():
    lines = [v for (lang, _, _), v in TPL.OPENINGS.items() if lang in ("hi", "hinglish")]
    lines += [d[l] for d in list(TPL.PLAYBOOK.values()) + list(TPL.MOCK.values()) for l in ("hi", "hinglish")]
    assert not {w for ln in lines for w in _latin(ln)}


def test_hooks_never_use_deficit_framing_but_keep_the_data_in_the_reason():
    for f in SAMPLES_DIR.glob("seller_*.json"):
        p = generate(load_seller(f))
        for h in p.conversation_plan.personalisation:
            described = re.sub(r"Do not[^.]*\.", "", h.hook)            # the "Do not quote ..." instruction names what to avoid
            assert not has_deficit_framing(described), (f.name, h.hook)
            assert h.reason.why and h.reason.source


def test_hindi_prompt_does_not_expose_latin_names():
    seller = load_seller(SAMPLES_DIR / "seller_R001.json")           # Hinglish persona
    prompt = system_prompt(generate(seller), seller, [])
    assert seller.categories[0] not in prompt and seller.city not in prompt and seller.display_name not in prompt
    assert "Devanagari" in prompt and "negative or deficit framing" in prompt


def test_template_replies_in_mock_calls_are_clean():
    call = new_call("R001", client=MockClient())
    call.start()
    for line in ("हाँ बोलिए", "लीड क्या होता है? समझ नहीं आया", "पैसे लगेंगे क्या?"):
        text = call.turn(text=line)["bot_text"]
        assert not _latin(text), text
