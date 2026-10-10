---
description: Replay scripted seller turns through the signal detector and persona policy
argument-hint: [scenario file, default tests/scenarios/*.yaml]
---
Replay seller-turn scenarios ($ARGUMENTS, or every file in `tests/scenarios/`) through `signal_detector` → `persona_policy` without audio (use `python -m persona_bot.cli replay`).

For each scenario, print turn by turn: seller text → detected signal (confidence) → switch? → persona delta. Then write the switch log to `outputs/switch_logs/` and validate it against `schemas/switch_log.schema.json`.

Check and report:
- Expected switches that were missed (false negatives)
- Switches on turns that shouldn't trigger (false positives), and any oscillation
- Cooldown and hysteresis respected
If a scenario doesn't exist yet, create the three demo scenarios: rushed trader (Hinglish → rush), confused small manufacturer (Hindi → confusion), frustrated repeat-callee (English→Hindi switch, then frustration).
