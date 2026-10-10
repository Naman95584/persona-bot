"""
models.py: the data contracts of the whole system, written as Pydantic models.

Pydantic gives us three things for free:
  1. Validation – a malformed seller file fails loudly at load time, not mid-demo.
  2. Type hints – Claude Code and your editor autocomplete every field.
  3. JSON in/out – `.model_dump_json()` writes exactly the files the jury sees.

The persona models mirror schemas/persona_spec.schema.json and
schemas/switch_log.schema.json (the JSON Schemas are for humans/jury; these
classes are what the code actually uses).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ───────────────────────────── Seller input ──────────────────────────────────
# The deck says seller data = profile, business type, turnover, categories,
# engagement, past call outcomes and objections. Each of those is a field here.

BusinessType = Literal["manufacturer", "trader", "distributor", "retailer", "exporter", "service_provider"]
TurnoverBand = Literal["0-40L", "40L-1.5Cr", "1.5-5Cr", "5-25Cr", "25Cr+"]
Lang = Literal["hi", "hinglish", "en"]
# "general" = the seller talked but committed to nothing. It is neutral, not a bad ending.
Outcome = Literal["meeting_fixed", "callback", "not_interested", "no_answer", "disconnected", "general"]
Objection = Literal["busy", "price", "not_needed", "already_using_other", "trust", "lead_quality", "none"]


class Engagement(BaseModel):
    leads_last_30d: int = 0              # buyer enquiries received in the last 30 days
    lead_response_rate: float = 0.0      # share of those leads the seller replied to (0–1)
    app_active_days_30d: int = 0         # how many of the last 30 days they opened the app
    avg_reply_time_hrs: float = 0.0      # how fast they reply to buyers
    last_login_days_ago: int = 0


class PastCall(BaseModel):
    date: str
    outcome: Outcome
    duration_sec: int
    objections: list[Objection] = []
    seller_language: Lang                 # language the seller actually spoke on that call
    avg_seller_turn_words: float          # short turns = impatient / busy
    summary: str = ""


class History(BaseModel):
    """Seller-level flags from past bot calls. Optional: synthetic sellers leave it empty."""
    showed_frustration: bool = False
    asked_if_bot: bool = False
    past_objection_categories: list[str] = []   # raw categories, e.g. "Not Ready / Needs Time / Early-Stage Seller"
    years_on_im_is_proxy: bool = False          # True when years_on_im was derived from the GST year (weak signal)


class Seller(BaseModel):
    seller_id: str                        # anonymised ID only, never a real GLID in samples
    display_name: str                     # synthetic business name for the demo
    city: str
    state: str
    business_type: BusinessType
    turnover_band: TurnoverBand
    categories: list[str]
    years_on_im: int
    subscription: Literal["free", "paid_basic", "paid_premium"]
    preferred_language: Lang
    engagement: Engagement
    past_calls: list[PastCall] = []
    history: History = History()


# ───────────────────────────── Persona spec ──────────────────────────────────
class Reason(BaseModel):
    """Every persona choice carries one of these. It's what makes the spec defensible."""
    why: str                              # human-readable explanation
    source: str                           # seller field or evidence key it came from


class Voice(BaseModel):
    tts_model: str
    speaker: str
    gender: Literal["female", "male"]
    accent: str
    pace: float = Field(ge=0.5, le=2.0)
    pitch: Optional[float] = None         # only meaningful on bulbul:v2
    temperature: Optional[float] = None   # v3 / v4-flash: expressiveness
    reason: Reason


class Language(BaseModel):
    label: Lang                           # hi | hinglish | en
    primary_code: str                     # BCP-47 for Sarvam, e.g. hi-IN
    hinglish_ratio: float = Field(ge=0, le=1)   # share of English words when speaking Hindi
    formality: Literal["aap_formal", "aap_friendly", "casual"]
    reason: Reason


class Tone(BaseModel):
    warmth: int = Field(ge=1, le=5)
    empathy: int = Field(ge=1, le=5)
    verbosity: Literal["crisp", "normal", "explanatory"]
    reason: Reason


class Opening(BaseModel):
    line: str
    reason: Reason


class Hook(BaseModel):
    hook: str
    reason: Reason


class Play(BaseModel):
    objection: str
    response: str
    reason: Reason


class ConversationPlan(BaseModel):
    opening: Opening
    personalisation: list[Hook]
    objection_playbook: list[Play]
    escalation_rules: list[str]
    guardrails: list[str]


class LiveAdaptation(BaseModel):
    watch_for: list[str]
    fallback_language: str
    max_switches_per_call: int = 4
    reason: Reason


class PersonaSpec(BaseModel):
    seller_id: str
    segment: str
    voice: Voice
    language: Language
    tone: Tone
    conversation_plan: ConversationPlan
    live_adaptation: LiveAdaptation
    evidence_used: list[str] = []         # evidence keys that influenced this persona


# ───────────────────────────── Live call ─────────────────────────────────────
SignalName = Literal["frustration", "confusion", "interest", "language_switch", "rush"]


class Signal(BaseModel):
    name: SignalName
    confidence: float
    evidence: str                         # what triggered it (quoted words / features)
    value: Optional[str] = None           # e.g. the new language for language_switch


class SwitchLogEntry(BaseModel):
    """One line of outputs/switch_logs/<call_id>.jsonl, which the deck explicitly asks for."""
    call_id: str
    turn: int
    ts_ms: int
    signal: SignalName
    confidence: float
    evidence: str
    change: dict[str, list]               # {"voice.pace": [1.0, 1.15], ...}  before → after
    reason: str
    latency_ms: Optional[int] = None
