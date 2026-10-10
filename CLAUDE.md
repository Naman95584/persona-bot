# CLAUDE.md: Persona Design (IndiaMART Voice AI Hackathon 2.0, Problem 4)

Claude Code reads this file at the start of every session. Keep it current, because it is the team's shared brain.

## Goal
For each seller, generate a Voice Bot persona from their seller data **before** the call, then adapt it **live** when the seller gets frustrated, confused, interested or rushed, or switches language. Build on Sarvam (Saaras STT, Bulbul TTS, Sarvam LLM, Voice Agents).

Deadline: **Sat 10 Oct, 11:59 PM** (target 9 PM). Optimise for a working end-to-end demo over polish.

## Must-ship outputs (the jury checks each)
1. `python -m persona_bot.cli personas`: runs on every file in `data/samples/` → writes `outputs/personas/<seller_id>.json`
2. Persona spec per seller, valid against `schemas/persona_spec.schema.json`, where **every field has a `reason`** citing a seller field or an evidence stat
3. A live voice demo: the same scenario for 2–3 contrasting sellers, with ≥1 live mid-call switch
4. A switch log `outputs/switch_logs/<call_id>.jsonl`, valid against `schemas/switch_log.schema.json`
5. `skills.md` updated as we go (run `/log-skill` after each milestone), plus a README and sample outputs

## Architecture
```
            OFFLINE                         PRE-CALL                          LIVE CALL
 past calls (transcripts,     seller file ──► persona_generator ──► persona_spec.json
 summaries, outcomes)                         (rules from evidence        │
        │                                      + LLM for wording)         ▼
        ▼                                                         ┌──────────────────────┐
 evidence_miner ──► evidence/persona_effects.json ──────────────► │ STT (Saaras, WS)     │
 (segment × persona choice                                        │   ▼                  │
  → outcome rate, n)                                              │ signal_detector      │──► switch_log.jsonl
                                                                  │   ▼  (hysteresis)    │
                                                                  │ persona_policy       │
                                                                  │   ▼                  │
                                                                  │ LLM reply (prompt    │
                                                                  │   rebuilt from spec) │
                                                                  │   ▼                  │
                                                                  │ TTS (Bulbul, stream) │
                                                                  └──────────────────────┘
```

### Modules (actual code)
- `persona_bot/data/synth.py`: synthetic sellers + past calls (planted effects). Replace with an adapter for real data.
- `persona_bot/evidence/traits.py`: transcript → bot traits (language, formality, verbosity, ack, pace)
- `persona_bot/evidence/miner.py`: segment × trait → meeting rate; shrinkage, BH-FDR, parent consistency, Simpson guard; `Evidence.best()` query API
- `persona_bot/persona/templates.py`: reviewed openings, objection playbook, mock replies (gender-agreeing Hindi)
- `persona_bot/persona/generator.py`: specific evidence → own history → broad evidence → default; every field has a `Reason`
- `persona_bot/live/signal_detector.py`: rules (lexicons + features) → `Signal`s; optional LLM hybrid
- `persona_bot/live/persona_policy.py`: `LiveState.step()`: hysteresis, cooldown, priority, idempotence, opposites, language/style channels → `SwitchLogEntry`
- `persona_bot/live/prompt.py`: live persona → LLM system prompt (rebuilt every turn)
- `persona_bot/live/engine.py`: `Call.start/turn/end`: STT → detect → policy → LLM (template fallback) → TTS; writes logs
- `persona_bot/sarvam/client.py`: Saaras / sarvam-m / Bulbul over httpx + `MockClient`
- `persona_bot/web/app.py` + `static/index.html`: demo UI
- `persona_bot/cli.py`: `data | mine | personas | replay | serve | all`
- Tests: `MOCK=1 pytest -q`. Scenarios in `tests/scenarios/*.yaml` (`expect` = switches that must fire)

## Sarvam constraints (docs.sarvam.ai, checked 9 Oct 2026)
- TTS models: `bulbul:v4-flash` (recommended; personas like `shubh_enhi_ads`), `bulbul:v3` (default), `bulbul:v2` (legacy). Speaker names are lowercase and must match the model.
- `pace`: 0.5–2.0 (v3/v4-flash). `pitch` and `loudness`: v2 only. `temperature`: v3/v4-flash only. Max 2500 characters per request.
- Use **streaming TTS** (WebSocket) and **realtime STT WebSocket** for latency. Voice Experience is 20% of the score.
- Read the API key from env `SARVAM_API_KEY`. Never hard-code it or commit it.
- Before writing integration code, check the current docs at docs.sarvam.ai, because parameters change between model versions. Ask the Sarvam team on the floor whether Voice Agents can change voice or speaker mid-call. If they can't, run our own STT→LLM→TTS loop for the demo and still register an agent on the platform for the submission's "Agent ID / live link".

## Data rules
- **No customer data leaves the premises.** Real seller files and transcripts stay in `data/raw/`, which is **gitignored**. Do not upload them to any external service other than the provided Sarvam keys and the approved LLM key.
- `data/samples/` holds anonymised or synthetic seller files only. Mask phone numbers, names and GLIDs before anything goes into the demo video.
- Before sending real records to any hosted model (including this tool), confirm with the organisers that it is allowed. Otherwise work on schemas and aggregates.

## Conventions
- Python 3.11+, `pip install -r requirements.txt`, `pydantic` models that mirror the JSON schemas, `pytest` for policy and detector unit tests
- Config in `config.yaml`, secrets in `.env`
- Keep functions small. Log every LLM and TTS call's latency to `outputs/latency.csv`, because we will quote p50 and p95 in the demo.
- The 3 demo sellers are regression-tested in `tests/test_persona.py::test_demo_sellers_are_distinct`

## Commands
- `/persona <seller_file>`: generate and explain a persona spec
- `/mine-evidence`: run or extend the evidence miner and summarise the findings
- `/switch-test`: replay scripted seller turns through the detector and policy, then print the switch log
- `/log-skill`: append the latest milestone to skills.md
- `/submit-check`: audit the repo against the submission checklist and scoring
