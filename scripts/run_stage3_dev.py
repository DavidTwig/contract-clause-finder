"""Stage 3: all five clause types, second pass, statuses, merging, on the dev set.

Run:  .venv/Scripts/python scripts/run_stage3_dev.py
Writes results/stage3_dev.json, stage3_dev_findings.csv, stage3_dev_clauses.csv.
Re-runs use the cache. If the daily limit stops the run, results are saved with complete=false.

Counts here are provisional (Stage 4 defines the metrics). Span overlap is character-offset Jaccard.
"""

import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import llm
from pipeline import NEEDS_REVIEW, NOT_FOUND, VERIFIED, analyse_contract

OUT = config.RESULTS_DIR / "stage3_dev.json"
OUT_FINDINGS = config.RESULTS_DIR / "stage3_dev_findings.csv"
OUT_CLAUSES = config.RESULTS_DIR / "stage3_dev_clauses.csv"


def char_jaccard(a, b) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def size_stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def main():
    titles = json.loads(config.DEV_TITLES_PATH.read_text(encoding="utf-8"))
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        recs = {r["title"]: r for r in map(json.loads, f) if r["title"] in titles}

    run = {"started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "model": config.MODEL, "first_pass_prompt": config.FIRST_PASS_PROMPT,
           "second_pass_prompt": config.SECOND_PASS_PROMPT, "definitions": config.DEFINITIONS,
           "complete": True, "stopped_reason": None, "tokens_today_at_start": llm.tokens_today()}
    contracts = []
    for title in titles:
        rec = recs[title]
        print(f"\n{title[:80]}")
        try:
            out = analyse_contract(rec["text"])
        except llm.DailyLimitReached as e:
            run.update(complete=False, stopped_reason=str(e))
            print(f"STOPPED EARLY: {e}. Results saved with complete=false; rerun later to finish.")
            break
        gold = {c: [(s["start"], s["start"] + len(s["text"])) for s in rec["gold"][c]] for c in config.CATEGORIES}
        for fnd in out["findings"]:
            fnd["best_gold_jaccard"] = round(max((char_jaccard((fnd["start"], fnd["end"]), g)
                                                  for g in gold[fnd["category"]]), default=0.0), 3)
            fnd["text_in_contract"] = rec["text"][fnd["start"]:fnd["end"]]
        for cl in out["clauses"]:
            cl["gold_present"] = bool(gold[cl["category"]])
            cl["n_gold_spans"] = len(gold[cl["category"]])
            print(f"  {cl['category']:28s} {cl['status']:18s} gold={'yes' if cl['gold_present'] else 'no ':3s}  {'; '.join(cl['reasons'])}")
        contracts.append({"title": title, "chars": len(rec["text"]),
                          "gold": {c: [{"start": s, "end": e} for s, e in gold[c]] for c in config.CATEGORIES},
                          **out})
    run["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    run["tokens_today_at_end"] = llm.tokens_today()

    # ---- summary (all derived from `contracts`) ----
    per_cat = {}
    for c in config.CATEGORIES:
        cls = [cl for k in contracts for cl in k["clauses"] if cl["category"] == c]
        raw = [f for k in contracts for f in k["raw_findings"] if f["category"] == c]
        merged = [f for k in contracts for f in k["findings"] if f["category"] == c]
        per_contract = [(k, next(cl for cl in k["clauses"] if cl["category"] == c)) for k in contracts]
        before = [(cl["gold_present"], any(f["category"] == c for f in k["findings"])) for k, cl in per_contract]
        after = [(cl["gold_present"], cl["status"] == VERIFIED) for k, cl in per_contract]
        per_cat[c] = {
            "contracts": len(cls),
            "contracts_with_gold": sum(cl["gold_present"] for cl in cls),
            "status": {s: sum(cl["status"] == s for cl in cls) for s in (VERIFIED, NEEDS_REVIEW, NOT_FOUND)},
            "status_when_gold_present": {s: sum(cl["status"] == s for cl in cls if cl["gold_present"])
                                         for s in (VERIFIED, NEEDS_REVIEW, NOT_FOUND)},
            "status_when_gold_absent": {s: sum(cl["status"] == s for cl in cls if not cl["gold_present"])
                                        for s in (VERIFIED, NEEDS_REVIEW, NOT_FOUND)},
            "contract_level_before_second_pass": {
                "tp": sum(g and p for g, p in before), "fp": sum(p and not g for g, p in before),
                "fn": sum(g and not p for g, p in before)},
            "contract_level_after_second_pass_verified_only": {
                "tp": sum(g and p for g, p in after), "fp": sum(p and not g for g, p in after),
                "fn": sum(g and not p for g, p in after)},
            "raw_findings": len(raw),
            "raw_passed": sum(f["status"] == "passed" for f in raw),
            "failed_quotes": sum(f["status"] == "failed_quote" for f in raw),
            "merged_findings": len(merged),
            "second_pass_confirm": sum(f["verdict"] == "confirm" for f in merged),
            "second_pass_reject": sum(f["verdict"] == "reject" for f in merged),
            "second_pass_failed": sum(f["verdict"] is None for f in merged),
            "merged_overlapping_gold": sum(f["best_gold_jaccard"] > 0 for f in merged),
            "merged_jaccard_ge_0.5": sum(f["best_gold_jaccard"] >= 0.5 for f in merged),
            "gold_spans": sum(cl["n_gold_spans"] for cl in cls),
        }

    all_raw = [f for k in contracts for f in k["raw_findings"]]
    all_merged = [f for k in contracts for f in k["findings"]]
    fp_usage = [ch["usage"] for k in contracts for ch in k["chunks"] if ch["status"] == "ok"]
    fp_real = [ch["usage"] for k in contracts for ch in k["chunks"] if ch["status"] == "ok" and not ch["cached"]]
    sp_usage = [f["second_pass_usage"] for f in all_merged if f["second_pass_usage"]]
    sp_real = [f["second_pass_usage"] for f in all_merged if f["second_pass_usage"] and not f["second_pass_cached"]]

    def tok(rows):
        return {k: sum(r[k] or 0 for r in rows)
                for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")}

    summary = {
        "run": run,
        "contracts": len(contracts),
        "per_category": per_cat,
        "overall": {
            "chunks": sum(len(k["chunks"]) for k in contracts),
            "failed_chunks": sum(len(k["failed_chunks"]) for k in contracts),
            "raw_findings": len(all_raw),
            "raw_by_status": {s: sum(f["status"] == s for f in all_raw)
                              for s in ("passed", "failed_quote", "wrong_category")},
            "category_name_normalised": sum(f["model_category"] != f["category"]
                                            for f in all_raw if f["status"] != "wrong_category"),
            "merged_findings": len(all_merged),
            "merges": sum(len(f["merged_from_chunks"]) - 1 for f in all_merged),
            "second_pass_confirm": sum(f["verdict"] == "confirm" for f in all_merged),
            "second_pass_reject": sum(f["verdict"] == "reject" for f in all_merged),
            "second_pass_failed": sum(f["verdict"] is None for f in all_merged),
        },
        "tokens": {
            "first_pass_all_calls": tok(fp_usage), "second_pass_all_calls": tok(sp_usage),
            "first_pass_uncached_this_run": tok(fp_real), "second_pass_uncached_this_run": tok(sp_real),
            "api_calls_this_run": {"first_pass": len(fp_real), "second_pass": len(sp_real)},
        },
        "reply_sizes_completion_tokens": {
            "first_pass": size_stats([u["completion_tokens"] for u in fp_usage]),
            "second_pass": size_stats([u["completion_tokens"] for u in sp_usage]),
            "first_pass_reasoning": size_stats([u["reasoning_tokens"] for u in fp_usage]),
            "second_pass_reasoning": size_stats([u["reasoning_tokens"] for u in sp_usage]),
            "throttle_reply_estimate": config.REPLY_TOKENS_ESTIMATE,
        },
        "note": "Provisional counts; Stage 4 defines metrics. best_gold_jaccard is character-offset Jaccard.",
    }

    config.RESULTS_DIR.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "contracts": contracts}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    with open(OUT_FINDINGS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "category", "status", "verdict", "verdict_reason", "start", "end",
                    "best_gold_jaccard", "merged_from_chunks", "text_in_contract", "first_pass_reason"])
        for k in contracts:
            for fnd in k["findings"]:
                w.writerow([k["title"], fnd["category"], fnd["status"], fnd["verdict"], fnd["verdict_reason"],
                            fnd["start"], fnd["end"], fnd["best_gold_jaccard"], fnd["merged_from_chunks"],
                            fnd["text_in_contract"], fnd["reason"]])
            for fnd in k["raw_findings"]:
                if fnd["status"] != "passed":
                    w.writerow([k["title"], fnd["category"], fnd["status"], "", "", "", "", "", [fnd["chunk"]],
                                fnd["quote"], fnd["reason"]])
    with open(OUT_CLAUSES, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "category", "status", "gold_present", "n_gold_spans", "reasons"])
        for k in contracts:
            for cl in k["clauses"]:
                w.writerow([k["title"], cl["category"], cl["status"], cl["gold_present"], cl["n_gold_spans"],
                            "; ".join(cl["reasons"])])

    print("\n" + json.dumps(summary, indent=1))
    print(f"\nWrote {OUT}, {OUT_FINDINGS}, {OUT_CLAUSES}")


if __name__ == "__main__":
    main()
