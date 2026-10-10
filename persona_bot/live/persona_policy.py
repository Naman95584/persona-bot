"""
persona_policy.py: decides WHETHER to switch the persona and HOW, then logs it.

The detector says "the seller sounds rushed (0.8)". The policy decides what to do:

  1. Threshold + hysteresis: switch if confidence ≥ fire_confidence (0.75), OR
     the same signal was ≥ watch_confidence (0.5) on this AND the previous turn.
     One ambiguous "haan" shouldn't flip the persona, but two in a row should.
     Signals this seller is expected to show (persona.live_adaptation.watch_for)
     get a small 0.05 discount on the threshold.
  2. Cooldown: at least `cooldown_turns` seller turns between switches, so the
     bot can't flip-flop. Exception: frustration and an explicit language
     request at ≥ 0.9 may override the cooldown (an angry seller can't wait).
  3. Priority: if two signals fire on the same turn, frustration beats
     language_switch beats confusion beats rush beats interest.
  4. Idempotence: a signal that's already active is not re-applied (no
     "pace +0.15" twice for the same rush).
  5. Opposites cancel: confusion removes an active rush (and vice versa), and
     frustration removes interest.
  6. Max switches per call.
  7. Two independent channels: LANGUAGE (language_switch) and STYLE (everything
     else). An angry seller who switches to Hindi needs BOTH changes on the same
     turn, so each channel has its own cooldown and step() can return two entries.

Every applied switch becomes one SwitchLogEntry, with the before → after value
of every changed field. That's the deck's "signal detected, change made, reason".
"""
from __future__ import annotations

import copy

from persona_bot.config import CONFIG
from persona_bot.models import PersonaSpec, Signal, SwitchLogEntry

OPPOSITE = {"rush": "confusion", "confusion": "rush", "frustration": "interest"}
CLAMP = {"voice.pace": (0.5, 2.0), "voice.temperature": (0.01, 1.0), "tone.empathy": (1, 5), "tone.warmth": (1, 5)}
COOLDOWN_OVERRIDE = {"frustration", "language_switch"}


def _get(p: PersonaSpec, path: str):
    obj, attr = path.split(".")
    return getattr(getattr(p, obj), attr)


def _set(p: PersonaSpec, path: str, value):
    obj, attr = path.split(".")
    setattr(getattr(p, obj), attr, value)


class LiveState:
    """The persona as it evolves during ONE call."""

    def __init__(self, call_id: str, base: PersonaSpec):
        self.call_id = call_id
        self.base = base
        self.persona = copy.deepcopy(base)       # mutated live; base stays untouched
        self.active: dict[str, str] = {}         # signal → directive currently in force
        self.turn_signals: list[dict[str, float]] = []
        self.last_switch_turn = {"style": -99, "language": -99}
        self.switches: list[SwitchLogEntry] = []
        L = CONFIG["live"]
        self.fire, self.watch, self.cooldown = L["fire_confidence"], L["watch_confidence"], L["cooldown_turns"]
        self.max_sw = base.live_adaptation.max_switches_per_call
        self.priority = L["priority"]
        self.deltas = L["deltas"]

    @property
    def directives(self) -> list[str]:
        return list(self.active.values())

    # ───────────────────────── decision ─────────────────────────
    def step(self, turn: int, signals: list[Signal], ts_ms: int) -> list[SwitchLogEntry]:
        """Returns 0, 1 or 2 switch entries (one per channel) for this seller turn."""
        now = {s.name: s.confidence for s in signals}
        prev = self.turn_signals[-1] if self.turn_signals else {}
        self.turn_signals.append(now)
        by_name = {s.name: s for s in signals}
        fired: list[SwitchLogEntry] = []
        for channel, names in (("language", ["language_switch"]),
                               ("style", [n for n in self.priority if n != "language_switch"])):
            for name in names:                           # highest priority first
                if len(self.switches) >= self.max_sw:
                    return fired
                s = by_name.get(name)
                if not s:
                    continue
                thr = self.fire - (0.05 if name in self.persona.live_adaptation.watch_for else 0)
                fires = s.confidence >= thr or (s.confidence >= self.watch and prev.get(name, 0) >= self.watch)
                if not fires:
                    continue
                if name in self.active and name != "language_switch":
                    continue                              # already applied
                if name == "language_switch" and s.value == self.persona.language.label:
                    continue
                in_cooldown = turn - self.last_switch_turn[channel] < self.cooldown
                if in_cooldown and not (name in COOLDOWN_OVERRIDE and s.confidence >= 0.9):
                    continue
                hyst = "" if s.confidence >= thr else f" (2nd consecutive turn ≥{self.watch})"
                fired.append(self._apply(turn, s, ts_ms, hyst, channel))
                break                                     # max one switch per channel per turn
        return fired

    # ───────────────────────── apply ────────────────────────────
    def _apply(self, turn: int, s: Signal, ts_ms: int, hyst: str, channel: str) -> SwitchLogEntry:
        p = self.persona
        change: dict[str, list] = {}
        spec = self.deltas.get(s.name, {})

        # Opposites cancel, so the bot isn't told to be both rushed and explanatory
        opp = OPPOSITE.get(s.name)
        if opp and opp in self.active:
            del self.active[opp]
            change["cancelled"] = [opp, None]

        for path, val in spec.items():
            if path == "directive":
                continue
            before = _get(p, path)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                lo, hi = CLAMP.get(path, (-1e9, 1e9))
                if path == "voice.pace":      # a switch never slows the voice below the floor (or below where it already was)
                    lo = max(lo, min(CONFIG["live"]["min_pace"], before))
                after = round(min(hi, max(lo, (before or 0) + val)), 2)
                after = int(after) if isinstance(before, int) else after
            else:
                after = val
            if after != before:
                _set(p, path, after)
                change[path] = [before, after]

        if s.name == "language_switch" and s.value:
            new = s.value
            change["language.label"] = [p.language.label, new]
            change["language.primary_code"] = [p.language.primary_code, CONFIG["language_codes"][new]]
            new_spk = CONFIG["voices"][p.voice.tts_model][p.voice.gender][new]
            if CONFIG["live"].get("change_speaker_on_language_switch") and new_spk != p.voice.speaker:
                change["voice.speaker"] = [p.voice.speaker, new_spk]
                p.voice.speaker = new_spk
            p.language.label = new
            p.language.primary_code = CONFIG["language_codes"][new]
            p.language.hinglish_ratio = {"hi": 0.1, "hinglish": 0.4, "en": 0.95}[new]

        directive = spec.get("directive", "")
        if directive:
            self.active[s.name] = directive
        changed = ", ".join(f"{k} {v[0]}→{v[1]}" for k, v in change.items() if k != "cancelled")
        entry = SwitchLogEntry(
            call_id=self.call_id, turn=turn, ts_ms=ts_ms, signal=s.name, confidence=round(s.confidence, 2),
            evidence=s.evidence, change=change,
            reason=f"{s.name} detected{hyst}: {s.evidence}. Changed {changed or 'conversation style'}. {directive}".strip())
        self.switches.append(entry)
        self.last_switch_turn[channel] = turn
        return entry
