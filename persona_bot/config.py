"""
config.py: loads config.yaml and .env once, and exposes them everywhere.

Why a module instead of reading YAML in each file?
  * One place to find every tunable value (pace, thresholds, speakers…).
  * Tests can monkey-patch CONFIG without touching disk.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

try:  # python-dotenv is optional; if present, .env is loaded into os.environ
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

# Repo root = the folder that contains config.yaml (one level above this package)
ROOT = Path(__file__).resolve().parent.parent

if load_dotenv:
    load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml", encoding="utf-8") as fh:
    CONFIG: dict = yaml.safe_load(fh)

# Well-known folders, so no module hard-codes paths
DATA_DIR = ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"        # seller files (synthetic or anonymised)
RAW_DIR = DATA_DIR / "raw"                # real data – gitignored, never leaves the laptop
EVIDENCE_DIR = ROOT / "evidence"
OUTPUTS_DIR = ROOT / "outputs"
PERSONAS_DIR = OUTPUTS_DIR / "personas"
SWITCH_LOGS_DIR = OUTPUTS_DIR / "switch_logs"
CALLS_DIR = OUTPUTS_DIR / "calls"

for _d in (SAMPLES_DIR, RAW_DIR, EVIDENCE_DIR, PERSONAS_DIR, SWITCH_LOGS_DIR, CALLS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def sarvam_key() -> str | None:
    """The Sarvam API key, or None → the app runs in MOCK mode (no network calls)."""
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    return key or None


def mock_mode() -> bool:
    """MOCK=1 forces mock mode even when a key is present (handy for offline tests)."""
    return os.environ.get("MOCK", "") == "1" or sarvam_key() is None
