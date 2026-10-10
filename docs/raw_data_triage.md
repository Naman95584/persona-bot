# Raw data triage for Problem 4 (Persona Design)

Schema only: file names, columns, row counts. No values were read. All 17 files in `data/raw/` are the PS07 dataset (Seller-Fit Adaptive Voice Persona), so every file is relevant to our problem. All share the seller key `fk_glusr_usr_id`. Call-level files also share `attempt_id`.

Score: 3 = seller id + (business type/turnover/category) or call outcome or transcripts; 2 = seller id + engagement/objection fields; 1 = seller id only; 0 = unrelated.

| Rank | File | Type | Rows | Key columns found | Seller ID | Score | Why |
|---|---|---|---|---|---|---|---|
| 1 | `ps07_seller_files_part1.csv` + `part2.csv` (58 cols, stack the parts) | SELLER_PROFILE | ~149.4k (dictionary: 149,363) | `business_type`, `annual_turnover`, `top_category_1/2/3`, `seller_state`, `nature_of_business`, `eng_*`, `calls_meeting_fixed`, `calls_not_interested`, `past_objections`, `showed_frustration`, `asked_if_talking_to_bot`, `past_dispositions_detailed`, `do_not_call_requested` | `fk_glusr_usr_id` | 3 | The persona input: profile, engagement, and per-seller bot-call outcomes, objections and frustration flags in one row. |
| 2 | `ps07_call_turns.csv` | TRANSCRIPTS | 139,555 turns (12,788 calls) | `speaker`, `text`, `start_sec`, `end_sec`, `turn_no` | `fk_glusr_usr_id` + `attempt_id` | 3 | Turn-level Hindi/Hinglish text. Trains and tests the live signal detector, and gives bot traits (language, verbosity) for the evidence miner. |
| 3 | `ps07_bot_calls_2026-04_to_06`, `-07`, `-08`, `-09` (.csv) | CALL_RECORDS | 269,455 total | `disposition_label`, `meeting_fixed`, `lead_bot_version`, `lead_call_summary`, `lead_call_duration`, `has_turn_transcript` | `fk_glusr_usr_id` + `attempt_id` | 3 | Outcome table for the miner (segment x bot choice -> meeting rate). `lead_bot_version` includes a `personalis...` trial, a natural experiment. |
| 4 | `ps07_evaluator_outputs_*` (7 files) | CALL_RECORDS / ENGAGEMENT (JSON in `agent_output`) | 278,332 total | `eval_agent` (disposition, objections, seller_questions, latency_repetition, ...), `agent_output` | `fk_glusr_usr_id` + `attempt_id` | 3 | Detailed outcomes and objections. `latency_repetition` holds transcripts for 13,681 calls (the source of `call_turns`). |
| 5 | `ps07_recording_sample_5000.csv` | CALL_RECORDS | 5,000 | Same columns as bot_calls, incl. `call_recording_url` | `fk_glusr_usr_id` + `attempt_id` | 3 | Balanced subset of bot calls with audio links. Useful for checking Saaras against existing transcripts. |
| 6 | `ps07_executive_calls.csv` | OTHER (executive contact; "best time to call" / "already in touch") | 67,151 | `module`, `status`, `call_duration`, `ring_duration`, `fk_employeeid` | `fk_glusr_usr_id` | 2 | Aug-Sep only; nothing persona-relevant. |

## Recommended minimum set
1. `seller_files` part1+2: pre-call persona input.
2. `bot_calls` (all four files, at least Jul-Sep): persona choices and outcomes for the evidence miner.
3. `call_turns.csv`: Hindi/Hinglish text for the live signal detector and bot traits.
4. Optional: `evaluator_outputs` filtered to `disposition` and `objections`, if `past_objections` / `past_dispositions_detailed` prove too coarse.

Skip `executive_calls`. Add the recording sample later for the STT check.

## Caveats
- Row counts are newline counts, so they can run slightly high where quoted fields contain line breaks (seller files ~111 over the dictionary figure). bot_calls and evaluator totals match the dictionary exactly.
- No language, formality or pace columns exist anywhere. The miner must derive them from `call_turns` (via `evidence/traits.py`), which covers only 12,788 of the 269k calls.
- The data dictionary says summaries, transcripts and evaluator quotes contain real seller and company names. Do not send them to a hosted model until the organisers confirm it is allowed; work on schemas and aggregates until then.
