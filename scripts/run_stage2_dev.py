"""Stage 2: Governing Law only, on the dev set: split, first pass, quote check.

Run:  .venv/Scripts/python scripts/run_stage2_dev.py
Writes results/stage2_dev_governing_law.json and .csv. Re-runs use the cache and cost nothing.

The span overlap here is an informal, character-based Jaccard. Stage 4 defines the real metric.

NOTE: this script NO LONGER REPRODUCES the committed Stage 2 results. It uses the current prompt
settings in config.py (Stage 2 used first_pass_v1 + category_definitions_v1), so rerunning it makes
new API calls with newer prompts. The Stage 2 results in results/stage2_dev_governing_law.* stand as
recorded; to reproduce them, set FIRST_PASS_PROMPT="first_pass_v1" and DEFINITIONS="category_definitions_v1".
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import llm
from first_pass import run_first_pass

CATEGORY = "Governing Law"
OUT_JSON = config.RESULTS_DIR / "stage2_dev_governing_law.json"
OUT_CSV = config.RESULTS_DIR / "stage2_dev_governing_law.csv"


def char_jaccard(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def main():
    titles = json.loads(config.DEV_TITLES_PATH.read_text(encoding="utf-8"))
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        recs = {r["title"]: r for r in map(json.loads, f) if r["title"] in titles}

    contracts = []
    for title in titles:
        rec = recs[title]
        print(f"\n{title[:80]}")
        try:
            out = run_first_pass(rec["text"], [CATEGORY])
        except llm.DailyLimitReached as e:
            print(f"Stopped: {e}. Run again later; finished chunks are cached.")
            break
        gold = [(s["start"], s["start"] + len(s["text"])) for s in rec["gold"][CATEGORY]]
        kept = []
        for fnd in out["findings"]:
            if fnd["status"] == "passed":
                span = (fnd["start"], fnd["end"])
                fnd["best_gold_jaccard"] = round(max((char_jaccard(span, g) for g in gold), default=0.0), 3)
                dup = next((k for k in kept if char_jaccard(span, (k["start"], k["end"])) > 0), None)
                fnd["duplicate_of_chunk"] = dup["chunk"] if dup else None
                if not dup:
                    kept.append(fnd)
            print(f"  [{fnd['status']}] chunk {fnd['chunk']}: {fnd['quote'][:110]!r}")
        contracts.append({
            "title": title,
            "chars": len(rec["text"]),
            "gold": [{"start": s, "end": e, "text": rec["text"][s:e]} for s, e in gold],
            **out,
        })

    # Summary counts (all derived from the per-contract records above)
    all_f = [f for c in contracts for f in c["findings"]]
    passed = [f for f in all_f if f["status"] == "passed" and f.get("duplicate_of_chunk") is None]
    real_calls = [ch for c in contracts for ch in c["chunks"] if ch["status"] == "ok" and not ch["cached"]]
    all_calls = [ch for c in contracts for ch in c["chunks"] if ch["status"] == "ok"]
    summary = {
        "category": CATEGORY,
        "model": config.MODEL,
        "prompt_version": config.FIRST_PASS_PROMPT,
        "contracts": len(contracts),
        "contracts_with_gold": sum(1 for c in contracts if c["gold"]),
        "contracts_with_passed_finding": sum(
            1 for c in contracts if any(f["status"] == "passed" for f in c["findings"])),
        "contracts_with_gold_and_passed_finding": sum(
            1 for c in contracts if c["gold"] and any(f["status"] == "passed" for f in c["findings"])),
        "chunks": sum(len(c["chunks"]) for c in contracts),
        "invalid_responses": sum(len(c["errors"]) for c in contracts),
        "findings_total": len(all_f),
        "findings_by_status": {s: sum(1 for f in all_f if f["status"] == s)
                               for s in ("passed", "failed_quote", "wrong_category")},
        "overlap_duplicates": sum(1 for f in all_f if f.get("duplicate_of_chunk") is not None),
        "unique_passed_findings": len(passed),
        "unique_passed_with_gold_jaccard_ge_0.5": sum(1 for f in passed if f["best_gold_jaccard"] >= 0.5),
        "gold_spans": sum(len(c["gold"]) for c in contracts),
        "retries_for_invalid_json": sum(1 for ch in all_calls if ch["attempts"] == 2),
        "tokens_this_run_uncached": {
            k: sum(ch["usage"][k] or 0 for ch in real_calls)
            for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")},
        "tokens_all_calls_incl_cached": {
            k: sum(ch["usage"][k] or 0 for ch in all_calls)
            for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")},
        "api_calls_this_run": len(real_calls),
        "note": "best_gold_jaccard is an informal character-offset Jaccard; Stage 4 defines the metric.",
    }

    config.RESULTS_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({"summary": summary, "contracts": contracts},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "chunk", "status", "start", "end", "best_gold_jaccard",
                    "duplicate_of_chunk", "quote", "reason"])
        for c in contracts:
            for fnd in c["findings"]:
                w.writerow([c["title"], fnd["chunk"], fnd["status"], fnd["start"], fnd["end"],
                            fnd.get("best_gold_jaccard"), fnd.get("duplicate_of_chunk"),
                            fnd["quote"], fnd["reason"]])
            if not c["findings"]:
                w.writerow([c["title"], "", "no_findings", "", "", "", "", "", ""])

    print("\n" + json.dumps(summary, indent=1))
    print(f"\nWrote {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
