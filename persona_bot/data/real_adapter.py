"""
real_adapter.py: real IndiaMART PS07 data (data/raw/) → 10 anonymised demo sellers (data/samples/seller_R001..R010.json).

    python -m persona_bot.data.real_adapter

Privacy: the output files carry NO real names, phone numbers, GLIDs or summaries. Display names are generic
("Steel Trader, Punjab"). The R-id → real-id map is written to data/raw/real_id_map.json (gitignored).
Nothing printed by this script contains free text; only counts, categories and R-ids.

Groups (3 busy, 3 new/confused, 3 frustrated or language-mixing, 1 typical) are picked by transparent scores
over seller-file flags and by running our own signal detector over the seller side of call_turns.
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter

import pandas as pd

from persona_bot.config import RAW_DIR, SAMPLES_DIR
from persona_bot.live.signal_detector import detect, spoken_language
from persona_bot.models import Engagement, History, PastCall, Seller

FK = "fk_glusr_usr_id"
WRONG_CONTACT = "Wrong Contact / Business Not Applicable"
NOT_READY = "Not Ready / Needs Time / Early-Stage Seller"

NATURE = {  # nature_of_business → (our business_type, role word for the generic display name)
    "Manufacturer": ("manufacturer", "Manufacturer"),
    "Trader - Retailer": ("retailer", "Retailer"), "Retailer": ("retailer", "Retailer"),
    "Trader - Wholesaler/Distributor": ("distributor", "Distributor"),
    "Wholesaler/Distributor": ("distributor", "Distributor"),
    "Service Provider and Others": ("service_provider", "Service Provider"),
}
TURNOVER = {
    "0 - 40 L": "0-40L", "40 L - 1.5 Cr": "40L-1.5Cr", "1.5 - 5 Cr": "1.5-5Cr", "5 - 25 Cr": "5-25Cr",
    "25 - 100 Cr": "25Cr+", "100 - 500 Cr": "25Cr+", "> 500 Cr": "25Cr+",
}
OBJECTION = {
    "Seller Unavailability & Scheduling Constraints": "busy",
    "Callback / Deferred Engagement (Neutral)": "busy",
    "Explicit Disinterest / Refusal": "not_needed",
    "Wrong Contact / Business Not Applicable": "not_needed",
    "Product / Service / Business Mismatch": "not_needed",
    "Existing Engagement / Past Experience": "already_using_other",
    "Information / Trust / Privacy Concerns": "trust",
    # Not Ready → "none" (it drives the new/confused signal via history); call-quality / handling / no-response /
    # Others are bot or process problems, not seller objections → "none"
}
OUTCOME = {"Not Interested": "not_interested", "Call Later / Busy": "callback", "General (talked)": "general"}
CONFUSION_Q = ("Clarification", "Purpose Reason")


# ───────────────────────── parsing helpers ───────────────────────────────────
def parse_counted(cell) -> list[tuple[str, int]]:
    """'Cat A (2); Cat B' → [('Cat A', 2), ('Cat B', 1)] (the file uses ';' between items)."""
    if not isinstance(cell, str):
        return []
    out = []
    for part in cell.split(";"):
        m = re.match(r"\s*(.*?)\s*(?:\((\d+)\))?\s*$", part)
        if m and m.group(1):
            out.append((m.group(1), int(m.group(2) or 1)))
    return sorted(out, key=lambda x: -x[1])


def map_objections(row) -> tuple[list[str], list[str]]:
    cats = parse_counted(row.past_objections)
    objs: list[str] = []
    for c, _ in cats:
        o = OBJECTION.get(c)
        if o and o not in objs:
            objs.append(o)
    if any(c == "budget_issue_denial" for c, _ in parse_counted(row.past_dispositions_detailed)) and "price" not in objs:
        objs.append("price")
    return objs, [c for c, _ in cats]


def dropped_count(row) -> int:
    return sum(n for c, n in parse_counted(row.past_dispositions_detailed) if c == "call_dropped")


# ───────────────────────── loading ───────────────────────────────────────────
def load_sellers() -> pd.DataFrame:
    cols = [FK, "seller_city", "seller_state", "nature_of_business", "annual_turnover", "gst_registration_year",
            "top_category_1", "top_category_2", "top_category_3", "eng_activity_30d", "eng_enq_received_90d",
            "eng_enq_replies_90d", "eng_cqs", "bot_attempts", "bot_answered", "calls_meeting_fixed",
            "calls_not_interested", "calls_call_later", "avg_answered_call_sec", "past_objections",
            "past_questions_asked", "past_dispositions_detailed", "asked_if_talking_to_bot", "showed_frustration",
            "do_not_call_requested"]
    files = sorted(glob.glob(str(RAW_DIR / "ps07_seller_files_part*.csv")))
    df = pd.concat([pd.read_csv(f, usecols=cols, dtype={FK: str}, low_memory=False) for f in files], ignore_index=True)
    df = df[df.do_not_call_requested.fillna(0) != 1]                      # never call these sellers
    df = df[df.nature_of_business.isin(NATURE) & df.annual_turnover.isin(TURNOVER)]
    df = df[df.top_category_1.notna() & df.seller_state.notna() & df.seller_city.notna()]
    df = df[df.bot_answered.fillna(0) >= 2]
    return df.drop_duplicates(FK).reset_index(drop=True)


def load_calls(fks: set[str]) -> pd.DataFrame:
    cols = ["attempt_id", FK, "call_start_time", "lead_call_duration", "disposition_label", "meeting_fixed"]
    files = sorted(glob.glob(str(RAW_DIR / "ps07_bot_calls_2026-*.csv")))
    df = pd.concat([pd.read_csv(f, usecols=cols, dtype={FK: str, "attempt_id": str}) for f in files], ignore_index=True)
    return df[df[FK].isin(fks)].sort_values("call_start_time").reset_index(drop=True)


def transcript_stats(fks: set[str]) -> pd.DataFrame:
    """Per call: seller language, avg words per seller turn, and how many turns our detector flags."""
    t = pd.read_csv(RAW_DIR / "ps07_call_turns.csv", usecols=["attempt_id", FK, "turn_no", "speaker", "text"],
                    dtype={FK: str, "attempt_id": str})
    t = t[(t.speaker == "seller") & t[FK].isin(fks) & t.text.notna()].sort_values(["attempt_id", "turn_no"])
    rows = []
    for aid, g in t.groupby("attempt_id", sort=False):
        texts = [str(x) for x in g.text]
        sig = Counter()
        for i, x in enumerate(texts):
            for s in detect(x, bot_language="hi", history=texts[:i]):
                if s.name in ("frustration", "confusion", "rush") and s.confidence >= 0.5:
                    sig[s.name] += 1
        words = [len(x.split()) for x in texts]
        rows.append({"attempt_id": aid, FK: g[FK].iloc[0], "n_turns": len(texts),
                     "avg_words": sum(words) / len(words), "lang": spoken_language(" ".join(texts)),
                     "frustration": sig["frustration"], "confusion": sig["confusion"], "rush": sig["rush"]})
    return pd.DataFrame(rows)


# ───────────────────────── per-seller features ───────────────────────────────
def features(sellers: pd.DataFrame, calls: pd.DataFrame, ts: pd.DataFrame) -> pd.DataFrame:
    ncalls = calls.groupby(FK).size().rename("n_calls")
    agg = ts.groupby(FK).agg(t_calls=("attempt_id", "size"), t_turns=("n_turns", "sum"),
                             t_words=("avg_words", "mean"), t_frust=("frustration", "sum"),
                             t_conf=("confusion", "sum"), t_rush=("rush", "sum"),
                             langs=("lang", lambda x: sorted(set(x))))
    df = sellers.merge(ncalls, left_on=FK, right_index=True).merge(agg, left_on=FK, right_index=True)
    df = df[(df.n_calls >= 2) & (df.t_turns >= 4)].copy()
    om = df.apply(map_objections, axis=1)
    df["objs"], df["obj_cats"] = om.str[0], om.str[1]
    df = df[~df.obj_cats.apply(lambda c: len(c) > 0 and set(c) == {WRONG_CONTACT})]   # bad demo cases
    df["dropped"] = df.apply(dropped_count, axis=1)
    df["asked_bot"] = df.asked_if_talking_to_bot.fillna(0) == 1
    df["frustrated"] = df.showed_frustration.fillna(0) == 1
    df["not_ready"] = df.obj_cats.apply(lambda c: NOT_READY in c)
    df["conf_q"] = df.past_questions_asked.apply(lambda c: sum(n for k, n in parse_counted(c) if k in CONFUSION_Q))
    df["callback_share"] = df.calls_call_later.fillna(0) / df.bot_answered.clip(lower=1)
    df["mixed"] = df.langs.apply(lambda l: len(l) > 1)
    df["has_eng"] = df.eng_enq_received_90d.notna()
    df["busy_s"] = ((df.objs.apply(lambda o: "busy" in o)) * 3 + df.callback_share * 2 + (df.t_words < 6) * 1.5
                    + df.t_rush.clip(upper=3) * 0.5 + df.has_eng * 1.0)
    df["conf_s"] = (df.not_ready * 4 + df.eng_activity_30d.between(1, 4) * 2 + df.conf_q.clip(upper=3) * 1.0 + df.t_conf.clip(upper=3) * 1.0
                    + (df.eng_cqs.fillna(50) < 20) * 0.5 + df.has_eng * 1.0)
    df["frus_s"] = (df.frustrated * 5 + df.t_frust.clip(upper=3) * 1.0 + df.mixed * 2 + df.dropped.clip(upper=3) * 0.7
                    + df.asked_bot * 0.5 + df.has_eng * 1.0)
    return df


def pick(df: pd.DataFrame, score: str, n: int, chosen: list[dict], used: set[str], group: str,
         qualify=None, check=None) -> None:
    """Greedy pick with a diversity penalty. `check(row)` must hold for the generated persona, so a group
    only contains sellers whose persona really shows that group's behaviour."""
    pool = df[~df[FK].isin(used)]
    if qualify is not None:
        pool = pool[qualify(pool)]
    while sum(c["group"] == group for c in chosen) < n:
        if pool.empty:
            raise SystemExit(f"not enough qualifying sellers for group {group}")
        # diversity: penalise repeating a nature_of_business or state already chosen
        pen = pool.apply(lambda r: 0.6 * sum(c["nature"] == r.nature_of_business for c in chosen)
                         + 0.4 * sum(c["state"] == r.seller_state for c in chosen), axis=1)
        best = (pool[score] - pen).sort_values(ascending=False, kind="stable")
        row = pool.loc[best.index[0]]
        if check is not None and not check(row):
            pool = pool[pool[FK] != row[FK]]
            continue
        chosen.append({"fk": row[FK], "group": group, "nature": row.nature_of_business, "state": row.seller_state})
        used.add(row[FK])
        pool = pool[pool[FK] != row[FK]]


def typical_score(df: pd.DataFrame) -> pd.Series:
    quiet = ~(df.frustrated | df.not_ready | df.asked_bot | df.mixed) & (df.t_frust + df.t_conf + df.t_rush == 0)
    return (quiet * 3 + (df.calls_meeting_fixed.fillna(0) >= 1) * 2 + df.has_eng * 1.0
            - (df.t_words - 9).abs() / 10 - (df.n_calls - 3).abs() * 0.2)


# ───────────────────────── seller construction ───────────────────────────────
def build_seller(rid: str, row, calls: pd.DataFrame, ts: pd.DataFrame) -> Seller:
    btype, role = NATURE[row.nature_of_business]
    tl = ts[ts[FK] == row[FK]].set_index("attempt_id")
    langs = Counter(tl.lang)
    seller_lang = langs.most_common(1)[0][0] if langs else "hinglish"
    mean_words = round(float(tl.avg_words.mean()), 1) if len(tl) else 8.0
    cl = calls[calls[FK] == row[FK]].sort_values("call_start_time").tail(6)

    pcs = []
    for r in cl.itertuples():
        d = r.disposition_label
        out = "meeting_fixed" if (d == "Meeting Fixed" and r.meeting_fixed == 1) else ("general" if d == "Meeting Fixed" else OUTCOME.get(d, "general"))
        has_t = r.attempt_id in tl.index
        pcs.append({"date": str(r.call_start_time)[:10], "outcome": out,
                    "dur": int(r.lead_call_duration) if pd.notna(r.lead_call_duration) else 0,
                    "lang": tl.lang[r.attempt_id] if has_t else seller_lang,
                    "words": round(float(tl.avg_words[r.attempt_id]), 1) if has_t else mean_words,
                    "disp": d})
    # the seller file says N calls were dropped; mark the N shortest non-meeting calls as disconnected (approximation)
    drop_n = min(int(row.dropped), len(pcs))
    for p in sorted((p for p in pcs if p["outcome"] != "meeting_fixed"), key=lambda p: p["dur"])[:drop_n]:
        p["outcome"] = "disconnected"
    # seller-level objections go on the most recent call that did not end in a meeting (ordered by count)
    target = next((p for p in reversed(pcs) if p["outcome"] != "meeting_fixed"), None)
    if target is not None:
        target["objs"] = row.objs
    past = [PastCall(date=p["date"], outcome=p["outcome"], duration_sec=p["dur"], objections=p.get("objs", []),
                     seller_language=p["lang"], avg_seller_turn_words=p["words"],
                     summary=f"Bot call, original label '{p['disp']}'.") for p in pcs]

    recv = float(row.eng_enq_received_90d) if pd.notna(row.eng_enq_received_90d) else 0.0
    repl = float(row.eng_enq_replies_90d) if pd.notna(row.eng_enq_replies_90d) else 0.0
    gst = row.gst_registration_year
    years = 2026 - int(gst) if pd.notna(gst) and gst >= 2017 else 0
    cats = [c for c in (row.top_category_1, row.top_category_2, row.top_category_3) if isinstance(c, str)]
    return Seller(
        seller_id=rid, display_name=f"{cats[0]} {role}, {row.seller_state}", city=row.seller_city, state=row.seller_state,
        business_type=btype, turnover_band=TURNOVER[row.annual_turnover], categories=cats, years_on_im=years,
        subscription="free", preferred_language=seller_lang,
        engagement=Engagement(leads_last_30d=round(recv / 3),
                              lead_response_rate=round(min(1.0, repl / recv), 2) if recv > 0 else 0.0,
                              app_active_days_30d=min(30, int(row.eng_activity_30d)) if pd.notna(row.eng_activity_30d) else 10,
                              avg_reply_time_hrs=0.0, last_login_days_ago=0),
        past_calls=past,
        history=History(showed_frustration=bool(row.frustrated), asked_if_bot=bool(row.asked_bot),
                        past_objection_categories=row.obj_cats, years_on_im_is_proxy=True))


def persona_check(calls, ts, test):
    from persona_bot.persona.generator import generate

    def check(row) -> bool:
        return test(generate(build_seller("TMP", row, calls, ts)))
    return check


def main() -> None:
    sellers = load_sellers()
    fks = set(sellers[FK])
    calls = load_calls(fks)
    ts = transcript_stats(fks)
    df = features(sellers, calls, ts)
    print(f"eligible sellers (≥2 bot calls, transcripts, not DNC, mappable): {len(df)}")

    chosen: list[dict] = []
    used: set[str] = set()
    pick(df, "busy_s", 3, chosen, used, "busy",
         lambda p: p.objs.apply(lambda o: "busy" in o) | ((p.callback_share >= 0.5) & (p.t_rush >= 1)),
         persona_check(calls, ts, lambda sp: sp.tone.verbosity == "crisp"))
    pick(df, "conf_s", 3, chosen, used, "new_or_confused", lambda p: (p.not_ready | (p.t_conf >= 1) | (p.conf_q >= 1) | p.eng_activity_30d.between(1, 4))
         & ~p.objs.apply(lambda o: "busy" in o),   # busy would win in the generator
         persona_check(calls, ts, lambda sp: sp.tone.verbosity == "explanatory"))
    pick(df, "frus_s", 3, chosen, used, "frustrated_or_mixed", lambda p: p.frustrated | (p.t_frust >= 1) | p.mixed,
         persona_check(calls, ts, lambda sp: sp.tone.empathy >= 4 and "frustration" in sp.live_adaptation.watch_for))
    df["typ_s"] = typical_score(df)
    pick(df, "typ_s", 1, chosen, used, "typical")

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    idmap = {}
    print("\nR-id  group                 type              turnover   state          calls  langs        flags")
    for i, c in enumerate(chosen, 1):
        rid = f"R{i:03d}"
        row = df[df[FK] == c["fk"]].iloc[0]
        s = build_seller(rid, row, calls, ts)
        (SAMPLES_DIR / f"seller_{rid}.json").write_text(s.model_dump_json(indent=2), encoding="utf-8")
        idmap[rid] = c["fk"]
        flags = [k for k, v in (("frustrated", row.frustrated), ("asked_bot", row.asked_bot), ("not_ready", row.not_ready),
                                ("mixed_lang", row.mixed)) if v]
        print(f"{rid}  {c['group']:20}  {s.business_type:16}  {s.turnover_band:9}  {s.state:13}  {len(s.past_calls):5}  "
              f"{'+'.join(row.langs):11}  {','.join(flags) or '-'}  objs={row.objs}")
    (RAW_DIR / "real_id_map.json").write_text(json.dumps(idmap, indent=2), encoding="utf-8")   # gitignored folder
    print(f"\nwrote {len(chosen)} files to data/samples/ (seller_R001..R010.json); id map in data/raw/real_id_map.json")


if __name__ == "__main__":
    main()
