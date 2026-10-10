"""
synth.py: generates SYNTHETIC data in the same shape as the real data.

Why synthetic?
  * The hackathon rule says no customer data leaves the premises, and I (Claude)
    don't have the real files anyway.
  * Synthetic data with KNOWN, planted effects lets us test that the evidence
    miner actually recovers the truth. If the miner can't find an effect we
    planted, it won't find real ones either.

Two outputs:
  1. data/samples/seller_*.json  – 6 seller profiles (3 are the demo sellers)
  2. data/past_calls.csv         – 6,000 historical calls with bot transcripts
                                   and outcomes, used by the evidence miner

When the organisers' real data arrives, write a tiny adapter that maps their
columns to these same fields (see GUIDE.md §"Swapping in real data").
"""
from __future__ import annotations

import csv
import json
import random

from persona_bot.config import DATA_DIR, SAMPLES_DIR

RNG = random.Random(42)  # fixed seed → same data every run → reproducible demo

BUSINESS_TYPES = ["manufacturer", "trader", "distributor", "retailer", "exporter", "service_provider"]
TURNOVER = ["0-40L", "40L-1.5Cr", "1.5-5Cr", "5-25Cr", "25Cr+"]
SMALL = {"0-40L", "40L-1.5Cr"}
LARGE = {"5-25Cr", "25Cr+"}
LANGS = ["hi", "hinglish", "en"]
OBJECTIONS = ["busy", "price", "not_needed", "already_using_other", "trust", "lead_quality", "none"]

# ─────────────────── Bot sentence pools (for synthetic transcripts) ──────────
# Each pool = (greeting, pitch sentences…, closing ask) for one language × formality.
# The evidence miner never sees these labels. It has to RE-DISCOVER language,
# formality and verbosity from the raw text, exactly as it would on real transcripts.
POOLS = {
    ("hi", "aap_formal"): dict(
        greet="नमस्ते जी, मैं IndiaMART से रिया बोल रही हूँ।",
        body=["आपके लिए नए खरीदार ढूँढने में हम मदद करना चाहते हैं जी।",
              "हमारे सलाहकार आपसे सिर्फ़ पंद्रह मिनट बात करेंगे जी।",
              "इससे आपको ज़्यादा और अच्छे ऑर्डर मिल सकते हैं।"],
        ask="क्या कल सुबह ग्यारह बजे आपके लिए ठीक रहेगा जी?",
        ack="जी, मैं आपकी बात पूरी तरह समझ सकती हूँ।"),
    ("hi", "aap_friendly"): dict(
        greet="नमस्ते, मैं IndiaMART से रिया बोल रही हूँ।",
        body=["आपके लिए नए खरीदार ढूँढने में हम मदद करना चाहते हैं।",
              "हमारे सलाहकार आपसे सिर्फ़ पंद्रह मिनट बात करेंगे।",
              "इससे आपको ज़्यादा और अच्छे ऑर्डर मिल सकते हैं।"],
        ask="क्या कल सुबह ग्यारह बजे आपके लिए ठीक रहेगा?",
        ack="मैं आपकी बात पूरी तरह समझ सकती हूँ।"),
    ("hi", "casual"): dict(
        greet="हेलो, मैं IndiaMART से रिया बोल रही हूँ।",
        body=["तुम्हारे लिए नए खरीदार ढूँढने में हम मदद करेंगे।",
              "हमारे सलाहकार तुमसे बस पंद्रह मिनट बात करेंगे।",
              "इससे तुम्हें ज़्यादा ऑर्डर मिल सकते हैं यार।"],
        ask="कल सुबह ग्यारह बजे चलेगा क्या?",
        ack="हाँ, मैं तुम्हारी बात समझ रही हूँ।"),
    ("hinglish", "aap_formal"): dict(
        greet="नमस्ते जी, मैं IndiaMART से रिया बोल रही हूँ।",
        body=["आपकी buyer leads बढ़ाने के लिए एक quick बात करनी थी जी।",
              "हमारे growth advisor आपसे सिर्फ़ 15 minute call करेंगे।",
              "इससे आपको better quality leads मिल सकती हैं।"],
        ask="क्या कल 11 बजे का slot आपके लिए ठीक रहेगा जी?",
        ack="जी, मैं आपका point पूरी तरह समझ सकती हूँ।"),
    ("hinglish", "aap_friendly"): dict(
        greet="नमस्ते, मैं IndiaMART से रिया बोल रही हूँ।",
        body=["आपकी buyer leads बढ़ाने के लिए एक quick बात करनी थी।",
              "हमारे growth advisor आपसे सिर्फ़ 15 minute call करेंगे।",
              "इससे आपको better quality leads मिल सकती हैं।"],
        ask="क्या कल 11 बजे का slot आपके लिए ठीक रहेगा?",
        ack="मैं आपका point पूरी तरह समझ सकती हूँ।"),
    ("hinglish", "casual"): dict(
        greet="हेलो, मैं IndiaMART से रिया बोल रही हूँ।",
        body=["तुम्हारी buyer leads बढ़ाने के लिए quick बात करनी थी।",
              "हमारे growth advisor तुमसे बस 15 minute call करेंगे।",
              "इससे तुम्हें better leads मिलेंगी यार।"],
        ask="कल 11 बजे का slot चलेगा?",
        ack="हाँ, तुम्हारा point समझ रही हूँ।"),
    ("en", "aap_formal"): dict(
        greet="Good morning sir, this is Riya calling from IndiaMART.",
        body=["We would like to help you get more genuine buyer enquiries, sir.",
              "Our growth advisor needs only fifteen minutes with you.",
              "This can bring you better quality leads every month."],
        ask="Would tomorrow at eleven work for you, sir?",
        ack="I completely understand your concern, sir."),
    ("en", "aap_friendly"): dict(
        greet="Hi, this is Riya calling from IndiaMART.",
        body=["We would like to help you get more genuine buyer enquiries.",
              "Our growth advisor needs only fifteen minutes with you.",
              "This can bring you better quality leads every month."],
        ask="Would tomorrow at eleven work for you?",
        ack="I completely understand your concern."),
    ("en", "casual"): dict(
        greet="Hey there, Riya here from IndiaMART.",
        body=["Wanted to help you get way more buyer enquiries.",
              "Our advisor just needs fifteen minutes, that's it.",
              "You'll get better leads out of it, totally."],
        ask="Does tomorrow at eleven work?",
        ack="Yeah, totally get that."),
}
SENTENCES_PER_TURN = {"crisp": 1, "normal": 2, "explanatory": 3}


def make_transcript(lang: str, formality: str, verbosity: str, acknowledged: bool) -> str:
    """Build 3 bot turns. Turns are separated by ' || ' (a convention our extractor reads)."""
    p = POOLS[(lang, formality)]
    k = SENTENCES_PER_TURN[verbosity]
    body = p["body"]
    t1 = [p["greet"]] + body[: k - 1]
    t2 = ([p["ack"]] if acknowledged else []) + [body[i % 3] for i in range(k)]
    t3 = [body[(i + 1) % 3] for i in range(k - 1)] + [p["ask"]]
    return " || ".join(" ".join(t) for t in (t1, t2, t3))


# ─────────────────── The planted "ground truth" ───────────────────────────────
def true_meeting_probability(s: dict, bot: dict) -> float:
    """
    Hidden rules that decide whether a synthetic call fixed a meeting.
    The evidence miner never sees this function. It must rediscover these effects
    from data. (These are PLAUSIBLE, not real IndiaMART findings.)
    """
    p = 0.18                                               # base rate
    # 1. Speaking the seller's language helps most
    if bot["lang"] == s["seller_language"]:
        p += 0.10
    elif {bot["lang"], s["seller_language"]} == {"hi", "hinglish"}:
        p += 0.05
    # 2. Busy sellers and traders want it crisp; small manufacturers want explanation
    if s["top_objection"] == "busy" or s["business_type"] == "trader":
        p += {"crisp": 0.08, "normal": 0.0, "explanatory": -0.06}[bot["verbosity"]]
    elif s["business_type"] == "manufacturer" and s["turnover_band"] in SMALL:
        p += {"crisp": -0.03, "normal": 0.0, "explanatory": 0.07}[bot["verbosity"]]
    # 3. Formality: small Hindi sellers expect "aap…ji"; big English sellers like friendly
    if s["turnover_band"] in SMALL and s["seller_language"] == "hi":
        p += {"aap_formal": 0.05, "aap_friendly": 0.0, "casual": -0.06}[bot["formality"]]
    elif s["turnover_band"] in LARGE and s["seller_language"] == "en":
        p += {"aap_formal": 0.0, "aap_friendly": 0.04, "casual": -0.02}[bot["formality"]]
    elif bot["formality"] == "casual":
        p -= 0.03
    # 4. Acknowledging price / trust / lead-quality objections helps
    if s["top_objection"] in {"price", "trust", "lead_quality"} and bot["ack"]:
        p += 0.08
    # 5. Pace: busy → faster; Hindi small manufacturers → slower
    if s["top_objection"] == "busy":
        p += {"slow": -0.03, "normal": 0.0, "fast": 0.05}[bot["pace_band"]]
    elif s["seller_language"] == "hi" and s["business_type"] == "manufacturer":
        p += {"slow": 0.05, "normal": 0.0, "fast": -0.03}[bot["pace_band"]]
    # 6. Voice gender: deliberately NO effect, so we can show the miner saying "no evidence"
    return max(0.02, min(0.9, p))


PACE_NUM = {"slow": 0.9, "normal": 1.0, "fast": 1.15}


def gen_past_calls(n_calls: int = 6000, n_sellers: int = 600) -> list[dict]:
    sellers = []
    for i in range(n_sellers):
        bt = RNG.choice(BUSINESS_TYPES)
        lang = RNG.choices(LANGS, weights=[4, 4, 2])[0]
        sellers.append(dict(
            seller_id=f"H{i:04d}", business_type=bt, turnover_band=RNG.choice(TURNOVER),
            seller_language=lang,
            top_objection=RNG.choices(OBJECTIONS, weights=[3, 2, 2, 1, 1, 1, 2])[0]))
    rows = []
    for c in range(n_calls):
        s = RNG.choice(sellers)
        # Historical bot behaviour was varied. That variation is what makes learning possible.
        bot = dict(
            lang=RNG.choice(LANGS), formality=RNG.choice(["aap_formal", "aap_friendly", "casual"]),
            verbosity=RNG.choice(["crisp", "normal", "explanatory"]), ack=RNG.random() < 0.5,
            pace_band=RNG.choice(["slow", "normal", "fast"]), gender=RNG.choice(["female", "male"]))
        won = RNG.random() < true_meeting_probability(s, bot)
        outcome = "meeting_fixed" if won else RNG.choices(
            ["callback", "not_interested", "disconnected"], weights=[4, 4, 2])[0]
        rows.append(dict(
            call_id=f"C{c:05d}", seller_id=s["seller_id"], business_type=s["business_type"],
            turnover_band=s["turnover_band"], seller_language=s["seller_language"],
            top_objection=s["top_objection"],
            bot_transcript=make_transcript(bot["lang"], bot["formality"], bot["verbosity"], bot["ack"]),
            bot_voice_gender=bot["gender"], bot_pace=PACE_NUM[bot["pace_band"]],
            outcome=outcome, duration_sec=RNG.randint(25, 60) if not won else RNG.randint(90, 240)))
    return rows


# ─────────────────── Demo sellers (hand-written for contrast) ─────────────────
def demo_sellers() -> list[dict]:
    """Three contrasting demo sellers + three extras, to show the generator generalises."""
    def calls(spec):  # spec = list of (outcome, dur, objections, lang, words, summary)
        return [dict(date=f"2026-0{9 - i // 3}-{10 + i * 3:02d}", outcome=o, duration_sec=d,
                     objections=obj, seller_language=lg, avg_seller_turn_words=w, summary=sm)
                for i, (o, d, obj, lg, w, sm) in enumerate(spec)]

    return [
        dict(seller_id="S001", display_name="Sharma Steel Traders", city="Ludhiana", state="Punjab",
             business_type="trader", turnover_band="1.5-5Cr", categories=["MS Pipes", "GI Sheets", "TMT Bars"],
             years_on_im=6, subscription="paid_basic", preferred_language="hinglish",
             engagement=dict(leads_last_30d=48, lead_response_rate=0.31, app_active_days_30d=22,
                             avg_reply_time_hrs=9.5, last_login_days_ago=0),
             past_calls=calls([
                 ("callback", 38, ["busy"], "hinglish", 4.0, "Said 'abhi busy hoon, baad mein'. Cut call fast."),
                 ("disconnected", 21, ["busy"], "hinglish", 3.5, "Hung up during long intro."),
                 ("meeting_fixed", 140, ["price"], "hinglish", 7.0, "Agreed after a crisp pitch focused on lead count."),
             ])),
        dict(seller_id="S002", display_name="Shree Ganesh Agro Industries", city="Sehore", state="Madhya Pradesh",
             business_type="manufacturer", turnover_band="0-40L", categories=["Flour Mill Machine", "Masala Grinder"],
             years_on_im=1, subscription="free", preferred_language="hi",
             engagement=dict(leads_last_30d=6, lead_response_rate=0.5, app_active_days_30d=3,
                             avg_reply_time_hrs=30.0, last_login_days_ago=9),
             past_calls=calls([
                 ("callback", 95, ["not_needed"], "hi", 12.0, "Asked many questions about what a 'lead' is. Wanted son present."),
                 ("not_interested", 70, ["trust"], "hi", 10.5, "Unsure if service is genuine; asked 'paise to nahi lagenge?'"),
             ])),
        dict(seller_id="S003", display_name="Nexa Pharma Distributors", city="Bengaluru", state="Karnataka",
             business_type="distributor", turnover_band="5-25Cr", categories=["Surgical Gloves", "Hospital Consumables"],
             years_on_im=4, subscription="paid_premium", preferred_language="en",
             engagement=dict(leads_last_30d=120, lead_response_rate=0.78, app_active_days_30d=27,
                             avg_reply_time_hrs=2.0, last_login_days_ago=0),
             past_calls=calls([
                 ("not_interested", 55, ["lead_quality"], "en", 14.0, "Complained leads are irrelevant retail buyers."),
                 ("disconnected", 40, ["lead_quality", "price"], "hinglish", 11.0, "Got irritated: 'kitni baar call karoge'. Switched to Hindi when annoyed."),
                 ("callback", 80, ["price"], "en", 13.0, "Wants ROI numbers before any meeting."),
             ])),
        dict(seller_id="S004", display_name="Rajputana Handicrafts", city="Jaipur", state="Rajasthan",
             business_type="retailer", turnover_band="40L-1.5Cr", categories=["Wooden Handicrafts", "Brass Idols"],
             years_on_im=3, subscription="free", preferred_language="hi",
             engagement=dict(leads_last_30d=15, lead_response_rate=0.6, app_active_days_30d=10,
                             avg_reply_time_hrs=12.0, last_login_days_ago=2),
             past_calls=calls([("callback", 75, ["price"], "hi", 9.0, "Interested but worried about cost.")])),
        dict(seller_id="S005", display_name="Surat Silk Exports", city="Surat", state="Gujarat",
             business_type="exporter", turnover_band="25Cr+", categories=["Silk Sarees", "Dress Material"],
             years_on_im=8, subscription="paid_premium", preferred_language="hinglish",
             engagement=dict(leads_last_30d=90, lead_response_rate=0.55, app_active_days_30d=20,
                             avg_reply_time_hrs=5.0, last_login_days_ago=1),
             past_calls=calls([("meeting_fixed", 160, ["already_using_other"], "hinglish", 9.0, "Uses another portal too; agreed to compare.")])),
        dict(seller_id="S006", display_name="CoolAir HVAC Services", city="Pune", state="Maharashtra",
             business_type="service_provider", turnover_band="1.5-5Cr", categories=["AC Installation", "HVAC AMC"],
             years_on_im=2, subscription="paid_basic", preferred_language="en",
             engagement=dict(leads_last_30d=30, lead_response_rate=0.4, app_active_days_30d=15,
                             avg_reply_time_hrs=6.0, last_login_days_ago=3),
             past_calls=calls([("no_answer", 0, ["none"], "en", 0.0, "Did not pick up."),
                               ("callback", 50, ["busy"], "en", 6.0, "On site; asked to call evening.")])),
    ]


def main() -> None:
    for s in demo_sellers():
        path = SAMPLES_DIR / f"seller_{s['seller_id']}.json"
        path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = gen_past_calls()
    with open(DATA_DIR / "past_calls.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(demo_sellers())} seller files → {SAMPLES_DIR}")
    print(f"wrote {len(rows)} past calls → {DATA_DIR / 'past_calls.csv'}  (SYNTHETIC)")


if __name__ == "__main__":
    main()
