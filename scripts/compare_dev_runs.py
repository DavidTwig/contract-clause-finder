"""Compare two Stage 3 dev runs, per clause type, with raw counts.

Run:  .venv/Scripts/python scripts/compare_dev_runs.py stage3_dev stage3_dev_defs_v4
Writes results/<before>_vs_<after>.json. Counts are provisional (Stage 4 defines the metrics).

Per clause type and run:
  contract level  - of contracts WITH the clause in gold: Verified / Needs review / Not found
                  - of contracts WITHOUT it: wrongly Verified / Needs review / correctly Not found
  span level      - gold spans touched by a Verified finding of the same type (any overlap),
                    and matched with character Jaccard >= 0.5
  finding level   - Verified findings, and how many overlap no gold span of their type
                    (a rough precision check; CUAD gold can miss real clauses)
  second pass     - confirm / reject / failed
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from pipeline import NEEDS_REVIEW, NOT_FOUND, VERIFIED


def jaccard(a, b) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def summarise(run: dict) -> dict:
    s = run["summary"]
    if not s["run"]["complete"]:
        sys.exit("Refusing to compare: a run stopped early at the daily limit.")
    out = {}
    for c in config.CATEGORIES:
        r = {"with_gold": {VERIFIED: 0, NEEDS_REVIEW: 0, NOT_FOUND: 0},
             "without_gold": {VERIFIED: 0, NEEDS_REVIEW: 0, NOT_FOUND: 0},
             "gold_spans": 0, "gold_spans_touched": 0, "gold_spans_jaccard_ge_0.5": 0,
             "verified_findings": 0, "verified_findings_overlapping_no_gold": 0,
             "second_pass": {"confirm": 0, "reject": 0, "failed": 0}, "missed": [], "reject_reasons": []}
        for k in run["contracts"]:
            gold = [(g["start"], g["end"]) for g in k["gold"][c]]
            cl = next(x for x in k["clauses"] if x["category"] == c)
            r["with_gold" if gold else "without_gold"][cl["status"]] += 1
            if gold and cl["status"] != VERIFIED:
                r["missed"].append(f"{k['title']} -> {cl['status']}")
            mine = [f for f in k["findings"] if f["category"] == c]
            ver = [(f["start"], f["end"]) for f in mine if f["status"] == VERIFIED]
            r["gold_spans"] += len(gold)
            r["gold_spans_touched"] += sum(any(jaccard(g, v) > 0 for v in ver) for g in gold)
            r["gold_spans_jaccard_ge_0.5"] += sum(any(jaccard(g, v) >= 0.5 for v in ver) for g in gold)
            r["verified_findings"] += len(ver)
            r["verified_findings_overlapping_no_gold"] += sum(not any(jaccard(g, v) > 0 for g in gold) for v in ver)
            for f in mine:
                r["second_pass"][f["verdict"] or "failed"] += 1
                if f["verdict"] == "reject":
                    r["reject_reasons"].append(f"{k['title']}: {f['verdict_reason']}")
        out[c] = r
    return out


def main():
    before_name, after_name = sys.argv[1], sys.argv[2]
    runs = {n: json.loads((config.RESULTS_DIR / f"{n}.json").read_text(encoding="utf-8"))
            for n in (before_name, after_name)}
    versions = {n: {k: r["summary"]["run"][k] for k in ("first_pass_prompt", "second_pass_prompt", "definitions")}
                for n, r in runs.items()}
    result = {"runs": versions, "tokens": {n: r["summary"]["tokens"] for n, r in runs.items()},
              "per_category": {n: summarise(r) for n, r in runs.items()},
              "note": "Provisional; Stage 4 defines the metrics. Span match uses Verified findings only."}
    out = config.RESULTS_DIR / f"{before_name}_vs_{after_name}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    for c in config.CATEGORIES:
        print(f"\n{c}")
        for n in (before_name, after_name):
            r = result["per_category"][n][c]
            wg, ng = r["with_gold"], r["without_gold"]
            print(f"  {n:22s} gold-present: V {wg[VERIFIED]}/{sum(wg.values())}, NR {wg[NEEDS_REVIEW]}, NF {wg[NOT_FOUND]}"
                  f" | gold-absent: wrongly V {ng[VERIFIED]}/{sum(ng.values())}, NR {ng[NEEDS_REVIEW]}, NF {ng[NOT_FOUND]}"
                  f" | spans touched {r['gold_spans_touched']}/{r['gold_spans']}, J>=0.5 {r['gold_spans_jaccard_ge_0.5']}/{r['gold_spans']}"
                  f" | V findings {r['verified_findings']} (no gold overlap {r['verified_findings_overlapping_no_gold']})"
                  f" | 2nd pass {r['second_pass']}")
            for m in r["missed"]:
                print(f"      missed: {m}")
            for x in r["reject_reasons"]:
                print(f"      rejected: {x}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
