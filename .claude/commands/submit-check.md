---
description: Audit the repo against the submission checklist and scoring criteria
---
Audit the project for submission readiness and print a checklist with ✅ / ❌ and the fix for each ❌:

Submission items: demo video link, approach note, Sarvam agent ID or live link, code with README (setup in ≤5 commands), skills.md, sample outputs (`outputs/personas/*.json` for every sample seller, ≥1 `outputs/switch_logs/*.jsonl`), team name and members.

Expected outputs: generator runs on all sample files, every persona field has a reason, ≥1 mid-call switch in the logs, 2+ languages demonstrated.

Hygiene: no API keys in the repo, `data/raw/` gitignored, no unmasked phone numbers, names or GLIDs in outputs or README, and `pytest` passes.

Finally, score us 1–5 on each jury criterion (Business Impact 25, Completeness 20, Robustness 20, Voice 20, Demo & skills.md 15) and name the single highest-leverage fix.
