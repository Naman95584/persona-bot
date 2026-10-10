"""
miner.py: turns past calls into evidence: "for sellers like X, bot behaviour Y
fixed meetings Z% of the time (n calls, 95% interval)".

This is the backbone of the "Support from past-call evidence" metric, and of the
Business Impact slide.

Method (simple on purpose, so it's defensible in jury Q&A):
  1. Extract bot traits from every transcript (traits.py).
  2. Slice calls by seller segment (one or two seller attributes).
  3. Within each slice, compare the success rate of each trait value.
  4. Report rates with n and a Wilson 95% interval. Cells with n < min_n are
     kept in the file, but never used as evidence.

Why Wilson and not a plain ±? With rates near 0 or small n, the normal
approximation gives nonsense like negative rates. Wilson stays within 0–1 and is
standard for proportions.

Guarding against false findings: we test hundreds of (segment × trait) slices,
so some will look "significant" by pure chance. Two defences:
  * Shrinkage: each slice's rate is pulled toward the dataset-wide rate for
    that trait value, in proportion to how little data the slice has:
        shrunk = (wins + K × prior_rate) / (n + K),  K = shrink_k (config)
    A slice with 30 calls moves halfway to the prior; one with 600 barely moves.
  * Two-proportion z-test (best value vs. the rest of the segment), then
    Benjamini–Hochberg false-discovery control across ALL tests: we accept a
    finding as "strong" only if, at a 10% false-discovery rate, it survives.
    Plain English: of everything we label "strong", at most ~1 in 10 is
    expected to be a fluke.
  * Parent consistency + seller-level contradiction check (see below).

Limitations to say out loud: this is observational data. If historical bot
behaviour was not randomised, a "best" trait may be confounded. Mention it, and
pitch A/B testing (Problem 5) as the follow-up.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from persona_bot.config import CONFIG, DATA_DIR, EVIDENCE_DIR
from persona_bot.evidence import traits as T

SIZE = {"0-40L": "small", "40L-1.5Cr": "small", "1.5-5Cr": "mid", "5-25Cr": "large", "25Cr+": "large"}

# Seller segment definitions. Order = most specific first (the generator prefers those).
SEGMENTS: list[tuple[str, ...]] = [
    ("business_type", "size"),
    ("seller_language", "size"),
    ("seller_language",),
    ("business_type",),
    ("top_objection",),
    ("size",),
    (),                      # "all" – the whole dataset; acts as the prior for shrinkage
]
TRAITS = ["bot_language", "formality", "verbosity", "acknowledged_objection", "pace_band", "voice_gender"]


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def two_prop_pvalue(w1: int, n1: int, w2: int, n2: int) -> float:
    """One-sided p-value that rate1 > rate2 (pooled two-proportion z-test)."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-9
    z = (w1 / n1 - w2 / n2) / se
    return 0.5 * math.erfc(z / math.sqrt(2))


def segment_key(seg: tuple[str, ...], row: dict) -> str:
    """e.g. 'business_type=trader&size=mid'"""
    return "&".join(f"{f}={row[f]}" for f in seg) or "all"


def load_calls(path: Path) -> list[dict]:
    success = set(CONFIG["evidence"]["success_outcomes"])
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pace = float(r["bot_pace"]) if r.get("bot_pace") else None
            r.update(T.extract(r["bot_transcript"], pace, r.get("bot_voice_gender")))
            r["size"] = SIZE.get(r["turnover_band"], "unknown")
            r["won"] = r["outcome"] in success
            rows.append(r)
    return rows


def mine(rows: list[dict]) -> dict:
    min_n = CONFIG["evidence"]["min_n"]
    min_lift = CONFIG["evidence"]["min_lift_pts"] / 100
    # counts[segment_key][trait][value] = [wins, n]
    counts: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    seg_base: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        for seg in SEGMENTS:
            k = segment_key(seg, r)
            seg_base[k][0] += r["won"]
            seg_base[k][1] += 1
            for t in TRAITS:
                c = counts[k][t][r[t]]
                c[0] += r["won"]
                c[1] += 1

    k_shrink = CONFIG["evidence"].get("shrink_k", 30)
    cells: dict = {}
    findings = []
    prior = counts["all"]
    for k, by_trait in counts.items():
        cells[k] = {"_baseline": _stat(*seg_base[k])}
        for t, by_val in by_trait.items():
            cells[k][t] = {}
            for v, (w, n) in by_val.items():
                pw, pn = prior[t][v]
                st = _stat(w, n)
                st["shrunk"] = round((w + k_shrink * pw / pn) / (n + k_shrink), 3) if pn else st["rate"]
                cells[k][t][v] = st
            # Best value vs. the rest of the segment. Only count it if both sides have enough data
            usable = {v: s for v, s in cells[k][t].items() if s["n"] >= min_n and v != "unknown"}
            if len(usable) < 2:
                continue
            best_v, best = max(usable.items(), key=lambda kv: kv[1]["shrunk"])
            rest_w = sum(by_val[v][0] for v in usable if v != best_v)
            rest_n = sum(by_val[v][1] for v in usable if v != best_v)
            rest_rate = rest_w / rest_n
            lift = best["shrunk"] - rest_rate
            pval = two_prop_pvalue(best["wins"], best["n"], rest_w, rest_n)
            findings.append({
                "segment": k, "trait": t, "best": best_v,
                "rate": best["rate"], "shrunk": best["shrunk"], "n": best["n"],
                "rest_rate": round(rest_rate, 3), "lift_pts": round(lift * 100, 1),
                "p_value": pval,
                "strength": "weak" if lift >= min_lift else "none",   # upgraded to "strong" by BH below
            })
    # Benjamini–Hochberg: sort p-values; the i-th smallest passes if p ≤ (i/m)·q.
    # Every test up to the largest passing rank is accepted.
    q = CONFIG["evidence"].get("fdr", 0.10)
    ranked = sorted(findings, key=lambda f: f["p_value"])
    m = len(ranked)
    cutoff = 0
    for i, f in enumerate(ranked, 1):
        if f["p_value"] <= i / m * q:
            cutoff = i
    for f in ranked[:cutoff]:
        if f["lift_pts"] >= CONFIG["evidence"]["min_lift_pts"]:
            f["strength"] = "strong"
    for f in findings:
        f["p_value"] = float(f"{f['p_value']:.2g}")

    # Consistency check: a two-attribute finding (e.g. retailer & mid-size) only stays
    # "strong" if, in EACH parent segment (all retailers; all mid-size sellers), the same
    # trait value is at least as good as that parent's average. Flukes in small
    # sub-segments usually fail this, while real effects pass.
    for f in findings:
        parts = f["segment"].split("&")
        if f["strength"] != "strong" or len(parts) < 2:
            continue
        for parent in parts:
            pc = cells.get(parent, {})
            pv = pc.get(f["trait"], {}).get(f["best"])
            if not pv or pv["rate"] < pc["_baseline"]["rate"]:
                f["strength"] = "weak"
                f["note"] = f"inconsistent with parent segment {parent}"
                break
    findings.sort(key=lambda f: (f["strength"] != "strong", -f["lift_pts"]))
    total_w = sum(r["won"] for r in rows)
    return {
        "meta": {"n_calls": len(rows), "baseline": _stat(total_w, len(rows)),
                 "success_outcomes": CONFIG["evidence"]["success_outcomes"], "min_n": min_n,
                 "segments": ["&".join(s) for s in SEGMENTS], "traits": TRAITS},
        "findings": findings,
        "cells": cells,
    }


def _stat(w: int, n: int) -> dict:
    lo, hi = wilson(w, n)
    return {"wins": w, "n": n, "rate": round(w / n, 3) if n else 0.0,
            "ci_low": round(lo, 3), "ci_high": round(hi, 3)}


def write_summary(ev: dict, path: Path) -> None:
    """A human-readable summary for the approach note / demo slide."""
    m = ev["meta"]
    lines = [
        "# Evidence summary (auto-generated by persona_bot.evidence.miner)", "",
        f"Calls analysed: **{m['n_calls']}** · overall meeting-fixed rate: **{m['baseline']['rate']:.1%}**", "",
        "## Strongest findings (best bot behaviour vs. the rest, within a seller segment)", "",
        "Rates are raw; lift uses the shrunk rate (see miner.py docstring).", "",
        "| Seller segment | Trait | Best | Rate | n | Rest | Lift (pts) | Strength |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in [f for f in ev["findings"] if f["strength"] == "strong"][:15]:
        lines.append(f"| {f['segment']} | {f['trait']} | {f['best']} | {f['rate']:.1%} | {f['n']} | "
                     f"{f['rest_rate']:.1%} | +{f['lift_pts']} | {f['strength']} |")
    none = [f for f in ev["findings"] if f["trait"] == "voice_gender" and f["strength"] == "none"]
    lines += ["", f"## No evidence\n\nVoice gender showed no meaningful effect in {len(none)} segments, "
              "so the generator picks gender by rule (see reason in each persona), not by data."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(calls_path: Path | None = None) -> dict:
    calls_path = calls_path or DATA_DIR / "past_calls.csv"
    rows = load_calls(calls_path)
    ev = mine(rows)
    (EVIDENCE_DIR / "persona_effects.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    write_summary(ev, EVIDENCE_DIR / "summary.md")
    return ev


# ─────────────── Query API used by the persona generator ─────────────────────
class Evidence:
    """Wraps persona_effects.json and answers: 'for this seller, which value of trait X is best?'"""

    def __init__(self, data: dict | None = None):
        if data is None:
            p = EVIDENCE_DIR / "persona_effects.json"
            data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"cells": {}}
        self.data = data
        self.min_n = CONFIG["evidence"]["min_n"]
        self.min_lift = CONFIG["evidence"]["min_lift_pts"] / 100

    def best(self, seller_attrs: dict, trait: str, allowed: list[str] | None = None,
             level: str = "all") -> dict | None:
        """
        Walks seller segments from most to least specific and returns the first
        STRONG finding for this trait (see mine()), or None → the caller uses a rule.
        Using only "strong" findings means every evidence-based persona choice has
        passed shrinkage, the false-discovery control and the parent-consistency check.

        level: "specific" → only 2-attribute segments (e.g. trader & mid-size)
               "broad"    → only 1-attribute segments (e.g. all traders)
               "all"      → both, most specific first
        """
        index = self._index()
        tried: list[str] = []          # more specific segments already visited for this seller
        for seg in SEGMENTS:
            if not seg or not all(f in seller_attrs for f in seg):
                continue
            k = segment_key(seg, seller_attrs)
            if (level == "specific" and len(seg) < 2) or (level == "broad" and len(seg) > 1):
                tried.append(k)
                continue
            f = index.get((k, trait))
            if f and (allowed is None or f["best"] in allowed) and not self._contradicted(tried, trait, f["best"]):
                return {"value": f["best"], "segment": f["segment"], "rate": f["rate"], "n": f["n"],
                        "rest_rate": f["rest_rate"], "lift_pts": f["lift_pts"],
                        "key": f"evidence:{f['segment']}|{trait}={f['best']} → {f['rate']:.0%} meetings "
                               f"(n={f['n']}) vs {f['rest_rate']:.0%} for other choices"}
            tried.append(k)
        return None

    def _contradicted(self, specific_keys: list[str], trait: str, value: str) -> bool:
        """
        Simpson's-paradox guard. "Small sellers like crisp" may be driven by small
        TRADERS. If this seller's own, more specific segment (e.g. small
        MANUFACTURERS) has enough data and that value does worse than the segment's
        average there, the broad finding does not apply to this seller.
        """
        for k in specific_keys:
            cell = self.data.get("cells", {}).get(k, {})
            st = cell.get(trait, {}).get(value)
            if st and st["n"] >= self.min_n and st["rate"] < cell["_baseline"]["rate"]:
                return True
        return False

    def _index(self) -> dict:
        if not hasattr(self, "_idx"):
            self._idx = {(f["segment"], f["trait"]): f
                         for f in self.data.get("findings", []) if f["strength"] == "strong"}
        return self._idx


if __name__ == "__main__":
    ev = run()
    print(f"mined {ev['meta']['n_calls']} calls, baseline {ev['meta']['baseline']['rate']:.1%}")
    for f in ev["findings"][:12]:
        print(f"  [{f['strength']:6}] {f['segment']:40} {f['trait']:22} best={f['best']:12} "
              f"{f['rate']:.0%} vs {f['rest_rate']:.0%}  (+{f['lift_pts']} pts, n={f['n']})")
