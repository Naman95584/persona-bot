"""
client.py: one small wrapper around the three Sarvam APIs we use, plus a mock.

  stt(audio)  → Saaras speech-to-text   POST /speech-to-text   (multipart)
  chat(msgs)  → Sarvam LLM               POST /v1/chat/completions
  tts(text)   → Bulbul text-to-speech    POST /text-to-speech  → base64 WAV

Paths and models come from config.yaml, so a docs change is a one-line edit.
VERIFY AT THE VENUE: run `python -m persona_bot.sarvam.client` with your key.
It makes one call to each API and prints what came back.

Why plain httpx and not the sarvamai SDK? Fewer moving parts, and every request
is visible here for debugging. Swapping to the SDK later is easy.

Every call's latency is appended to outputs/latency.csv. Quote p50/p95 in the demo.
"""
from __future__ import annotations

import base64
import csv
import io
import math
import re
import struct
import time
import wave

import httpx

from persona_bot.config import CONFIG, OUTPUTS_DIR, mock_mode, sarvam_key

S = CONFIG["sarvam"]
THINK = re.compile(r"<think>.*?</think>", re.S)   # sarvam-m may emit reasoning in <think> tags


class SarvamError(RuntimeError):
    pass


def log_latency(kind: str, ms: int, extra: str = "") -> None:
    path = OUTPUTS_DIR / "latency.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts", "kind", "ms", "extra"])
        w.writerow([int(time.time()), kind, ms, extra])


class SarvamClient:
    """Real client. Needs SARVAM_API_KEY."""

    mock = False

    def __init__(self, key: str):
        self.key = key
        self.http = httpx.Client(base_url=S["base_url"], timeout=S["timeout_s"])

    def _check(self, r: httpx.Response, what: str) -> dict:
        if r.status_code >= 400:
            # The body usually says exactly which parameter is wrong: surface it
            raise SarvamError(f"{what} failed {r.status_code}: {r.text[:500]}")
        return r.json()

    def stt(self, audio: bytes, filename: str = "turn.wav", language_code: str | None = None) -> dict:
        t0 = time.perf_counter()
        data = {"model": S["stt_model"], "language_code": language_code or "unknown"}
        if S.get("stt_mode") and S["stt_model"].endswith("v3"):
            data["mode"] = S["stt_mode"]
        r = self.http.post(S["stt_path"], headers={"api-subscription-key": self.key},
                           files={"file": (filename, audio, "audio/wav")}, data=data)
        j = self._check(r, "STT")
        ms = int((time.perf_counter() - t0) * 1000)
        log_latency("stt", ms)
        return {"transcript": j.get("transcript", ""), "language_code": j.get("language_code"), "ms": ms}

    def chat(self, messages: list[dict], temperature: float = 0.4, max_tokens: int = 160) -> dict:
        t0 = time.perf_counter()
        r = self.http.post(S["chat_path"],
                           headers={"Authorization": f"Bearer {self.key}", "api-subscription-key": self.key},
                           json={"model": S["llm_model"], "messages": messages,
                                 "temperature": temperature, "max_tokens": max_tokens})
        j = self._check(r, "LLM")
        text = j["choices"][0]["message"]["content"] or ""
        text = THINK.sub("", text).strip()
        ms = int((time.perf_counter() - t0) * 1000)
        log_latency("llm", ms)
        return {"text": text, "ms": ms}

    def tts(self, text: str, language_code: str, speaker: str, pace: float,
            temperature: float | None = None, model: str | None = None) -> dict:
        t0 = time.perf_counter()
        model = model or S["tts_model"]
        body = {"text": text[:2400], "language_code": language_code, "speaker": speaker,
                "model": model, "pace": pace, "speech_sample_rate": S["tts_sample_rate"]}
        if temperature is not None and model != "bulbul:v2":
            body["temperature"] = temperature        # v3 / v4-flash only
        r = self.http.post(S["tts_path"], headers={"api-subscription-key": self.key}, json=body)
        j = self._check(r, "TTS")
        audio = base64.b64decode(j["audios"][0])
        ms = int((time.perf_counter() - t0) * 1000)
        log_latency("tts", ms, f"{len(text)} chars")
        return {"wav": audio, "ms": ms}


class MockClient:
    """
    Offline stand-in, used automatically when there is no API key.
    STT can't really transcribe, so the UI's text box is used instead. LLM replies
    come from the engine's template fallback. TTS returns a short soft chime
    whose length scales with text length / pace, so the UI flow feels real.
    """

    mock = True

    def stt(self, audio: bytes, filename: str = "turn.wav", language_code: str | None = None) -> dict:
        return {"transcript": "", "language_code": None, "ms": 0}

    def chat(self, messages: list[dict], temperature: float = 0.4, max_tokens: int = 160) -> dict:
        raise SarvamError("mock mode: no LLM")      # engine falls back to templates

    def tts(self, text: str, language_code: str, speaker: str, pace: float,
            temperature: float | None = None, model: str | None = None) -> dict:
        secs = min(1.2, 0.15 + len(text) / 400 / pace)
        rate = 16000
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            frames = bytearray()
            for i in range(int(secs * rate)):
                env = min(1.0, i / 800, (secs * rate - i) / 800)
                v = 0.08 * env * math.sin(2 * math.pi * (523 if i < secs * rate / 2 else 659) * i / rate)
                frames += struct.pack("<h", int(v * 32767))
            w.writeframes(bytes(frames))
        return {"wav": buf.getvalue(), "ms": 0}


def get_client():
    return MockClient() if mock_mode() else SarvamClient(sarvam_key())


if __name__ == "__main__":
    # Smoke test: python -m persona_bot.sarvam.client
    c = get_client()
    print("mode:", "MOCK" if c.mock else "REAL")
    out = c.tts("नमस्ते जी, मैं IndiaMART से रिया बोल रही हूँ।", "hi-IN", CONFIG["voices"]["bulbul:v3"]["female"]["hi"], 1.0, 0.6)
    (OUTPUTS_DIR / "smoke_tts.wav").write_bytes(out["wav"])
    print(f"TTS ok: {len(out['wav'])} bytes in {out['ms']} ms → outputs/smoke_tts.wav (play it!)")
    if not c.mock:
        print("STT:", c.stt(out["wav"], language_code="hi-IN"))
        print("LLM:", c.chat([{"role": "user", "content": "Ek line mein namaste bolo."}]))
