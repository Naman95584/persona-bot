# The complete guide to Persona Bot

This guide explains every file, every decision and every number, so you can change any part with confidence and answer any jury question.

---

## 0. The 60-second version

1. **Offline:** read 6,000 past calls. For each one, work out how the bot spoke (language, formality, length, whether it acknowledged objections, pace) and whether a meeting got fixed. Measure which bot behaviours work for which seller types. → `evidence/`
2. **Before a call:** take one seller's file and build a persona: voice, pace, language, formality, warmth, empathy, length, opening line, personalised hooks, objection answers, guardrails. Every choice comes with a *reason*. → `outputs/personas/`
3. **During the call:** after every seller sentence, detect how they feel (rushed / confused / frustrated / interested / switched language). If the signal is strong enough and not too soon after the last change, change the persona: pace, language, tone, and instructions to the LLM. Log the change. → `outputs/switch_logs/`

---

## 1. Running it

```bash
pip install -r requirements.txt
cp .env.example .env                  # add SARVAM_API_KEY at the venue
python -m persona_bot.cli all         # data → mine → personas → replay
python -m persona_bot.cli serve       # http://localhost:8000
MOCK=1 python -m pytest -q
```

| Command | What it does | Output |
|---|---|---|
| `cli data` | synthetic sellers + past calls | `data/samples/*.json`, `data/past_calls.csv` |
| `cli mine` | evidence miner | `evidence/persona_effects.json`, `evidence/summary.md` |
| `cli personas` | persona per seller | `outputs/personas/S00X.json` |
| `cli replay` | runs `tests/scenarios/*.yaml` through the full engine and checks the expected switches | console + `outputs/switch_logs/` |
| `cli serve` | demo web app | browser UI |
| `python -m persona_bot.sarvam.client` | **one call to each Sarvam API**: run this first at the venue | `outputs/smoke_tts.wav` |

**MOCK vs REAL:** no `SARVAM_API_KEY` → mock mode (fake STT, template replies, a chime instead of a voice). With a key → real Sarvam. `MOCK=1` forces mock even with a key. The UI badge shows which mode you're in.

---

## 2. Folder map

```
config.yaml                  every tunable value (§9)
persona_bot/
  config.py                  loads config.yaml + .env; folder paths; mock_mode()
  models.py                  Pydantic contracts: Seller, PersonaSpec, Reason, Signal, SwitchLogEntry
  data/synth.py              synthetic data with planted effects
  evidence/traits.py         transcript → bot traits
  evidence/miner.py          traits + outcomes → evidence; Evidence.best() query
  persona/templates.py       reviewed sentence bank (openings, playbook, mock replies)
  persona/generator.py       seller + evidence → PersonaSpec
  live/signal_detector.py    seller sentence → signals
  live/persona_policy.py     signals → switch decision → persona change + log entry
  live/prompt.py             live persona → LLM system prompt
  live/engine.py             a call: start / turn / end
  sarvam/client.py           Sarvam STT / LLM / TTS + MockClient
  web/app.py, static/index.html   demo UI
  cli.py                     command line
schemas/                     JSON Schemas for the persona spec and the switch log (for humans and the jury)
tests/                       18 tests + demo scenarios (YAML)
evidence/  outputs/          generated artefacts
data/raw/                    REAL data goes here (gitignored)
CLAUDE.md  .claude/commands/ Claude Code context + slash commands
```

---

## 3. Data contracts (`models.py`)

- **Seller** mirrors the deck's list (profile, business type, turnover, categories, engagement, past call outcomes and objections). `past_calls[].seller_language` and `avg_seller_turn_words` matter because they show how the seller actually behaves on calls.
- **Reason {why, source}** is attached to every persona choice. `source` is either a seller field (`seller.years_on_im`) or an evidence key (`evidence:business_type=trader&size=mid|verbosity=crisp → 43% meetings (n=72) vs 20%`).
- **PersonaSpec** = voice + language + tone + conversation_plan + live_adaptation + evidence_used.
- **Signal** = name, confidence 0–0.95, evidence (what triggered it), value (the new language).
- **SwitchLogEntry** = call_id, turn, ts_ms, signal, confidence, evidence, `change` (`{"voice.pace": [1.15, 1.3]}` before→after), reason, latency_ms.

---

## 4. Synthetic data (`data/synth.py`)

- **6 sellers.** S001–S003 are the demo trio (rushed Hinglish trader / confused new Hindi manufacturer / irritated English distributor who switches to Hindi). S004–S006 show the generator handles other types.
- **6,000 past calls**, each with a 3-turn bot transcript and an outcome. The bot's style in history was **randomised**, which is what makes learning possible (and, in real data, it's the first thing to check).
- **Planted truth** (`true_meeting_probability`): language match +10 pts; busy/traders like crisp; small manufacturers like explanatory; small Hindi sellers like formal "aap…ji"; acknowledging price/trust/lead-quality objections +8; busy → fast pace; **gender has no effect**.
- Fixed seed 42 → identical data every run.

### Swapping in real data
Write a short adapter that produces the same columns as `past_calls.csv`:
`call_id, seller_id, business_type, turnover_band, seller_language, top_objection, bot_transcript, bot_voice_gender, bot_pace, outcome, duration_sec`
- `bot_transcript`: the bot's turns joined with ` || `. If the transcript has speaker tags, keep only the bot lines.
- `outcome`: map their dispositions to `meeting_fixed` (or change `evidence.success_outcomes` in config).
- Missing `bot_pace` / `bot_voice_gender` → leave empty; those traits become `unknown` and are skipped.
- Seller files: map their fields to `Seller`. Unknown fields can be dropped; missing ones need sensible defaults.
- If transcripts are **romanised Hindi**, `traits.language_of` will call them English. Add the `ROMAN_HINDI` check from `signal_detector.spoken_language`.

---

## 5. Evidence (`evidence/traits.py`, `evidence/miner.py`)

**Traits from text** (validated 54/54 on every template; `tests/test_traits_and_evidence.py`):
| Trait | Rule |
|---|---|
| language | share of Latin-script words among (Latin + Devanagari) words, ignoring "IndiaMART" and numbers: < 6% → hi, no Devanagari or > 60% → en, otherwise hinglish |
| formality | tum/yaar/hey → casual · ji/sir/madam → aap_formal · else aap_friendly |
| verbosity | average words per bot turn: ≤ 14.5 crisp · ≤ 23.8 normal · more → explanatory |
| acknowledged | "समझ सकती/सकता/रही", "understand", "get that" |
| pace band | configured TTS pace < 0.95 slow, > 1.07 fast |

**Miner**
1. Segments: `business_type & size`, `seller_language & size`, then single attributes, then "all". Size = small (≤ 1.5 Cr), mid (1.5–5 Cr), large (5 Cr+).
2. For each segment × trait × value: wins, n, rate, **Wilson 95% interval** (never goes below 0 or above 1).
3. **Shrinkage:** `(wins + 30 × prior) / (n + 30)`, where prior = that trait value's rate over all calls. Small cells are pulled toward the average.
4. Best value vs the rest of the segment: a **one-sided two-proportion z-test** → p-value.
5. **Benjamini–Hochberg at 10% FDR** across all ~600 tests → "strong". Plain English: of all strong findings, at most ~1 in 10 is expected to be a fluke.
6. **Parent consistency:** "retailer & mid" stays strong only if "all retailers" and "all mid-size" agree.
7. `Evidence.best(attrs, trait, level)` returns the first strong finding for the seller's segments (most specific first), skipping a broad finding if the seller's own sub-segment contradicts it (**Simpson's-paradox guard**).

**Honest limitation (say it):** historical data is observational. If the old bot wasn't randomised, findings can be confounded. The fix is A/B testing personas (Problem 5). With synthetic data, one fluke ("retailers: don't acknowledge objections") still survives. We show it on purpose.

---

## 6. Persona generator (`persona/generator.py`, `persona/templates.py`)

**Decision order for every trait:**
1. Specific evidence (two attributes match) →
2. This seller's own history (e.g. always "busy", new seller with low app use) →
3. Broad evidence (one attribute) →
4. Safe default.

Own history beats broad evidence because averages over very different sellers can point the wrong way (that's how S002 wrongly became "crisp" in an early version).

| Field | How it's set |
|---|---|
| language | evidence, else what the seller **actually spoke on past calls** (beats the profile setting) |
| formality | evidence (only `aap_formal` / `aap_friendly` allowed: we never start casual), else small or Hindi → formal, large + English → friendly |
| verbosity | the decision order above; busy or < 6 words per turn → crisp; ≤ 1 year on IM or < 5 app days → explanatory |
| empathy | 2 + bad past endings + 1 if trust/lead-quality complaints (1–5) |
| warmth | 3, +1 for new/small sellers, −1 if crisp (1–5) |
| gender | evidence, else brand default (our data shows no gender effect) |
| pace | evidence, else follows verbosity: crisp 1.15 / normal 1.0 / explanatory 0.9 |
| speaker | `config.voices[model][gender][language]` |
| temperature | 0.45 + 0.075 × (warmth − 1) → 0.45…0.75 (Bulbul expressiveness) |
| opening | template by language × formality × verbosity, filled with name, business and category |
| hooks | from numbers: lead volume, reply rate, years on IM |
| playbook | the seller's past objections first, plus busy/not_needed always |
| watch_for | expected signals from history (busy → rush, new → confusion, bad endings → frustration, 2+ languages → language_switch) |

**Pitch:** Bulbul v3 has no pitch (it's v2-only), so voice = speaker + pace + temperature. If the jury asks, that's the reason.

**Gender agreement:** Hindi lines use `{rahi}`/`{sakti}` → रही/रहा, सकती/सकता. Bot name: Riya (f) / Rohan (m), written in Devanagari in Hindi lines.

---

## 7. Live adaptation (`live/`)

### Detector (`signal_detector.py`)
- Lexicons with weights: strong 0.8, medium 0.5, weak 0.3. Matches add up, capped at 0.95.
- Features: one-word "क्या?" → confusion 0.8. ≤ 3 words that aren't a greeting/ack → rush 0.3. > 3.5 words/s → rush 0.3. 3 refusals in a row → frustration 0.5. A how/when/how-much question → interest 0.3.
- Negation guard: "not interested" / "नहीं चाहिए" never count as interest.
- Language: an explicit request → 0.95. Otherwise the spoken language vs the bot's current one: 0.85 (≥ 6 words), 0.6 (3–5 words). Hindi ↔ Hinglish is the same family, so no switch.
- `detector_mode: hybrid` asks the LLM for a second opinion (+~1 s per turn). Keep it on `rules` for the demo.

### Policy (`persona_policy.py`)
| Rule | Value | Why |
|---|---|---|
| fire immediately | confidence ≥ 0.75 (−0.05 for expected signals) | clear signals act at once |
| hysteresis | ≥ 0.5 on 2 consecutive turns | one ambiguous turn isn't enough |
| cooldown | 2 turns per channel | no flip-flopping |
| cooldown override | frustration / language request ≥ 0.9 | an angry seller can't wait |
| priority | frustration > confusion > rush > interest | safety first |
| idempotent | an active signal isn't re-applied | no double pace jumps |
| opposites | confusion ↔ rush cancel; frustration cancels interest | no contradictory instructions |
| channels | language and style switch independently | angry + switched to Hindi needs both |
| max | 4 switches per call | |
| speaker on language switch | kept (config flag) | one consistent "person" on the call |

What each signal changes is in `config.yaml → live.deltas` (pace ±, temperature ±, warmth/empathy +, verbosity, plus a directive sentence for the LLM).

### Prompt (`prompt.py`)
Rebuilt **every turn** from the live persona: language rule, formality, length limit, tone, hooks, playbook, escalation, guardrails, and LIVE ADJUSTMENTS (active directives, newest first). That's what makes a switch real on the very next sentence.

### Engine (`engine.py`)
`turn()`: STT (if audio) → detect → policy → LLM reply (trimmed to max sentences for the current verbosity) → TTS with the current speaker/pace/language → return everything with timings.
Robustness: empty STT → "please repeat". LLM error → reviewed template reply (`reply_source: template`). TTS error → text-only.
`end()` writes `outputs/switch_logs/<id>.jsonl` and `outputs/calls/<id>.json` (full transcript, base and final persona).

---

## 8. Demo UI (`web/`)
- Left: seller card + persona spec. Click any section to see **why** and the **source**.
- Middle: the call. 🎙 click to talk / click to send (or hold **Space**). Typed fallback. **Demo-script buttons** come from `tests/scenarios/`, so your non-tech teammate can drive a reliable take.
- Right: live dials (they flash on change), active directives, the switch log, and per-turn latency.
- The mic records 16 kHz mono WAV in the browser (it works on `localhost` without HTTPS).
- The bot audio stops when the seller starts talking (simple barge-in).

---

## 9. Tuning cheat-sheet (`config.yaml`)
| You notice | Change |
|---|---|
| a voice sounds wrong | `voices.bulbul:v3.<gender>.<lang>` (listen to the speakers first) |
| switches feel too eager | raise `live.fire_confidence` / `watch_confidence`, raise `cooldown_turns` |
| switches are missed | add phrases to `LEXICON` in `signal_detector.py`, or lower thresholds |
| rush isn't fast enough | `live.deltas.rush.voice.pace` |
| Hinglish TTS sounds odd | try `hindi_script`, or the v4-flash `_enhi_` personas (`sarvam.tts_model: bulbul:v4-flash` + speaker names) |
| STT is weak on Hinglish | `sarvam.stt_model: saaras:v4` (and set `stt_mode: ""`) |
| the evidence is too strict | `evidence.fdr` 0.10 → 0.20, `min_n` 20 → 15 |

---

## 10. First hour at the venue
1. `python -m persona_bot.sarvam.client` with your key. Play `outputs/smoke_tts.wav`. If any call fails, the error body names the bad field. Fix `config.yaml → sarvam.*`.
2. Listen to 4–6 Bulbul speakers in Hindi and English with your non-tech teammate. Put the best ones in `voices`.
3. Ask the Sarvam team whether Voice Agents can change speaker/pace mid-call. Either way, register an agent with S001's persona prompt for the "Agent ID" checklist item.
4. Ask the organisers about using their seller data with external tools. Then write the adapter (§4) and rerun `cli all`.
5. Run the UI with the real key and do all 3 demo scripts. Watch the latency box.

---

## 11. Demo video script (~6 min)
1. 0:00 Problem: one voice and one style for every seller.
2. 0:30 Evidence slide: `evidence/summary.md` top rows + how we avoid flukes (FDR, shrinkage, Simpson guard).
3. 1:15 Three persona specs side by side. Click "why" on voice/tone for each.
4. 2:00 Live call S001: "जल्दी बोलो" → rush → faster and one-liners.
5. 3:00 Live call S002: "लीड क्या होता है?" → confusion → slower, simpler, with an example.
6. 4:00 Live call S003: English → irritated Hindi → language + frustration switch on the same turn → apology, then the meeting is fixed.
7. 5:00 The switch log file + latency numbers + tests passing.
8. 5:40 Next: A/B test personas in production; learn thresholds from labelled calls.

---

## 12. Jury Q&A prep
- **"How do you know the persona choices work?"** Past-call evidence with intervals, FDR control and shrinkage, and we validated the method on data with known planted effects. Causal proof needs an A/B test, which is our next step.
- **"Why rules for detection, not an LLM?"** Latency (< 1 ms vs ~1 s) and explainability (the log quotes the trigger words). A hybrid mode exists.
- **"What stops the bot flip-flopping?"** Hysteresis, a 2-turn cooldown per channel, idempotence, and opposites cancelling. See the tests.
- **"Why no pitch?"** Bulbul v3 doesn't support it; it's v2-only. We use speaker, pace and temperature.
- **"What if the LLM fails mid-call?"** Reviewed template fallback. The call continues.
- **"Same persona every time?"** Yes, the generator is deterministic (tested).
- **"Customer data?"** Synthetic in the repo. Real data stays in gitignored `data/raw/`.
