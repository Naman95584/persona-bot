"""
cli.py: one entry point for every stage.

  python -m persona_bot.cli data        # 1. synthetic sellers + 6,000 past calls
  python -m persona_bot.cli mine        # 2. evidence miner → evidence/
  python -m persona_bot.cli personas    # 3. persona spec for every seller → outputs/personas/
  python -m persona_bot.cli replay      # 4. run scripted scenarios, print turn-by-turn + write switch logs
  python -m persona_bot.cli serve       # 5. demo web app on http://localhost:8000
  python -m persona_bot.cli all         # 1-4 in order (what the jury can run to reproduce outputs)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from persona_bot.config import CONFIG, ROOT


def cmd_data():
    from persona_bot.data import synth
    synth.main()


def cmd_mine():
    from persona_bot.evidence import miner
    ev = miner.run()
    strong = [f for f in ev["findings"] if f["strength"] == "strong"]
    print(f"mined {ev['meta']['n_calls']} calls · baseline {ev['meta']['baseline']['rate']:.1%} · "
          f"{len(strong)} strong findings → evidence/summary.md")


def cmd_personas():
    from persona_bot.persona import generator
    for sp in generator.run():
        print(f"  {sp.seller_id}  {sp.segment:45} {sp.language.label:8} {sp.tone.verbosity:11} "
              f"pace={sp.voice.pace:<5} empathy={sp.tone.empathy}  evidence={len(sp.evidence_used)}")


def cmd_replay(paths: list[str]):
    """Plays each scenario through the full engine (mock client) and checks expected switches."""
    from persona_bot.live.engine import new_call
    from persona_bot.sarvam.client import MockClient
    files = [Path(p) for p in paths] or sorted((ROOT / "tests" / "scenarios").glob("*.yaml"))
    ok_all = True
    for f in files:
        sc = yaml.safe_load(f.read_text(encoding="utf-8"))
        call = new_call(sc["seller_id"], client=MockClient())
        print(f"\n━━ {sc['title']} ({sc['seller_id']}) ━━")
        print(f"  BOT   {call.start()['bot_text']}")
        for t in sc["turns"]:
            r = call.turn(text=t["text"])
            got = [s["signal"] for s in r["switches"]]
            ok = sorted(got) == sorted(t.get("expect", []))
            ok_all &= ok
            sig = ", ".join(f"{s['name']} {s['confidence']:.2f}" for s in r["signals"]) or "-"
            print(f"  SELLER {t['text']}\n         signals: {sig}")
            for s in r["switches"]:
                chg = ", ".join(f"{k} {v[0]}→{v[1]}" for k, v in s["change"].items())
                print(f"         ⟲ SWITCH {s['signal']}: {chg}")
            if not ok:
                print(f"         ✗ expected {t.get('expect', [])}, got {got}")
            print(f"  BOT   {r['bot_text']}")
        out = call.end()
        print(f"  → {Path(out['switch_log']).relative_to(ROOT)}  meeting_fixed={out['summary']['meeting_fixed']}")
    print("\nALL SCENARIOS PASS" if ok_all else "\nSOME SCENARIOS FAILED")
    return ok_all


def cmd_serve():
    import uvicorn
    from persona_bot.config import mock_mode
    print(f"Mode: {'MOCK (no SARVAM_API_KEY)' if mock_mode() else 'REAL Sarvam APIs'}")
    print(f"Open http://localhost:{CONFIG['server']['port']}")
    uvicorn.run("persona_bot.web.app:app", host=CONFIG["server"]["host"], port=CONFIG["server"]["port"])


def main(argv: list[str]):
    if not argv:
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    if cmd == "data": cmd_data()
    elif cmd == "mine": cmd_mine()
    elif cmd == "personas": cmd_personas()
    elif cmd == "replay": sys.exit(0 if cmd_replay(rest) else 1)
    elif cmd == "serve": cmd_serve()
    elif cmd == "all":
        cmd_data(); cmd_mine(); cmd_personas(); sys.exit(0 if cmd_replay([]) else 1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
