# Real-data summary (PS07 bot calls, Apr–Sep 2026)

Aggregates only; cells with n < 30 are suppressed. Rate = `meeting_fixed == 1` per answered bot call. `business_type` = our mapped `nature_of_business`; turnover bands as in the Seller model.

## a) Totals

- Answered bot calls: **269,455**
- Distinct sellers called: **130,129** (0 calls without a seller id)
- Overall meeting-fixed rate: **11.5%** (31,013 calls)
- Calls with a seller-file match (business type and turnover known): 223,798 (83.1%)

## b) Meeting rate by `lead_bot_version`

| lead_bot_version | n | meeting rate | 95% CI |
|---|---:|---:|---|
| main_vani | 208,605 | 11.6% | 11.5% to 11.7% |
| arrowhead | 30,676 | 10.7% | 10.3% to 11.0% |
| last_met_d | 23,046 | 11.1% | 10.7% to 11.5% |
| main | 5,573 | 14.0% | 13.1% to 15.0% |
| last_met_a | 723 | 11.9% | 9.7% to 14.5% |
| personalis | 452 | 14.2% | 11.2% to 17.7% |
| base_vani | 289 | 18.3% | 14.3% to 23.2% |
| summary_va | 91 | 3.3% | 1.1% to 9.2% |

### `personalis` trial vs the others

The trial has **452** calls from **325** sellers, all in 2026-09. The dictionary says these are the *recorded* calls of the trial, so the trial may have been larger and this subset may not be a random sample.

| Control group | n control | control rate | trial rate | diff (pts) | 95% CI (pts, calls) | 95% CI (pts, seller-clustered) |
|---|---:|---:|---:|---:|---|---|
| All other versions, all months | 269,003 | 11.5% | 14.2% | +2.7 | -0.6 to +5.9 | -0.6 to +6.1 |
| Other versions, Sep only (same month) | 68,995 | 10.6% | 14.2% | +3.6 | +0.3 to +6.8 | +0.3 to +7.0 |
| `main_vani`, Sep only | 59,125 | 10.5% | 14.2% | +3.6 | +0.4 to +6.9 | +0.4 to +7.2 |

### Is the segment mix different? (trial vs Sep controls)

| business_type | trial | Sep others | gap (pts) |
|---|---:|---:|---:|
| distributor | 21.7% | 22.7% | -1.1 |
| manufacturer | 32.3% | 24.2% | +8.1 |
| retailer | 22.6% | 27.5% | -4.9 |
| service_provider | 12.8% | 14.5% | -1.7 |
| unknown | 10.6% | 11.1% | -0.4 |

Total-variation distance for business type: **0.081** (0 = identical mix, 1 = disjoint).

| turnover | trial | Sep others | gap (pts) |
|---|---:|---:|---:|
| 0-40L | 55.1% | 58.8% | -3.7 |
| 1.5-5Cr | 7.1% | 7.7% | -0.6 |
| 25Cr+ | 2.7% | 1.6% | +1.0 |
| 40L-1.5Cr | 13.7% | 14.8% | -1.1 |
| 5-25Cr | 5.5% | 4.2% | +1.3 |
| unknown | 15.9% | 12.8% | +3.1 |

Total-variation distance for turnover band: **0.054** (0 = identical mix, 1 = disjoint).

| redis_bucket | trial | Sep others | gap (pts) |
|---|---:|---:|---:|
| ENQR | 1.8% | 0.8% | +1.0 |
| OLP | 4.4% | 4.3% | +0.1 |
| PAM | 3.1% | 3.0% | +0.1 |
| PIM | 43.1% | 35.3% | +7.8 |
| PNSM | 1.8% | 0.3% | +1.4 |
| PNSR | 2.2% | 0.4% | +1.9 |
| PUA | 27.4% | 33.1% | -5.6 |
| SCHD | 0.0% | 2.1% | -2.1 |
| UA | 16.2% | 20.1% | -3.9 |

Total-variation distance for lead type (redis_bucket): **0.123** (0 = identical mix, 1 = disjoint).

**The mix differs noticeably**, so raw differences can reflect who was called, not the bot. Mix-adjusted differences below are the safer numbers.

### Mix-adjusted difference (standardised to the trial's mix)

| Control | Adjusted on | diff (pts) | 95% CI (pts) | trial calls covered |
|---|---|---:|---|---:|
| Other versions, Sep | business type × turnover | +5.4 | +1.8 to +9.1 | 98.1% |
| Other versions, Sep | lead type | +3.9 | +0.7 to +7.1 | 100.0% |
| `main_vani`, Sep | business type × turnover | +5.5 | +1.9 to +9.2 | 98.1% |
| `main_vani`, Sep | lead type | +4.0 | +0.8 to +7.2 | 100.0% |

### Trial vs Sep controls, by business type

| business_type | n trial | trial rate | n control | control rate | diff (pts) | 95% CI (pts) |
|---|---:|---:|---:|---:|---:|---|
| distributor | 91 | 16.5% | 14,496 | 9.0% | +7.5 | -0.2 to +15.1 |
| manufacturer | 137 | 16.1% | 15,408 | 9.1% | +6.9 | +0.8 to +13.1 |
| retailer | 82 | 14.6% | 17,050 | 9.9% | +4.7 | -3.0 to +12.4 |
| service_provider | 50 | 10.0% | 9,019 | 11.6% | -1.6 | -10.0 to +6.7 |

### Trial vs Sep controls, by turnover band

| turnover | n trial | trial rate | n control | control rate | diff (pts) | 95% CI (pts) |
|---|---:|---:|---:|---:|---:|---|
| 0-40L | 238 | 14.7% | 37,398 | 10.2% | +4.5 | -0.0 to +9.0 |
| 40L-1.5Cr | 54 | 20.4% | 9,599 | 9.2% | +11.1 | +0.4 to +21.9 |
| 1.5-5Cr | 31 | 12.9% | 5,024 | 9.1% | +3.8 | -8.0 to +15.6 |

### Control check: meeting rate by month (all versions)

| month | n | meeting rate | 95% CI |
|---|---:|---:|---|
| 2026-04 | 9,800 | 14.7% | 14.1% to 15.5% |
| 2026-05 | 23,328 | 13.6% | 13.1% to 14.0% |
| 2026-06 | 34,806 | 14.7% | 14.3% to 15.0% |
| 2026-07 | 58,124 | 11.6% | 11.4% to 11.9% |
| 2026-08 | 73,950 | 9.7% | 9.5% to 9.9% |
| 2026-09 | 69,447 | 10.6% | 10.4% to 10.9% |

## c) Meeting rate by segment

### Business type

| business_type | n | meeting rate | 95% CI |
|---|---:|---:|---|
| distributor | 57,587 | 9.5% | 9.2% to 9.7% |
| manufacturer | 59,641 | 10.3% | 10.0% to 10.5% |
| retailer | 69,324 | 10.9% | 10.6% to 11.1% |
| service_provider | 37,246 | 12.2% | 11.8% to 12.5% |

### Turnover band

| turnover | n | meeting rate | 95% CI |
|---|---:|---:|---|
| 0-40L | 149,077 | 11.2% | 11.1% to 11.4% |
| 40L-1.5Cr | 39,317 | 9.5% | 9.2% to 9.8% |
| 1.5-5Cr | 21,473 | 8.9% | 8.5% to 9.3% |
| 5-25Cr | 10,445 | 8.7% | 8.1% to 9.2% |
| 25Cr+ | 3,486 | 9.1% | 8.2% to 10.1% |

### Call-duration band

| dur_band | n | meeting rate | 95% CI |
|---|---:|---:|---|
| 0-10s | 75,448 | 0.0% | 0.0% to 0.0% |
| 11-30s | 86,542 | 0.7% | 0.7% to 0.8% |
| 31-60s | 55,561 | 20.2% | 19.9% to 20.6% |
| 61-120s | 42,156 | 36.1% | 35.6% to 36.6% |
| 121s+ | 9,748 | 40.3% | 39.3% to 41.2% |

> **Caution:** duration is partly an *outcome* of the call (a seller who agrees to a meeting talks longer), so the duration gradient is not evidence that long calls cause meetings.

## Caveats

- Calls to the same seller are not independent; the seller-clustered intervals are the honest ones.
- Version assignment was not randomised that we know of; month and lead type differ across versions.
- Results describe answered calls only (no-answer calls are not in this file).

## Three findings for a slide

1. The personalised-script bot fixed meetings on 14.2% of its 452 calls vs 10.6% for other September bots (+3.6 points, 95% interval +0.3 to +7.0; +5.4 points after adjusting for business type and turnover mix).
2. By business type, the bot's meeting rate runs from 9.5% (distributor) to 12.2% (service_provider), among calls with a known seller profile.
3. By seller size (turnover), the bot's meeting rate runs from 8.7% (5-25Cr) to 11.2% (0-40L), among calls with a known seller profile.
