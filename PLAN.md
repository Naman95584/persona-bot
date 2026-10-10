# Battle plan: Problem 4, Persona Design

## 0. Do these in the first 30 minutes
- [ ] Get the Sarvam API keys onto every laptop (`.env` → `SARVAM_API_KEY`). Run a hello-world TTS call in Hinglish.
- [ ] **Ask the Sarvam team on the floor** whether a Voice Agent can change speaker, pace or language mid-call. The answer decides the demo architecture (§3).
- [ ] **Ask the organisers** whether you may send seller data to Claude. "No customer data leaves the premises" is a rule. Until they say yes, give Claude only schemas, aggregates and anonymised samples.
- [ ] Open the provided seller data. List the fields and row counts, and confirm past-call transcripts and outcomes exist.
- [ ] Create the repo from this kit (`CLAUDE.md`, `.claude/commands`, `schemas`). Add `data/raw/` to `.gitignore`.

## 1. Roles (team of 3: 2 tech, 1 non-tech)
| Who | Owns | Claude tool |
|---|---|---|
| **Tech A** (voice) | Live loop: STT WS → signal detector → policy → LLM → streaming TTS. Switch log. Latency. | Claude Code |
| **Tech B** (data) | Evidence miner, persona generator, persona specs, golden tests | Claude Code |
| **Non-tech** | Demo scenarios and seller "actor" lines; judges persona fit by ear; approach note; skills.md; records and edits the video; Q&A rehearsal | Claude Project |

The non-tech teammate is a real asset here. Persona *fit* and *voice naturalness* are 2 of the 5 metrics and are judged by ear.

## 2. Map scoring to deliverables
| Criterion (weight) | What wins it |
|---|---|
| Business Impact (25%) | One slide: "segment X with persona choice Y → Z% meeting-fixed vs W% baseline (n=…)" from the past-call evidence. Show scale: N sellers/day × lift. |
| Completeness (20%) | All 4 expected outputs exist: generator on all sample files, specs with reasons, live switch demo, switch log |
| Robustness (20%) | Hysteresis and cooldown (no flapping), noisy-STT handling, scenario replay tests, real data |
| Voice Experience (20%) | Streaming TTS, short bot turns, Hinglish that sounds natural, a switch with no awkward silence. Quote p50 latency. |
| Demo & skills.md (15%) | Tight 6-min video with a side panel showing the switch log live. An honest skills.md with timestamps. |

## 3. Architecture choice (decide by 12:30 PM)
- **Option A, Sarvam Voice Agent only:** fastest, and it's the native "agent ID". Use it if the agent supports changing voice or prompt mid-call (via tools or a webhook).
- **Option B, own loop (recommended fallback):** Python/FastAPI with a browser mic → Saaras realtime WS → our detector → Sarvam LLM → Bulbul streaming TTS. Full control over mid-call switches. **Still register a Sarvam Voice Agent** that uses the persona-generated prompt, so the submission has an agent ID.
- Persona voice knobs: gender/accent → `speaker`, pace → `pace`, energy → `temperature`. Pitch is **v2 only**, so prefer v4-flash `_enhi_`/`_hi_` personas for accent.

## 4. Timeline
**Day 1 (Fri)**
| Time | Tech A | Tech B | Non-tech |
|---|---|---|---|
| 11:00–13:00 | Sarvam STT/TTS hello world, streaming TTS, pick speakers per gender/language | Data exploration, segments, `/mine-evidence` v1 | Pick 3 contrasting demo sellers; write the scenario scripts in a Claude Project |
| 14:00–15:30 | Text-only live loop (typed seller turns → LLM → TTS) | Persona generator v1 → specs for the 3 demo sellers | Listen to TTS samples and rate the fit; draft opening lines and playbooks |
| **15:30** | **Mentor check-in: show 3 persona specs plus one spoken opening per seller** | | |
| 15:30–18:00 | Signal detector and policy, `/switch-test` on scripted turns | Evidence → reasons in specs; distinctness check | Start skills.md; draft the approach note |
| **18:00** | **Stand-up: specs done, switch works on text replay** | | |
| Evening (optional) | Mic in via STT WS; end-to-end voice | Generator on ALL sample files | |

**Day 2 (Sat)**
| Time | Goal |
|---|---|
| 10:00–13:00 | Full voice loop with a live switch; latency tuning; register the Sarvam agent |
| 13:00–15:00 | Freeze features. Rehearse 3 seller scenarios; the non-tech teammate plays the seller. |
| 15:00–17:30 | Record the demo (two takes), edit to 5–7 min, mask any PII |
| 17:30–20:00 | README, skills.md final, approach note, sample outputs, `/submit-check` |
| **~21:00** | **Submit.** Use the time until 23:59 as buffer only. |

## 5. Demo script outline (6 min)
1. (30s) Problem: one voice for every seller → mismatch
2. (60s) Three seller cards → generated persona specs side by side, with the reason for each choice and the evidence stat
3. (3 min) Same scenario × 3 sellers, live voice:
   - Rushed Hinglish trader: crisp, fast pace → **rush detected, cuts to the meeting ask**
   - Confused Hindi-first manufacturer: slow, explanatory → **confusion detected, slows down and simplifies**
   - English-first distributor who switches to Hindi and gets frustrated → **language switch plus empathy escalation**
   - A switch-log panel updates on screen as each switch fires
4. (60s) Evidence and impact: segment × persona → outcome lift, plus latency numbers
5. (30s) What's next: plug into the production Voice Bot, A/B the personas (ties to Problem 5)

## 6. Cut list (when you fall behind, drop from the bottom)
1. Keep: specs with reasons, a text-replay switch log, one live voice switch
2. Then: 3 sellers instead of 2, a second language
3. Nice-to-have: evidence stats with intervals, latency dashboard, interruption handling (barge-in)
