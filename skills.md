# skills.md: Build journey & tools used

**Team:** Awaaz · **Members:** Naman Budhiraja (builder), Manish Sharma (voice & conversation), Manish Murli (story & submission)
**Problem:** 4 · Persona Design
**Sarvam Agents:** R004 `Voice-AI-Aw-9bef087e-5b49` · R007 `R007-voice--dacaa385-9967` · R001 `voice-ai-aw-4bc1e71b-7b2e` (details: [docs/SARVAM_AGENTS.md](docs/SARVAM_AGENTS.md))

## What we built (one paragraph)
A persona generator that turns each seller's data and past-call history into a Voice Bot persona (voice, pace, language, formality, tone, opening, objection playbook, guardrails), with a reason for every choice. A live loop detects rush, confusion, frustration, interest and language switches, and re-tunes the persona mid-call with hysteresis and cooldowns, logging each switch. It runs on Sarvam Saaras, the Sarvam LLM and Bulbul, with a browser demo UI, and each demo seller also has a Sarvam Voice Agent generated from its persona spec. We validated the method on synthetic data, then built **10 real seller personas** from the PS07 dataset (269,455 answered bot calls, 130,129 sellers, transcripts for 12.8k calls). Real-data findings are in `evidence/real_summary.md` (aggregates only).

## Tools used
| Tool | What we used it for |
|---|---|
| Sarvam Saaras (STT) | Transcription of seller speech, Hinglish/code-mixed (`saaras:v3`, codemix) |
| Sarvam Bulbul (TTS) | Persona voices: speaker, pace, temperature per persona (`bulbul:v3`) |
| Sarvam LLM | Bot replies conditioned on the persona spec (`sarvam-105b-conversations`, after `sarvam-m` was deprecated) |
| Sarvam Voice Agents | One agent per demo seller (R001, R004, R007), generated from the persona spec |
| Claude Code | Pair-programming the generator, detector, policy, real-data adapter, tests; repo conventions in CLAUDE.md; custom slash commands (/persona, /switch-test, /submit-check) |
| Claude (Projects) | Shared team workspace: persona design, Hinglish objection playbooks, demo scripts, Q&A rehearsal |
| Python libs | pydantic (data contracts), FastAPI + uvicorn (demo server), httpx (Sarvam calls), pandas (real-data stats), PyYAML, pytest |

## Skills we developed / applied
- Persona design grounded in past-call evidence (segment × trait → outcome rate) and, for real sellers, in the seller's own history
- Careful use of real data: triage by schema only, aggregates in the repo, anonymised demo sellers
- Real-time signal detection with hysteresis and cooldown
- Voice tuning by ear (pace scale, floors) and conversation-quality debugging on the real LLM
- Hinglish conversational writing

## Build journey
<!-- Append with /log-skill after each milestone. Be honest: dead ends count. -->

### Friday 9 Oct: foundation (see earlier entries below), then real data
- **Fri 11:00:** Picked Problem 4. Set up the Claude Project with the brief and the repo with CLAUDE.md and slash commands. Key question for Sarvam: can the voice change mid-call?
- **Fri ~11:15:** Chose our own STT → policy → LLM → TTS loop (full control of mid-call switches), push-to-talk for v1, and a mock mode for offline development. Built Pydantic contracts with a `Reason` on every persona field.
- **Fri:** Synthetic sellers and past calls with planted effects, to test the evidence miner before real data arrived. The trait extractor was 53/54 on the first run (a boundary case at exactly 24 words); after tuning the threshold it was 54/54.
- **Fri (dead end → fix):** The first miner flagged spurious "strong" findings (multiple comparisons). Added shrinkage, a 99% bar, and parent consistency. Still too lenient: every seller became "crisp + fast", and a fake gender effect was being cited. Replaced it with a two-proportion z-test + Benjamini–Hochberg FDR and doubled the data to 6,000 calls.
- **Fri (Simpson's paradox):** S002 (small manufacturer) inherited "small sellers like crisp", a finding driven by small traders. Introduced the decision order: specific evidence → own history → broad evidence → default, plus a contradiction guard. The demo trio became clearly distinct.
- **Fri:** Live detector (lexicons + features) and policy (hysteresis, cooldown, priority, idempotence, opposites). A test showed an angry seller switching to Hindi got only the frustration change, with the bot still in English. Split the policy into independent language/style channels.
- **Fri:** Sarvam client + mock, engine with template fallback, FastAPI UI with live dials and switch log, scenario scripts (incl. a false-positive control), 18 tests passing.
- **Fri afternoon, real Sarvam APIs:** First calls with the real key failed with 403 (it looked like a Voice-Agents-only key); a new key fixed it. Then the LLM call failed because `sarvam-m` had been deprecated; switched to `sarvam-105b-conversations`. TTS, STT and LLM all worked (about 1.3–1.8 s, 0.3 s and 0.15 s on the smoke test). Exported the first Sarvam agent configs from the persona spec (`export_agent`).
- **Fri evening, real data triage:** The PS07 folder had 17 files. We read **schema only** (column names, row counts, no values) and scored each against the problem: used **3 file families** (seller files, bot calls, call turns); skipped the 7 evaluator files, executive calls and recording sample. Wrote `triage_raw.py`.
- **Fri evening, outcome mapping decisions:** only `meeting_fixed == 1` counts as a meeting (41 "Meeting Fixed" calls without the flag do not); "General (talked)" became a neutral `general` outcome instead of a bad ending; 12 objection categories mapped to our 7, with bot or process problems (call quality, no response) mapped to none; `years_on_im` and `subscription` marked as weak proxies. Added an optional `history` field (showed frustration, asked if a bot, objection categories).
- **Fri evening, 10 real seller personas:** Wrote `real_adapter.py` (skips do-not-call sellers; needs at least 2 bot calls and transcripts; generic display names; real IDs kept out of the repo). Dead end: our first pick of the "new/confused" group came out *crisp* because a `busy` objection outranked it, so the picker now checks that each chosen seller's generated persona really shows its group's behaviour. Result: R001–R010 and three demo sellers: **R001 busy, R004 new/confused, R007 frustrated/language-mixing**.

### Saturday 10 Oct: evidence, voice, quality and submission
- **Sat, real stats:** `real_stats.py` → `evidence/real_summary.md` (aggregates only, n ≥ 30). Key lesson: the personalised-script trial ran only in September, so the fair control is other bots *in the same month*. Result: 14.2% vs 10.6% meetings (+3.6 pts, 95% CI +0.3 to +7.0; +5.4 after adjusting for business type × turnover) on a small trial of 452 recorded calls. Also: meeting rate varies by seller type (9.5%–12.2%) and size (8.7%–11.2%), and 60% of answered calls end within 30 seconds with almost no meetings. Estimate: about 2,500 extra meetings per month at ~69k answered calls (an estimate, with wide uncertainty).
- **Sat, demo scenarios:** Wrote fresh scripted lines for R001 (rush), R004 (confusion) and R007 (language switch + frustration); all pass in the replay. Made the seller chips in the UI horizontally scrollable.
- **Sat, Sarvam agents:** Built three Voice Agents from the exported persona text (R001, R004, R007), documented in `docs/SARVAM_AGENTS.md`. Finding on the R004 agent: the greeting could not be interrupted by the seller; we shortened the greeting as the fix. Live persona switching stays in our app.
- **Sat, voice-speed fix:** Listening to the bot showed it was too slow for real sellers. Re-scaled pace to slow 1.0 / normal 1.1 / fast 1.25, softened mid-call slow-downs (confusion −0.1, frustration −0.05), added a **0.9 pace floor**, and stopped the **synthetic evidence** from driving real sellers' personas (it had been setting their pace and length from synthetic effects).
- **Sat, reply-quality experiment (applied, then reverted):** A reply cut to "समझ गई sir, आपका time valuable है" with no ask led us to apply a strict teammate voice-agent spec (word caps, forced acknowledgement and question every turn, Devanagari-only Hinglish, new playbook lines, bot and do-not-call detection). Replies became **robotic**. We tried loosening it, then **reverted all of it**. **Lesson: hard word caps hurt naturalness.** Keep length as guidance.
- **Sat, the targeted fix we kept:** An audit of all 16 sellers on the real LLM found that the trimmer dropped the model's question in **34 of 64 replies**. The trimmer now always keeps the final question (0 of 64 after the fix); added 6 tests (24 total).
- **Sat, wording fix (deficit framing and mixed scripts):** after the revert an audit (16 sellers x 6 turns, real LLM) found deficit framing ("zero leads", "only 3") in about 13 of 96 replies and Latin words inside Hindi/Hinglish sentences in 78 of 96. Fixed at the source, not with word caps: positive demand hooks (numbers stay in the reason, never quoted), a framing rule and a one-script-per-sentence rule in the prompt, Devanagari Hindi/Hinglish template lines, no Latin product or city names given to Hindi personas, plus two light safety nets (a Devanagari word guard and one retry on deficit wording). Re-audit: 0 of 96 deficit, 4 of 96 mixed (plain English words we then added to the word list). Dead end on the way: the first audit runs hit the API rate limit (429) and silently fell back to templates, so we added a throttle and retry before trusting the numbers. 31 tests now.
- **Sat, honest open issues:** a hurried seller sometimes still gets an acknowledgement with no ask from the model (the trimmer never drops the question; the model just does not always write one). Real personas use the seller's own history, not mined real evidence (the miner has only run on synthetic data so far).

## What we'd do next
- Run the evidence miner on the real calls, so real personas cite mined evidence
- A/B test personas against meeting-fixed rate with random assignment and a bigger sample
- Make rushed replies reliably end with the ask, without hard word caps
- Learn the switch thresholds from labelled calls instead of hand-tuning them
