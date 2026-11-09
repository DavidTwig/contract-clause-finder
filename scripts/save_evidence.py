"""Save evidence the write-up relies on, as files in results/. No API calls, no network.

Run:  .venv/Scripts/python scripts/save_evidence.py
Writes:
  results/evidence_duplicate_contract.json
      The two ADUROBIOTECH train copies: identical text, gold labels compared per clause type.
      Read from the local CUAD-QA copy in data/raw/hf (offline).
  results/evidence_cap_missed_spans.json and .csv
      Every dev Cap on Liability gold span, for each Stage 3 dev run: found by a Verified
      finding or not, best character-Jaccard, the gold text, and keyword hints.
      The hints are regex matches for orientation only; read the text to judge.
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

os.environ["HF_DATASETS_OFFLINE"] = "1"  # local copy only; never download
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import cuad_loader
from pipeline import VERIFIED

DUP_TITLES = ["ADUROBIOTECH,INC_06_02_2020-EX-10.7-CONSULTING AGREEMENT",
              "ADUROBIOTECH,INC_06_02_2020-EX-10.7-CONSULTING AGREEMENT(1)"]
RUNS = ["stage3_dev", "stage3_dev_defs_v4"]
CAP = "Cap on Liability"

HINTS = {
    "damage_type_exclusion": r"consequential|incidental|indirect|special damages|punitive|lost profits",
    "claim_time_limit": r"(brought|commenced|action|claim)[^.]{0,120}(year|month|days)",
    "monetary_cap": r"exceed|aggregate|maximum|limited to the amount|in no event shall[^.]{0,40}liability",
    "force_majeure": r"force majeure",
}


def jaccard(a, b) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def hints(text: str) -> list[str]:
    return [name for name, rx in HINTS.items() if re.search(rx, text, flags=re.IGNORECASE)] or ["none"]


def duplicate_contract() -> dict:
    rows = [r for r in cuad_loader.load_rows()["train"] if r["title"] in DUP_TITLES]
    saved, cuad_loader.DROP_TITLES = cuad_loader.DROP_TITLES, set()
    try:
        recs = {r["title"]: r for r in cuad_loader.build_records(rows, "train")}
    finally:
        cuad_loader.DROP_TITLES = saved
    a, b = (recs[t] for t in DUP_TITLES)
    per_cat = {}
    for c in config.CATEGORIES:
        sa = {(s["start"], s["text"]) for s in a["gold"][c]}
        sb = {(s["start"], s["text"]) for s in b["gold"][c]}
        per_cat[c] = {"same": sa == sb,
                      "only_in_" + DUP_TITLES[0]: [{"start": s, "text": t} for s, t in sorted(sa - sb)],
                      "only_in_" + DUP_TITLES[1]: [{"start": s, "text": t} for s, t in sorted(sb - sa)],
                      "n_spans": [len(sa), len(sb)]}
    return {"titles": DUP_TITLES, "rows_read": len(rows), "text_identical": a["text"] == b["text"],
            "text_chars": [len(a["text"]), len(b["text"])], "per_category": per_cat,
            "dropped_by_loader": sorted(cuad_loader.DROP_TITLES)}


def cap_missed_spans() -> dict:
    out = {"note": "keyword_hints are regex matches for orientation only; judge from gold_text.", "runs": {}}
    for name in RUNS:
        run = json.loads((config.RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        rows = []
        for k in run["contracts"]:
            status = next(cl["status"] for cl in k["clauses"] if cl["category"] == CAP)
            ver = [(f["start"], f["end"]) for f in k["findings"] if f["category"] == CAP and f["status"] == VERIFIED]
            for g in k["gold"][CAP]:
                gs = (g["start"], g["end"])
                best = max((jaccard(gs, v) for v in ver), default=0.0)
                text = k["text"][g["start"]:g["end"]] if "text" in k else None
                rows.append({"title": k["title"], "contract_status": status, "gold_start": g["start"],
                             "gold_end": g["end"], "found_any_overlap": best > 0,
                             "best_jaccard": round(best, 3), "gold_text": text})
        out["runs"][name] = {"definitions": run["summary"]["run"]["definitions"],
                             "complete": run["summary"]["run"]["complete"], "spans": rows}
    return out


def main():
    dev = {r["title"]: r for r in map(json.loads, open(config.CONTRACTS_PATH, encoding="utf-8"))
           if r["title"] in json.loads(config.DEV_TITLES_PATH.read_text(encoding="utf-8"))}

    dup = duplicate_contract()
    (config.RESULTS_DIR / "evidence_duplicate_contract.json").write_text(
        json.dumps(dup, ensure_ascii=False, indent=1), encoding="utf-8")

    cap = cap_missed_spans()
    summary = {}
    for name, r in cap["runs"].items():
        for s in r["spans"]:
            s["gold_text"] = dev[s["title"]]["text"][s["gold_start"]:s["gold_end"]]
            s["keyword_hints"] = hints(s["gold_text"])
        missed = [s for s in r["spans"] if not s["found_any_overlap"]]
        summary[name] = {"gold_spans": len(r["spans"]), "found_any_overlap": len(r["spans"]) - len(missed),
                         "found_jaccard_ge_0.5": sum(s["best_jaccard"] >= 0.5 for s in r["spans"]),
                         "missed": len(missed),
                         "missed_by_hint": {h: sum(h in s["keyword_hints"] for s in missed)
                                            for h in list(HINTS) + ["none"]}}
    cap["summary"] = summary
    (config.RESULTS_DIR / "evidence_cap_missed_spans.json").write_text(
        json.dumps(cap, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(config.RESULTS_DIR / "evidence_cap_missed_spans.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "title", "contract_status", "gold_start", "gold_end", "found_any_overlap",
                    "best_jaccard", "keyword_hints", "gold_text"])
        for name, r in cap["runs"].items():
            for s in r["spans"]:
                w.writerow([name, s["title"], s["contract_status"], s["gold_start"], s["gold_end"],
                            s["found_any_overlap"], s["best_jaccard"], "; ".join(s["keyword_hints"]), s["gold_text"]])

    print(json.dumps({"duplicate_contract": {k: dup[k] for k in ("rows_read", "text_identical", "text_chars")},
                      "differences": {c: v for c, v in dup["per_category"].items() if not v["same"]},
                      "cap_summary": summary}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
