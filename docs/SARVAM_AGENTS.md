# Sarvam Voice Agents

One Sarvam Voice Agent per demo seller. Each agent is **generated from our persona spec**, not written by hand:

```bash
python -m persona_bot.export_agent R004     # → outputs/agent_R004.txt (greeting, language, speaker, system prompt)
```

The text file is what gets pasted into the Sarvam Voice Agents builder. Re-export and re-paste after any change to a persona,
the prompt rules or the voice settings.

| Seller ID | Seller type | Sarvam Agent ID | Built from | Notes |
|---|---|---|---|---|
| R004 | New / confused | `Voice-AI-Aw-9bef087e-5b49` | `outputs/agent_R004.txt` | Greeting is not interruptible; shortened as a fix |
| R007 | Frustrated / language-mixing | `R007-voice--dacaa385-9967` | `outputs/agent_R007.txt` | |
| R001 | Busy | `voice-ai-aw-4bc1e71b-7b2e` | `outputs/agent_R001.txt` | |

**Seller types come from each persona:**
- **R001, busy:** base persona is crisp and fast (own history: a `busy` objection and short replies).
- **R004, new / confused:** base persona is explanatory and slower (own history: a "Not Ready / Early-Stage" objection).
- **R007, frustrated / language-mixing:** starts in English, with frustration and language switching on its watch list.

## What runs where

- **In the Sarvam agent:** the opening line, starting language, speaker and the system prompt built from the persona spec.
- **In our app (not in the Sarvam agent):** the live mid-call persona switching. Our signal detector reads each seller turn,
  the persona policy changes pace, tone, length and language (with hysteresis and cooldown), the prompt is rebuilt every turn,
  and each change is written to `outputs/switch_logs/<call_id>.jsonl`. The demo of the switches is the web UI
  (`python -m persona_bot.cli serve`).
