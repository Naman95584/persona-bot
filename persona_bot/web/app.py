"""
app.py: the demo web server (FastAPI).

Run:  python -m persona_bot.cli serve   → open http://localhost:8000

Endpoints (all JSON):
  GET  /api/health                  → {mock: bool}
  GET  /api/sellers                 → seller cards + persona summary
  GET  /api/sellers/{id}            → full seller + full persona spec (with reasons)
  GET  /api/scenarios/{id}          → scripted seller lines for the demo buttons
  POST /api/calls        {seller_id} → starts a call, returns the opening line + audio
  POST /api/calls/{id}/turn         → multipart: audio (wav) OR text; returns reply + audio + switches
  POST /api/calls/{id}/end          → writes switch log + transcript to outputs/

Calls live in memory (a dict): fine for a demo. Restarting the server ends calls.
Browser mic access works on http://localhost without HTTPS. For another
device, use HTTPS or a tunnel.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from persona_bot.config import PERSONAS_DIR, ROOT, SAMPLES_DIR, mock_mode
from persona_bot.live.engine import Call, new_call
from persona_bot.persona.generator import generate, load_seller

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Persona Bot – IndiaMART Voice AI Hackathon")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
CALLS: dict[str, Call] = {}


def _persona(seller_id: str):
    p = PERSONAS_DIR / f"{seller_id}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    spec = generate(load_seller(SAMPLES_DIR / f"seller_{seller_id}.json"))
    p.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return spec.model_dump()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"mock": mock_mode()}


@app.get("/api/sellers")
def sellers():
    out = []
    for f in sorted(SAMPLES_DIR.glob("seller_*.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        p = _persona(s["seller_id"])
        out.append({"seller_id": s["seller_id"], "display_name": s["display_name"], "city": s["city"],
                    "business_type": s["business_type"], "turnover_band": s["turnover_band"],
                    "language": p["language"]["label"], "segment": p["segment"],
                    "verbosity": p["tone"]["verbosity"], "pace": p["voice"]["pace"]})
    return out


@app.get("/api/sellers/{seller_id}")
def seller(seller_id: str):
    f = SAMPLES_DIR / f"seller_{seller_id}.json"
    if not f.exists():
        raise HTTPException(404, "unknown seller")
    return {"seller": json.loads(f.read_text(encoding="utf-8")), "persona": _persona(seller_id)}


@app.get("/api/scenarios/{seller_id}")
def scenario(seller_id: str):
    for f in sorted((ROOT / "tests" / "scenarios").glob(f"{seller_id}_*.yaml")):
        sc = yaml.safe_load(f.read_text(encoding="utf-8"))
        return {"title": sc["title"], "lines": [t["text"] for t in sc["turns"]]}
    return {"title": None, "lines": []}


class StartReq(BaseModel):
    seller_id: str


@app.post("/api/calls")
def start(req: StartReq):
    call = new_call(req.seller_id)
    CALLS[call.id] = call
    return call.start()


@app.post("/api/calls/{call_id}/turn")
async def turn(call_id: str, text: str | None = Form(None), audio: UploadFile | None = File(None),
               audio_seconds: float | None = Form(None)):
    call = CALLS.get(call_id)
    if not call:
        raise HTTPException(404, "call not found (server restarted?)")
    data = await audio.read() if audio else None
    return call.turn(text=text, audio=data, audio_seconds=audio_seconds)


@app.post("/api/calls/{call_id}/end")
def end(call_id: str):
    call = CALLS.pop(call_id, None)
    if not call:
        raise HTTPException(404, "call not found")
    return call.end()
