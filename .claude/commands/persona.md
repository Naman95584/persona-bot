---
description: Generate a persona spec for a seller file and explain each choice
argument-hint: <path to seller file>
---
Generate a persona for the seller in $ARGUMENTS.

1. Read the seller file. Read `evidence/persona_effects.json` if it exists.
2. Run `python -m persona_bot.persona.generator <file>`.
3. Validate the output against `schemas/persona_spec.schema.json`.
4. Print a short table: field → value → reason. Flag any field whose reason does not cite a seller field or an evidence stat.
5. Compare against the other personas in `outputs/personas/`. If this one is not clearly distinct from a different seller type, say so (distinctness is scored).
