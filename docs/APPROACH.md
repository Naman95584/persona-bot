# Approach note: Problem 4, Persona Design
*Team: Awaaz · Naman Budhiraja (builder), Manish Sharma (voice & conversation), Manish Murli (story & submission) ·
Sarvam agents: see [SARVAM_AGENTS.md](SARVAM_AGENTS.md)*

## Problem
Voice Bot speaks to every seller in one voice and one style for the whole call. Sellers differ in pace, patience, language and objections, and their mood changes mid-call.

## Solution in one line
A **persona generator** builds a seller-specific persona from seller data plus past-call evidence (with a reason for every choice), and a **live adaptation loop** detects rush, confusion, frustration, interest and language switches, then re-tunes voice, language and conversation style on the next sentence, logging every switch.

## What is real data and what is synthetic
We want this to be clear to the jury.

| Part | Data | What it shows |
|---|---|---|
| Evidence-miner **method** (shrinkage, FDR, Simpson guard) | **Synthetic** calls with planted effects | The method recovers known effects and finds none where none were planted. It is *method validation*, not a business result. |
| Sample sellers **S001–S006**, their personas and the numbers in their reasons | **Synthetic** | Early development and tests. |
| **R001–R010** personas, the 3 demo sellers, the demo scenarios | **Real** PS07 seller files, bot calls and transcripts (anonymised: generic names, no IDs or phone numbers in the repo) | Personas come from each seller's *own history and rules*. They do **not** use the synthetic evidence. |
| Business-impact numbers below (`evidence/real_summary.md`) | **Real**, aggregates only | Descriptive statistics on real calls. |
| The miner run on real calls | **Not done yet** | Real personas therefore cite the seller's own history, not mined real evidence. This is the clearest next step. |

## 1. Real dataset
PS07 data, Apr–Sep 2026: **269,455 answered bot calls** to **130,129 sellers**, a 149k-seller profile file and turn-level transcripts for **12.8k calls**.
We triaged all 17 files and used three families: the seller files (profile, engagement, past outcomes, objections), the bot calls (outcome per
call, bot version) and the call turns (transcripts). The 7 evaluator files, the executive calls and the recording sample were not needed.

Mapping decisions that matter:
- Only `meeting_fixed == 1` counts as a meeting (41 calls labelled "Meeting Fixed" without the flag are not counted).
- "General (talked)" is a neutral outcome (`general`), not a bad ending. "Call Later / Busy" maps to callback.
- Twelve objection categories map to our seven. Bot or process problems (call quality, no response, executive gaps) are not seller objections.
- `years_on_im` (from GST year) and `subscription` are weak proxies and are marked as weak signals, never used as strong reasons.
- Sellers with `do_not_call_requested` are excluded, as are sellers whose only objection is "Wrong Contact".

## 2. Evidence from past calls (method)
- From each past call's transcript we infer how the bot spoke: language (script ratio), formality (aap/ji vs tum), length (words per turn), objection acknowledgement and pace. The extractor was validated 54/54 on known templates.
- We compare meeting-fixed rates for each behaviour within seller segments, reported with n and Wilson 95% intervals.
- **Guarding against false findings:** shrinkage toward the global rate, a two-proportion z-test with Benjamini–Hochberg FDR at 10%, parent-segment consistency, and a Simpson's-paradox guard per seller.
- On **synthetic** data with planted effects the miner recovers them (e.g. traders + crisp bot: 43% vs 20% meetings, n=72) and correctly finds no broad gender effect.

## 3. Persona generator
Decision order per trait: **specific evidence → the seller's own call history → broad evidence → safe default.** For real sellers (R…) the evidence step is switched off, so they use their own history and rules. The output is a JSON spec covering voice (Bulbul speaker, gender, pace, temperature), language, tone (warmth, empathy, verbosity), a conversation plan (opening, personalised hooks, objection playbook, escalation, guardrails) and the signals to watch for. Every field carries `reason.why` and `reason.source`. Deterministic: same seller → same persona.

**Real seller personas:** 10 sellers (R001–R010): 3 busy, 3 new/confused, 3 frustrated or language-mixing, 1 typical, chosen from sellers with at least 2 bot calls and transcripts. A seller only counts for a group if its generated persona really shows that group's behaviour. History flags (showed frustration, asked "are you a bot?", "Not Ready / Early-Stage" objection) feed the reasons.

**The 3 demo sellers** (same call scenario, contrasting personas):

| Seller | Type | Persona | Key reasons (own history) |
|---|---|---|---|
| R001 | Busy | Hinglish, formal, **crisp**, pace **1.25**, speaker priya | `busy` objection in past calls; replies average 4.3 words per turn |
| R004 | New / confused | Hinglish, formal, **explanatory**, pace **1.0**, empathy **5/5**, speaker priya | "Not Ready / Early-Stage" objection; 3 calls marked disconnected (attribution approximate) |
| R007 | Frustrated / language-mixing | **English**, formal, crisp, pace **1.25**, empathy **5/5**, speaker ritu; watches for a language switch | Showed frustration on a past call (empathy +2); spoke English and Hinglish across calls; replies average 4.1 words per turn (crisp) |

(Synthetic S001–S003 follow the same logic and remain as regression tests of distinctness.)

## 4. Live adaptation
- **Detector:** weighted lexicons in Devanagari, romanised Hindi and English, plus features (reply length, speech rate, repeated refusals, spoken-language vs bot-language). Runs in under 1 ms. An LLM hybrid mode is optional.
- **Policy:** fire at ≥ 0.75, or ≥ 0.5 on two consecutive turns (hysteresis). 2-turn cooldown with an override for anger and explicit language requests. Priority frustration > confusion > rush > interest. Idempotent. Opposites cancel. **Independent language and style channels**, so an irritated seller who switches language gets both changes on the same turn. Max 4 switches per call.
- **Apply:** pace/temperature/warmth/empathy/verbosity deltas, plus language code (same voice, so it stays one consistent person), plus a directive injected into the LLM prompt, which is rebuilt every turn. Mid-call slow-downs are soft (confusion −0.1, frustration −0.05) with a **0.9 pace floor**.
- **Switch log** (`outputs/switch_logs/*.jsonl`): turn, time, signal, confidence, quoted trigger words, before→after per field, reason, latency.

## 5. Voice and reply quality: what we learned
- **Speed:** voice testing showed the bot was too slow for real sellers. We re-scaled pace (slow 1.0, normal 1.1, fast 1.25), softened the slow-downs, added the 0.9 floor, and stopped synthetic evidence from setting pace for real sellers.
- **A reply bug we fixed:** a crisp reply was cut to one sentence, dropping the question. An audit of all 16 sellers on the real LLM found the question lost in 34 of 64 replies; after the fix, 0 of 64. Trimming now always keeps the final question.
- **An experiment we reverted:** we applied a strict reply spec (word caps, forced acknowledgement and question every turn). Replies became robotic, so we reverted it. Lesson: hard word caps hurt naturalness; keep length as guidance and protect only the question.
- **Wording fix (targeted, no word caps):** an audit of 16 sellers x 6 turns on the real LLM found deficit framing ("zero leads last month", "only 3") in about 13 of 96 replies and Latin words inside Hindi/Hinglish sentences in 78 of 96. We fixed both at the source: hooks are now pure untapped-demand framing (the numbers stay in the reason as the data source but are never quoted), the prompt carries a framing rule and a one-script-per-sentence rule, the Hindi/Hinglish template lines are written in Devanagari, product names and the city are not given to Hindi/Hinglish personas, and two light code safety nets remain (a Devanagari word guard and one retry if a reply still quotes low numbers). Re-audit: deficit framing 0 of 96 and mixed-script 4 of 96; the 4 were plain English words ("pricing", "details", "customer") that we then added to the word list. No hard length caps were reintroduced.

## 6. Sarvam Voice Agents
Each demo seller has a Sarvam Voice Agent generated from its persona spec (`python -m persona_bot.export_agent <id>`: greeting, language, speaker, system prompt). Agent IDs and how each was built: **[SARVAM_AGENTS.md](SARVAM_AGENTS.md)**. The live mid-call persona switching runs in our app, not inside the Sarvam agent.
**Finding (R004 agent):** the greeting could not be interrupted by the seller. We shortened the greeting as the fix.

## 7. Business impact (real data, aggregates only; `evidence/real_summary.md`)
1. **The personalised-script bot fixed meetings on 14.2% of calls vs 10.6% for other bots in the same month** (+3.6 points, 95% CI +0.3 to +7.0; +5.4 points after adjusting for business type × turnover).
2. **One persona for everyone leaves a gap by seller type and size:** the meeting rate varies from 9.5% to 12.2% by seller type and from 8.7% to 11.2% by size. Sellers differ, which is the case for matching the persona to the seller.
3. **60% of answered calls end within 30 seconds with almost no meetings (0.0% and 0.7%).** The opening decides the call, which is why the persona's first line, pace and language matter.

**Impact estimate:** at about 69k answered calls per month (September volume), +3.6 points is roughly **2,500 extra meetings per month**. This is an estimate: the confidence interval (+0.3 to +7.0 points) corresponds to about 200 to 4,900 meetings per month.

**Caveats, stated plainly:**
- The personalised-script trial is small: **452 recorded calls** from 325 sellers, all in September, and the 452 may not be a random sample of the trial.
- Assignment to bot versions does not look random, and segment mix differs between the trial and the controls (we adjust for business type × turnover and for lead type; the gap stays positive).
- Duration is partly an *outcome* of the call (sellers who agree to a meeting talk longer), so the duration pattern in finding 3 shows where meetings happen, not that long calls cause them. Some very short calls may also not be humans (IVR or voicemail).
- Findings 2 and 3 are observational and do not prove that a personalised persona will win these meetings. They show where the headroom is. The trial result is borderline (lower bound +0.3 points), so we call it promising, not proven.

## 8. Robustness
31 automated tests: extractor accuracy, evidence recovery, reasons present, determinism, persona distinctness, hysteresis, cooldown, override, idempotence, opposites, clamping, both channels, reply trimming (the question is never lost), wording rules (no deficit framing, one script per sentence), all demo scenarios (including a calm-seller **false-positive check** and the three real-seller scenarios), and the API end to end. LLM failure → reviewed template fallback. Empty STT → polite re-ask.

## 9. Next steps
- Run the evidence miner on the real calls so real personas cite mined evidence, not only the seller's own history.
- A/B test generated personas against the current single persona (ties to Problem 5), with random assignment and a larger sample.
- Make rushed replies reliably end with the ask (the model sometimes answers a hurried seller with an acknowledgement and no question); learn switch thresholds from labelled calls; move to streaming STT/TTS for lower latency.

## Data and privacy
The repository holds only synthetic sellers and anonymised demo sellers (generic names, no GLIDs, phones or free text). Real seller files and transcripts stay in the gitignored `data/raw/` and go only to the provided Sarvam APIs. This document contains aggregates only.
