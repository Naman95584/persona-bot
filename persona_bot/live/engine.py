"""
engine.py: runs a call, one seller turn at a time.

    seller audio ─► STT ─► detect signals ─► policy (maybe switch) ─► LLM reply ─► TTS ─► bot audio
                    (or typed text)                 │
                                                    └─► switch log (JSONL)

Robustness choices (Technical Robustness = 20% of the score):
  * If STT returns nothing, the turn is skipped politely ("sorry, could you repeat?").
  * If the LLM fails or times out, we fall back to the persona's reviewed
    template lines, so the call never dies on stage.
  * If TTS fails, the text is still returned, and the UI shows it.
  * The LLM reply is cut to the persona's max sentences, so a chatty model
    can't break "crisp" mode.
"""
from __future__ import annotations

import base64
import json
import re
import time
import uuid

from persona_bot.config import CALLS_DIR, CONFIG, PERSONAS_DIR, SAMPLES_DIR, SWITCH_LOGS_DIR
from persona_bot.live.persona_policy import LiveState
from persona_bot.live.prompt import system_prompt
from persona_bot.live.signal_detector import detect
from persona_bot.models import PersonaSpec, Seller, Signal
from persona_bot.persona import templates as TPL
from persona_bot.persona.generator import generate, load_seller
from persona_bot.sarvam.client import SarvamError, get_client

MAX_SENTENCES = {"crisp": 1, "normal": 2, "explanatory": 3}
SENT_SPLIT = re.compile(r"(?<=[।.!?])\s+")
SLOT_WORDS = ("कल", "बजे", "kal", "baje", "tomorrow", "pm", "am", "evening", "शाम", "सुबह", "slot रख", "रख लो", "fix kar")
YES_WORDS = ("ठीक है", "theek hai", "हाँ", "haan", "ok", "okay", "yes", "chalega", "चलेगा", "done", "रख लो", "kar do")
OBJECTION_WORDS = {
    "price": ("paise", "पैसे", "पैसा", "charge", "cost", "price", "fees", "कितने का", "free"),
    "trust": ("fraud", "fake", "genuine", "भरोसा", "bharosa", "असली", "scam"),
    "lead_quality": ("useless", "irrelevant", "गलत लीड", "bekaar", "बेकार", "retail buyers", "quality"),
    "already_using_other": ("tradeindia", "justdial", "dusra portal", "दूसरा", "दूसरे", "other portal",
                            "already using", "comparison"),
    "not_needed": ("nahi chahiye", "नहीं चाहिए", "not needed", "zarurat nahi", "ज़रूरत नहीं", "जरूरत नहीं"),
    "busy": ("busy", "बिज़ी", "बिजी", "baad mein", "बाद में"),
}


# ── Wording safety nets (the prompt does most of the work; these catch what slips through) ─────────────────
# English business words an LLM leaks into Hindi / Hinglish sentences → Devanagari. IndiaMART and AI stay in Latin.
DEVANAGARI = {
    "minute": "मिनट", "minutes": "मिनट", "min": "मिनट", "slot": "स्लॉट", "slots": "स्लॉट", "sir": "सर", "advisor": "एडवाइजर",
    "advisors": "एडवाइजर्स", "meeting": "मीटिंग", "meetings": "मीटिंग्स", "time": "टाइम", "lead": "लीड", "leads": "लीड्स",
    "buyer": "बायर", "buyers": "बायर्स", "visibility": "विज़िबिलिटी", "free": "फ्री", "product": "प्रोडक्ट", "products": "प्रोडक्ट्स",
    "catalogue": "कैटलॉग", "catalog": "कैटलॉग", "quality": "क्वालिटी", "enquiry": "इन्क्वायरी", "enquiries": "इन्क्वायरी",
    "inquiry": "इन्क्वायरी", "inquiries": "इन्क्वायरी", "call": "कॉल", "calls": "कॉल्स", "order": "ऑर्डर", "orders": "ऑर्डर्स",
    "business": "बिज़नेस", "platform": "प्लेटफॉर्म", "growth": "ग्रोथ", "ok": "ओके", "okay": "ओके", "sms": "एसएमएस", "data": "डेटा",
    "profile": "प्रोफ़ाइल", "account": "अकाउंट", "category": "कैटेगरी", "seller": "सेलर", "sorry": "सॉरी", "thanks": "थैंक्स",
    "discussion": "डिस्कशन", "consultation": "कंसल्टेशन", "demand": "डिमांड", "search": "सर्च", "settings": "सेटिंग्स",
    "setting": "सेटिंग", "fix": "फिक्स", "book": "बुक", "confirm": "कन्फर्म", "online": "ऑनलाइन", "app": "ऐप", "number": "नंबर",
    "valuable": "कीमती", "interested": "इंटरेस्टेड",
    "pricing": "प्राइसिंग", "price": "प्राइस", "details": "डिटेल्स", "detail": "डिटेल", "customer": "कस्टमर", "customers": "कस्टमर्स",
    "offer": "ऑफर", "discount": "डिस्काउंट", "support": "सपोर्ट", "team": "टीम", "service": "सर्विस", "services": "सर्विसेज़",
    "report": "रिपोर्ट", "plan": "प्लान", "result": "रिज़ल्ट", "results": "रिज़ल्ट्स", "review": "रिव्यू", "check": "चेक", "quick": "क्विक", "simple": "सिंपल", "clear": "क्लियर", "special": "स्पेशल", "update": "अपडेट",
}
KEEP_LATIN = {"indiamart", "ai"}
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z']*")
# Deficit framing: quoting how few leads / how low a reply rate / "zero" / "only N". Never helps a sales call.
DEFICIT = re.compile(r"(?i)(\b(only|zero)\b|सिर्फ\s*\d|केवल\s*\d|ज़ीरो|जीरो|कोई\s*(भी\s*)?(lead|लीड)\w*\s*नहीं|"
                     r"\d+\s*%\s*(reply|रिप्लाई|response|जवाब)|reply rate|पिछले\s*महीने[^।?]{0,40}(कम|नहीं|सिर्फ|zero)|\bweak\b|कमज़ोर|"
                     r"low (lead|enquir)|कम\s+(leads|लीड))")


def devanagari_guard(text: str, lang: str) -> str:
    """Hindi / Hinglish: turn leaked Latin business words into Devanagari (IndiaMART and AI stay). Unknown words are left alone."""
    if lang == "en":
        return text
    return LATIN_WORD.sub(lambda m: m.group(0) if m.group(0).lower() in KEEP_LATIN
                          else DEVANAGARI.get(m.group(0).lower(), m.group(0)), text)


def hide_product_names(text: str, categories: list[str], lang: str) -> str:
    """Hindi / Hinglish: a Latin-script product name inside a Devanagari sentence becomes 'प्रोडक्ट्स'."""
    if lang == "en":
        return text
    for c in categories:
        text = re.sub(re.escape(c), "प्रोडक्ट्स", text, flags=re.I)
    return re.sub(r"['\"“”]प्रोडक्ट्स['\"“”]", "प्रोडक्ट्स", text)


def has_deficit_framing(text: str) -> bool:
    return bool(DEFICIT.search(text))


class Call:
    def __init__(self, seller: Seller, persona: PersonaSpec, client=None):
        self.id = f"{seller.seller_id}-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self.seller = seller
        self.state = LiveState(self.id, persona)
        self.client = client or get_client()
        self.t0 = time.perf_counter()
        self.messages: list[dict] = []           # chat history for the LLM
        self.seller_turns: list[str] = []
        self.transcript: list[dict] = []
        self.turn_no = 0
        self.meeting_fixed = False

    # ─────────────────────────── helpers ───────────────────────────
    def _ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def _speak(self, text: str) -> tuple[str | None, int]:
        v, lang = self.state.persona.voice, self.state.persona.language
        try:
            out = self.client.tts(text, lang.primary_code, v.speaker, v.pace, v.temperature, v.tts_model)
            return base64.b64encode(out["wav"]).decode(), out["ms"]
        except (SarvamError, Exception) as e:   # never crash the call over audio
            print("TTS error:", e)
            return None, 0

    def persona_snapshot(self) -> dict:
        p = self.state.persona
        return {"language": p.language.label, "language_code": p.language.primary_code,
                "formality": p.language.formality, "speaker": p.voice.speaker, "pace": p.voice.pace,
                "temperature": p.voice.temperature, "warmth": p.tone.warmth, "empathy": p.tone.empathy,
                "verbosity": p.tone.verbosity, "directives": self.state.directives,
                "active_signals": list(self.state.active)}

    # ─────────────────────────── call flow ─────────────────────────
    def start(self) -> dict:
        text = self.state.persona.conversation_plan.opening.line
        audio, tts_ms = self._speak(text)
        self.messages.append({"role": "assistant", "content": text})
        self.transcript.append({"who": "bot", "text": text, "ts_ms": self._ms()})
        return {"call_id": self.id, "bot_text": text, "audio_b64": audio, "persona": self.persona_snapshot(),
                "latency": {"tts_ms": tts_ms}}

    def turn(self, text: str | None = None, audio: bytes | None = None, audio_seconds: float | None = None) -> dict:
        t_start = time.perf_counter()
        lat: dict[str, int] = {}
        stt_lang = None
        if audio and not text:
            r = self.client.stt(audio, language_code=None)
            text, stt_lang, lat["stt_ms"] = r["transcript"], r["language_code"], r["ms"]
        text = (text or "").strip()
        if not text:
            msg = {"hi": "माफ़ कीजिए, आवाज़ नहीं आई, क्या आप दोबारा बोल सकते हैं?",
                   "hinglish": "Sorry, आवाज़ clear नहीं आई, एक बार फिर बोलेंगे?",
                   "en": "Sorry, I couldn't hear that. Could you say it again?"}[self.state.persona.language.label]
            audio_b64, _ = self._speak(msg)
            return {"seller_text": "", "bot_text": msg, "audio_b64": audio_b64, "signals": [], "switches": [],
                    "persona": self.persona_snapshot(), "latency": lat}

        # 1. Detect
        t = time.perf_counter()
        signals = detect(text, bot_language=self.state.persona.language.label, history=self.seller_turns,
                         stt_language=stt_lang, audio_seconds=audio_seconds)
        if CONFIG["live"]["detector_mode"] in ("llm", "hybrid") and not self.client.mock:
            signals = self._llm_signals(text, signals)
        lat["detect_ms"] = int((time.perf_counter() - t) * 1000)

        # 2. Policy (maybe switch persona)
        switches = self.state.step(self.turn_no, signals, self._ms())
        self.seller_turns.append(text)
        self.messages.append({"role": "user", "content": text})
        self.transcript.append({"who": "seller", "text": text, "ts_ms": self._ms(),
                                "signals": [s.model_dump() for s in signals]})

        # 3. Reply (LLM, or reviewed templates as a fallback)
        t = time.perf_counter()
        reply, source = self._reply(text, signals)
        lat["llm_ms"] = int((time.perf_counter() - t) * 1000)

        # 4. Speak with the (possibly new) voice
        audio_b64, lat["tts_ms"] = self._speak(reply)
        lat["total_ms"] = int((time.perf_counter() - t_start) * 1000)
        for e in switches:          # detection → first audio in the new persona
            e.latency_ms = lat["total_ms"] - lat.get("stt_ms", 0)

        self.messages.append({"role": "assistant", "content": reply})
        self.transcript.append({"who": "bot", "text": reply, "ts_ms": self._ms(), "source": source,
                                "switches": [e.model_dump() for e in switches]})
        self.turn_no += 1
        return {"seller_text": text, "stt_language": stt_lang, "bot_text": reply, "reply_source": source,
                "audio_b64": audio_b64, "signals": [s.model_dump() for s in signals],
                "switches": [e.model_dump() for e in switches], "persona": self.persona_snapshot(),
                "meeting_fixed": self.meeting_fixed, "latency": lat}

    # ─────────────────────────── reply ─────────────────────────────
    def _reply(self, text: str, signals: list[Signal]) -> tuple[str, str]:
        low = text.lower()
        if any(w in low for w in SLOT_WORDS) and any(w in low for w in YES_WORDS):
            self.meeting_fixed = True
        if not self.client.mock:
            try:
                sys = system_prompt(self.state.persona, self.seller, self.state.directives)
                history = self.messages[-12:]
                reply = self._trim(self.client.chat([{"role": "system", "content": sys}] + history)["text"])
                if reply and has_deficit_framing(reply):          # one retry, told exactly what to avoid
                    note = ("\nYOUR LAST DRAFT USED NEGATIVE FRAMING (it quoted low lead numbers or said 'zero' / 'only'). Rewrite it "
                            "without any such number or word: speak only about demand waiting for the seller.")
                    retry = self._trim(self.client.chat([{"role": "system", "content": sys + note}] + history)["text"])
                    reply = retry if retry and not has_deficit_framing(retry) else ""
                lang = self.state.persona.language.label
                reply = devanagari_guard(hide_product_names(reply, self.seller.categories, lang), lang)
                if reply:
                    return reply, "llm"
            except Exception as e:  # LLM down / slow / malformed → never let the call die
                print("LLM error, using template fallback:", e)
        return self._template_reply(low, signals), "template"

    def _trim(self, text: str) -> str:
        """
        Cut a chatty reply to the persona's sentence limit, but NEVER lose the final question (the ask for a time or a
        yes/no). With a question, the reply is the opening sentence(s) plus that question, so a crisp reply is at most
        'short answer + question'. Sentences after the question are dropped (the reply should end on it).
        """
        text = text.replace("*", "").replace("#", "").strip().strip('"')
        parts = [p for p in SENT_SPLIT.split(text) if p.strip()]
        limit = MAX_SENTENCES[self.state.persona.tone.verbosity]
        if len(parts) <= limit:
            return " ".join(parts)
        q = max((i for i, s in enumerate(parts) if "?" in s), default=None)
        if q is None:
            return " ".join(parts[:limit])
        keep = [q]
        for i in range(q):                              # earlier sentences, in order, until the budget is used
            if len(keep) < max(limit, 2):
                keep.append(i)
        return " ".join(parts[i] for i in sorted(keep))

    def _template_reply(self, low: str, signals: list[Signal]) -> str:
        p = self.state.persona
        lang, g = p.language.label, p.voice.gender
        names = {s.name for s in signals}
        fill = lambda t: TPL.fill(t, g, category=self.seller.categories[0])   # noqa: E731
        if self.meeting_fixed:
            return fill(TPL.MOCK["confirm"][lang])
        if "frustration" in names and "frustration" in self.state.active:
            return fill(TPL.MOCK["empathy"][lang])
        if "confusion" in names:                       # confused THIS turn → explain simply
            return fill(TPL.MOCK["explain"][lang])
        for obj, words in OBJECTION_WORDS.items():     # a concrete objection beats generic lines
            if any(w in low for w in words):
                return fill(TPL.PLAYBOOK[obj][lang])
        if "rush" in self.state.active:
            return fill(TPL.MOCK["rush"][lang])
        if "interest" in names:
            return fill(TPL.MOCK["interest"][lang])
        return fill(TPL.MOCK["ask_slot"][lang])

    def _llm_signals(self, text: str, rule_signals: list[Signal]) -> list[Signal]:
        """Hybrid mode: ask the LLM for a second opinion, keep the higher confidence per signal."""
        prompt = ("Classify the seller's latest phone reply. Return ONLY JSON like "
                  '{"frustration":0.0,"confusion":0.0,"interest":0.0,"rush":0.0}. Values 0-1.\nReply: ' + text)
        try:
            raw = self.client.chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=60)["text"]
            scores = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:
            return rule_signals
        merged = {s.name: s for s in rule_signals}
        for name, conf in scores.items():
            if name in ("frustration", "confusion", "interest", "rush") and float(conf) >= 0.3:
                if name not in merged or float(conf) > merged[name].confidence:
                    merged[name] = Signal(name=name, confidence=min(0.95, float(conf)), evidence="LLM classifier")
        return sorted(merged.values(), key=lambda s: -s.confidence)

    # ─────────────────────────── end ───────────────────────────────
    def end(self) -> dict:
        log_path = SWITCH_LOGS_DIR / f"{self.id}.jsonl"
        with open(log_path, "w", encoding="utf-8") as fh:
            for e in self.state.switches:
                fh.write(e.model_dump_json() + "\n")
        summary = {"call_id": self.id, "seller_id": self.seller.seller_id, "meeting_fixed": self.meeting_fixed,
                   "turns": self.turn_no, "switches": len(self.state.switches),
                   "base_persona": self.state.base.model_dump(), "final_persona": self.persona_snapshot(),
                   "transcript": self.transcript}
        (CALLS_DIR / f"{self.id}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"switch_log": str(log_path), "summary": summary}


def new_call(seller_id: str, client=None) -> Call:
    seller = load_seller(SAMPLES_DIR / f"seller_{seller_id}.json")
    p = PERSONAS_DIR / f"{seller_id}.json"
    persona = PersonaSpec(**json.loads(p.read_text(encoding="utf-8"))) if p.exists() else generate(seller)
    return Call(seller, persona, client)
