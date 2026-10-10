"""
export_agent.py: prints what to paste into the Sarvam Voice Agents builder for one seller.

    python -m persona_bot.export_agent S001

Output: Greeting, System prompt, Language and Speaker, taken from the generated persona.
Also saved to outputs/agent_<seller_id>.txt so you can copy from VS Code.
"""
import json
import sys

from persona_bot.config import OUTPUTS_DIR, PERSONAS_DIR, SAMPLES_DIR
from persona_bot.live.prompt import system_prompt
from persona_bot.models import PersonaSpec
from persona_bot.persona.generator import load_seller

sid = sys.argv[1] if len(sys.argv) > 1 else "S001"
persona = PersonaSpec(**json.loads((PERSONAS_DIR / f"{sid}.json").read_text(encoding="utf-8")))
seller = load_seller(SAMPLES_DIR / f"seller_{sid}.json")

text = f"""=== SARVAM VOICE AGENT CONFIG for {sid} ({seller.display_name}) ===

[Greeting]
{persona.conversation_plan.opening.line}

[Starting language]   {persona.language.primary_code}
[Allowed languages]   Hindi + English  (turn ON "Switch language during call")
[Speaker]             {persona.voice.speaker}   (gender {persona.voice.gender}, pace {persona.voice.pace})

[System prompt]
{system_prompt(persona, seller, [])}

[Extra rule to add at the end of the system prompt]
If the seller sounds rushed, reply in one short sentence. If confused, slow down and explain simply
with an example. If irritated, apologise first and offer to call later or stop calling.
"""
out = OUTPUTS_DIR / f"agent_{sid}.txt"
out.write_text(text, encoding="utf-8")
print(text)
print(f"(saved to {out})")
