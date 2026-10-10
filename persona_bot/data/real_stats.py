"""
real_stats.py: aggregate meeting-rate statistics from the real PS07 bot calls → evidence/real_summary.md

    python -m persona_bot.data.real_stats

Privacy: output has aggregates only (counts, rates, intervals). Any cell with n < MIN_N is suppressed.
No IDs, names or text are read into the report. Uses a parquet cache if one exists at data/raw/cache/*.parquet.

Method notes (also written into the report):
  * rate = meeting_fixed == 1 over answered bot calls; 95% intervals are Wilson (single rate) or normal-approx (difference).
  * "personalis" ran only in Sep 2026, so the fair control is other versions in the SAME month, not all months.
  * Mix-adjusted difference = direct standardisation on business_type × turnover (weights = personalis mix).
  * Seller-clustered bootstrap gives an interval that respects repeat calls to the same seller.
"""
from __future__ import annotations

import glob
import math

import numpy as np
import pandas as pd

from persona_bot.config import EVIDENCE_DIR, RAW_DIR
from persona_bot.data.real_adapter import NATURE, TURNOVER

FK = "fk_glusr_usr_id"
MIN_N = 30
TRIAL = "personalis"
Z = 1.96
DUR_BANDS = [(0, 10, "0-10s"), (11, 30, "11-30s"), (31, 60, "31-60s"), (61, 120, "61-120s"), (121, 10**6, "121s+")]


# ───────────────────────── loading ───────────────────────────────────────────
def load() -> pd.DataFrame:
    cache = RAW_DIR / "cache" / "bot_calls_joined.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    cols = ["attempt_id", FK, "lead_bot_version", "redis_bucket", "call_start_time", "lead_call_duration", "meeting_fixed"]
    calls = pd.concat([pd.read_csv(f, usecols=cols, dtype={FK: str, "attempt_id": str})
                       for f in sorted(glob.glob(str(RAW_DIR / "ps07_bot_calls_2026-*.csv")))], ignore_index=True)
    scols = [FK, "nature_of_business", "annual_turnover"]
    sellers = pd.concat([pd.read_csv(f, usecols=scols, dtype={FK: str}, low_memory=False)
                         for f in sorted(glob.glob(str(RAW_DIR / "ps07_seller_files_part*.csv")))], ignore_index=True)
    sellers = sellers.drop_duplicates(FK)
    sellers["business_type"] = sellers.nature_of_business.map(lambda x: NATURE.get(x, (None,))[0])
    sellers["turnover"] = sellers.annual_turnover.map(TURNOVER)
    df = calls.merge(sellers[[FK, "business_type", "turnover"]], on=FK, how="left")
    df["meeting"] = (df.meeting_fixed == 1).astype(int)
    df["month"] = df.call_start_time.str[:7]
    df["dur_band"] = pd.cut(df.lead_call_duration, [-1, 10, 30, 60, 120, 10**7],
                            labels=[b[2] for b in DUR_BANDS]).astype("object")
    return df


# ───────────────────────── stats helpers ─────────────────────────────────────
def wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return c - h, c + h


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def pts(x: float) -> str:
    return f"{100 * x:+.1f}"


def rate_row(g: pd.DataFrame) -> tuple[int, int] | None:
    return (int(g.meeting.sum()), len(g)) if len(g) >= MIN_N else None


def diff_ci(k1, n1, k0, n0) -> tuple[float, float, float]:
    p1, p0 = k1 / n1, k0 / n0
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    d = p1 - p0
    return d, d - Z * se, d + Z * se


def rate_table(df: pd.DataFrame, by: str, order: list[str] | None = None) -> str:
    rows = ["| " + by + " | n | meeting rate | 95% CI |", "|---|---:|---:|---|"]
    keys = order or sorted(df[by].dropna().unique())
    for k in keys:
        r = rate_row(df[df[by] == k])
        if r is None:
            continue
        lo, hi = wilson(*r)
        rows.append(f"| {k} | {r[1]:,} | {pct(r[0] / r[1])} | {pct(lo)} to {pct(hi)} |")
    return "\n".join(rows)


def compare(a: pd.DataFrame, b: pd.DataFrame) -> tuple[int, int, int, int] | None:
    if len(a) < MIN_N or len(b) < MIN_N:
        return None
    return int(a.meeting.sum()), len(a), int(b.meeting.sum()), len(b)


def cmp_table(a: pd.DataFrame, b: pd.DataFrame, by: str, order: list[str]) -> str:
    rows = [f"| {by} | n trial | trial rate | n control | control rate | diff (pts) | 95% CI (pts) |", "|---|---:|---:|---:|---:|---:|---|"]
    for k in order:
        c = compare(a[a[by] == k], b[b[by] == k])
        if c is None:
            continue
        d, lo, hi = diff_ci(*c)
        rows.append(f"| {k} | {c[1]:,} | {pct(c[0] / c[1])} | {c[3]:,} | {pct(c[2] / c[3])} | {pts(d)} | {pts(lo)} to {pts(hi)} |")
    return "\n".join(rows)


def adjusted_diff(a: pd.DataFrame, b: pd.DataFrame, keys: list[str]) -> tuple[float, float, float, float] | None:
    """Direct standardisation on `keys`, weights = trial mix. Returns diff, lo, hi, share of trial calls covered."""
    ga = a.dropna(subset=keys).groupby(keys).meeting.agg(["sum", "size"])
    gb = b.dropna(subset=keys).groupby(keys).meeting.agg(["sum", "size"])
    j = ga.join(gb, lsuffix="1", rsuffix="0", how="inner")
    j = j[(j.size1 >= 5) & (j.size0 >= 5)]
    if j.empty:
        return None
    w = j.size1 / j.size1.sum()
    p1, p0 = j.sum1 / j.size1, j.sum0 / j.size0
    d = float((w * (p1 - p0)).sum())
    se = math.sqrt(float((w ** 2 * (p1 * (1 - p1) / j.size1 + p0 * (1 - p0) / j.size0)).sum()))
    return d, d - Z * se, d + Z * se, float(j.size1.sum() / ga["size"].sum())


def cluster_boot(a: pd.DataFrame, b: pd.DataFrame, iters: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Resample SELLERS (not calls) to get an interval that respects repeat calls to one seller."""
    sa = a.groupby(FK).meeting.agg(["sum", "size"])
    sb = b.groupby(FK).meeting.agg(["sum", "size"])
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(iters):
        ia = rng.integers(0, len(sa), len(sa))
        ib = rng.integers(0, len(sb), len(sb))
        out.append(sa["sum"].values[ia].sum() / sa["size"].values[ia].sum() - sb["sum"].values[ib].sum() / sb["size"].values[ib].sum())
    out = np.array(out)
    return float(a.meeting.mean() - b.meeting.mean()), float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def mix_table(a: pd.DataFrame, b: pd.DataFrame, by: str, la: str, lb: str) -> tuple[str, float]:
    ka = a[by].fillna("unknown").value_counts(normalize=True)
    kb = b[by].fillna("unknown").value_counts(normalize=True)
    idx = sorted(set(ka.index) | set(kb.index))
    rows = [f"| {by} | {la} | {lb} | gap (pts) |", "|---|---:|---:|---:|"]
    tv = 0.0
    for k in idx:
        pa, pb = float(ka.get(k, 0)), float(kb.get(k, 0))
        tv += abs(pa - pb) / 2
        if pa >= 0.01 or pb >= 0.01:
            rows.append(f"| {k} | {pct(pa)} | {pct(pb)} | {pts(pa - pb)} |")
    return "\n".join(rows), tv


# ───────────────────────── report ────────────────────────────────────────────
def build() -> tuple[str, list[tuple[float, str]]]:
    df = load()
    seg = df.dropna(subset=["business_type", "turnover"])
    n_calls, n_sellers, base = len(df), df[FK].nunique(), df.meeting.mean()
    out: list[str] = []
    cand: list[tuple[float, str]] = []        # (strength, sentence) for the slide findings

    out += ["# Real-data summary (PS07 bot calls, Apr–Sep 2026)", "",
            "Aggregates only; cells with n < 30 are suppressed. Rate = `meeting_fixed == 1` per answered bot call. "
            "`business_type` = our mapped `nature_of_business`; turnover bands as in the Seller model.", "",
            "## a) Totals", "",
            f"- Answered bot calls: **{n_calls:,}**",
            f"- Distinct sellers called: **{n_sellers:,}** ({df[FK].isna().sum()} calls without a seller id)",
            f"- Overall meeting-fixed rate: **{pct(base)}** ({int(df.meeting.sum()):,} calls)",
            f"- Calls with a seller-file match (business type and turnover known): {len(seg):,} ({pct(len(seg) / n_calls)})", ""]

    # b) bot version
    out += ["## b) Meeting rate by `lead_bot_version`", "", rate_table(df, "lead_bot_version",
            list(df.lead_bot_version.value_counts().index)), ""]

    trial = df[df.lead_bot_version == TRIAL]
    sep = df[df.month == "2026-09"]
    ctrl_all = df[df.lead_bot_version != TRIAL]
    ctrl_sep = sep[sep.lead_bot_version != TRIAL]
    ctrl_sep_main = sep[sep.lead_bot_version == "main_vani"]
    months = sorted(trial.month.unique())
    out += [f"### `{TRIAL}` trial vs the others", "",
            f"The trial has **{len(trial):,}** calls from **{trial[FK].nunique():,}** sellers, all in {', '.join(months)}. "
            "The dictionary says these are the *recorded* calls of the trial, so the trial may have been larger and this "
            "subset may not be a random sample.", ""]
    out += ["| Control group | n control | control rate | trial rate | diff (pts) | 95% CI (pts, calls) | 95% CI (pts, seller-clustered) |",
            "|---|---:|---:|---:|---:|---|---|"]
    heads = {}
    for name, c in [("All other versions, all months", ctrl_all), ("Other versions, Sep only (same month)", ctrl_sep),
                    ("`main_vani`, Sep only", ctrl_sep_main)]:
        d, lo, hi = diff_ci(int(trial.meeting.sum()), len(trial), int(c.meeting.sum()), len(c))
        cd, clo, chi = cluster_boot(trial, c)
        heads[name] = (d, lo, hi, clo, chi)
        out.append(f"| {name} | {len(c):,} | {pct(c.meeting.mean())} | {pct(trial.meeting.mean())} | {pts(d)} | "
                   f"{pts(lo)} to {pts(hi)} | {pts(clo)} to {pts(chi)} |")
    out.append("")

    out += ["### Is the segment mix different? (trial vs Sep controls)", ""]
    tvs = {}
    for by, label in [("business_type", "business type"), ("turnover", "turnover band"), ("redis_bucket", "lead type (redis_bucket)")]:
        t, tv = mix_table(trial, ctrl_sep, by, "trial", "Sep others")
        tvs[label] = tv
        out += [t, "", f"Total-variation distance for {label}: **{tv:.3f}** (0 = identical mix, 1 = disjoint).", ""]
    mixdiff = max(tvs.values()) > 0.08
    out += [("**The mix differs noticeably**, so raw differences can reflect who was called, not the bot. "
             "Mix-adjusted differences below are the safer numbers." if mixdiff else
             "The mix is close, so raw and adjusted differences should agree."), ""]

    out += ["### Mix-adjusted difference (standardised to the trial's mix)", "",
            "| Control | Adjusted on | diff (pts) | 95% CI (pts) | trial calls covered |", "|---|---|---:|---|---:|"]
    adj_main = None
    for name, c in [("Other versions, Sep", ctrl_sep), ("`main_vani`, Sep", ctrl_sep_main)]:
        for keys, kl in [(["business_type", "turnover"], "business type × turnover"), (["redis_bucket"], "lead type")]:
            r = adjusted_diff(trial, c, keys)
            if r:
                out.append(f"| {name} | {kl} | {pts(r[0])} | {pts(r[1])} to {pts(r[2])} | {pct(r[3])} |")
                if name.startswith("Other") and keys[0] == "business_type":
                    adj_main = r
    out.append("")

    ts, cs = trial.dropna(subset=["business_type", "turnover"]), ctrl_sep.dropna(subset=["business_type", "turnover"])
    out += ["### Trial vs Sep controls, by business type", "", cmp_table(ts, cs, "business_type", sorted(ts.business_type.unique())), "",
            "### Trial vs Sep controls, by turnover band", "", cmp_table(ts, cs, "turnover", list(dict.fromkeys(TURNOVER.values()))), ""]

    # all versions by month, to expose a pure time trend
    out += ["### Control check: meeting rate by month (all versions)", "", rate_table(df, "month"), ""]

    # c) segments
    out += ["## c) Meeting rate by segment", "", "### Business type", "", rate_table(seg, "business_type"), "",
            "### Turnover band", "", rate_table(seg, "turnover", list(dict.fromkeys(TURNOVER.values()))), "",
            "### Call-duration band", "", rate_table(df.dropna(subset=["dur_band"]), "dur_band", [b[2] for b in DUR_BANDS]), "",
            "> **Caution:** duration is partly an *outcome* of the call (a seller who agrees to a meeting talks longer), "
            "so the duration gradient is not evidence that long calls cause meetings.", ""]

    out += ["## Caveats", "",
            "- Calls to the same seller are not independent; the seller-clustered intervals are the honest ones.",
            "- Version assignment was not randomised that we know of; month and lead type differ across versions.",
            "- Results describe answered calls only (no-answer calls are not in this file).", ""]

    # Slide findings, in a fixed order (trial result, business type, turnover). Duration is deliberately excluded:
    # it is partly an outcome of the call. The version spread is excluded: versions ran in different months.
    d, lo, hi, clo, chi = heads["Other versions, Sep only (same month)"]
    adj = f"; {pts(adj_main[0])} points after adjusting for business type and turnover mix" if adj_main else ""
    sig = clo > 0 or chi < 0
    cand.append((3, f"The personalised-script bot fixed meetings on {pct(trial.meeting.mean())} of its {len(trial):,} calls vs "
                 f"{pct(ctrl_sep.meeting.mean())} for other September bots ({pts(d)} points, 95% interval {pts(clo)} to {pts(chi)}{adj})"
                 + ("." if sig else ", but the interval includes zero, so it is not yet proven.")))
    for by, lab, w in [("business_type", "business type", 2), ("turnover", "seller size (turnover)", 1)]:
        rr = []
        for k, g in seg.groupby(by):
            r = rate_row(g)
            if r:
                rr.append((r[0] / r[1], k))
        rr.sort()
        cand.append((w, f"By {lab}, the bot's meeting rate runs from {pct(rr[0][0])} ({rr[0][1]}) to {pct(rr[-1][0])} ({rr[-1][1]}), among calls with a known seller profile."))
    return "\n".join(out), cand


def main() -> None:
    md, cand = build()
    cand.sort(key=lambda x: -x[0])
    top = [s for _, s in cand[:3]]
    md += "\n## Three findings for a slide\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(top, 1)) + "\n"
    path = EVIDENCE_DIR / "real_summary.md"
    path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n→ wrote {path}")


if __name__ == "__main__":
    main()
