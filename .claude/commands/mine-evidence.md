---
description: Mine past calls for which persona choices work for which seller types
---
Work on `persona_bot/evidence/` using the past-call data (transcripts, summaries, outcomes).

1. Inspect the data schema first and report the fields and row counts. Do not print raw personal data.
2. Define seller segments from available fields (business type, turnover band, primary language, top past objection).
3. Extract observable persona traits per call from transcripts: bot language mix, bot formality (aap/tum), turn length, whether the bot acknowledged objections.
4. For each segment × trait, compute the positive-outcome rate (meeting fixed or best available disposition) with n and a 95% interval. Flag cells with n < 20.
5. Write `evidence/persona_effects.json` and a 10-line plain-English summary of the strongest findings for the demo and approach note.
