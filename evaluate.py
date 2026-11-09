"""Stage 4: score a saved pipeline run against CUAD gold labels.

Run:  .venv/Scripts/python evaluate.py <run name>      e.g. evaluate.py eval
Reads results/<run name>.json (the format scripts/run_stage3_dev.py writes) and data/contracts.jsonl.
Writes results/metrics.json and results/errors.csv for the run named "eval";
for any other run, results/<run name>_metrics.json and _errors.csv.
No API calls: this file only scores. (Running the pipeline on eval is a separate step.)

Refuses to score (David's rules):
  1. a run that stopped early (complete = false), e.g. at the daily token limit;
  2. a run whose model or prompt versions differ from the current config.py.

Definitions used throughout
  cell          one (contract, clause type) pair. Gold present = CUAD has >= 1 span for it.
  predicted     AFTER the second pass: the cell's status is Verified.
                BEFORE the second pass: the cell has any finding that passed the quote check.
  span match    character-offset Jaccard >= 0.5 between a predicted span and a gold span
                (same contract, same clause type): overlap length / length of the union.
                A prediction is correct if it matches ANY gold span; a gold span is found if
                ANY prediction matches it (not one-to-one).
  no CUAD match a finding shown to the user whose quote failed the quote check, or whose span
                overlaps no gold span of its type at all. Called "no CUAD match", not "wrong",
                because CUAD gold misses some real clauses: the manual review decides which are
                model errors, gold label issues or ambiguous. (An over-long quote that contains
                the clause does match; the span metric scores its extent.)
"""

import csv
import json
import sys
from pathlib import Path

import config
from pipeline import NEEDS_REVIEW, NOT_FOUND, VERIFIED

SPAN_THRESHOLD = 0.5
VERSION_KEYS = {"model": "MODEL", "first_pass_prompt": "FIRST_PASS_PROMPT",
                "second_pass_prompt": "SECOND_PASS_PROMPT", "definitions": "DEFINITIONS"}


class RunNotScorable(Exception):
    """The run must not be reported on."""


# --- refusal rules -----------------------------------------------------------

def check_scorable(run_info: dict, cfg=config) -> None:
    if run_info.get("complete") is not True:
        raise RunNotScorable(f"run is incomplete (stopped early: {run_info.get('stopped_reason')}); "
                             "finish it before scoring")
    diffs = {k: (run_info.get(k), getattr(cfg, attr)) for k, attr in VERSION_KEYS.items()
             if run_info.get(k) != getattr(cfg, attr)}
    if diffs:
        detail = ", ".join(f"{k}: run={r!r} config={c!r}" for k, (r, c) in diffs.items())
        raise RunNotScorable(f"run used different versions than the current config ({detail})")


# --- basic measures ----------------------------------------------------------

def span_jaccard(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def best_jaccard(span, others) -> float:
    return max((span_jaccard(span, o) for o in others), default=0.0)


def ratio(num: int, den: int) -> dict:
    """A share with its raw counts, so reports can show "4/5 (80%)". None when den is 0."""
    return {"n": num, "of": den, "value": round(num / den, 4) if den else None}


def f1_score(p: dict, r: dict) -> float | None:
    """None if precision or recall is undefined (nothing predicted / nothing in gold)."""
    if p["value"] is None or r["value"] is None:
        return None
    total = p["value"] + r["value"]
    return round(2 * p["value"] * r["value"] / total, 4) if total else 0.0


def prf(tp: int, fp: int, fn: int, tn: int | None = None) -> dict:
    p, r = ratio(tp, tp + fp), ratio(tp, tp + fn)
    out = {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1_score(p, r)}
    if tn is not None:
        out["tn"] = tn
    return out


# --- cells -------------------------------------------------------------------

def cells(contracts: list[dict], categories: list[str]):
    """One dict per (contract, clause type) with everything the metrics need."""
    for k in contracts:
        for c in categories:
            merged = [f for f in k["findings"] if f["category"] == c]
            yield {"title": k["title"], "category": c,
                   "gold": [(g["start"], g["end"]) for g in k["gold"][c]],
                   "status": next(cl["status"] for cl in k["clauses"] if cl["category"] == c),
                   "merged": merged,
                   "verified": [f for f in merged if f["status"] == VERIFIED],
                   "failed_quotes": [f for f in k["raw_findings"]
                                     if f["category"] == c and f["status"] == "failed_quote"],
                   "raw": [f for f in k["raw_findings"] if f["category"] == c]}


def _span(f):
    return (f["start"], f["end"])


# --- metrics -------------------------------------------------------------------

def contract_level(cs: list[dict], when: str) -> dict:
    tp = fp = fn = tn = tp_no_overlap = 0
    for x in cs:
        pred = x["status"] == VERIFIED if when == "after" else bool(x["merged"])
        gold = bool(x["gold"])
        tp += pred and gold
        if pred and gold:  # right answer, but is any predicted quote actually on a gold span?
            spans = [_span(f) for f in (x["verified"] if when == "after" else x["merged"])]
            tp_no_overlap += not any(best_jaccard(g, spans) > 0 for g in x["gold"])
        fp += pred and not gold
        fn += gold and not pred
        tn += not gold and not pred
    return {**prf(tp, fp, fn, tn), "tp_without_overlapping_quote": ratio(tp_no_overlap, tp)}


def span_level(cs: list[dict], when: str) -> dict:
    preds_ok = preds = gold_found = gold_touched = gold_n = 0
    for x in cs:
        spans = [_span(f) for f in (x["verified"] if when == "after" else x["merged"])]
        preds += len(spans)
        preds_ok += sum(best_jaccard(s, x["gold"]) >= SPAN_THRESHOLD for s in spans)
        gold_n += len(x["gold"])
        gold_found += sum(best_jaccard(g, spans) >= SPAN_THRESHOLD for g in x["gold"])
        gold_touched += sum(best_jaccard(g, spans) > 0 for g in x["gold"])
    p, r = ratio(preds_ok, preds), ratio(gold_found, gold_n)
    return {"precision": p, "recall": r, "f1": f1_score(p, r),
            "recall_any_overlap": ratio(gold_touched, gold_n)}  # supplementary, more lenient


def no_cuad_match(f: dict, gold: list) -> bool:
    return f["status"] == "failed_quote" or best_jaccard(_span(f), gold) == 0


def review_usefulness(cs: list[dict]) -> dict:
    """(a) findings with no CUAD match and whether the checks moved them to Needs review;
    (b) cells with gold present that were not Verified, by where they landed;
    plus how many Not found results were correct. Reported separately (David's rule)."""
    unmatched = caught = flagged = flagged_unmatched = 0
    caught_by = {"quote_check": 0, "second_pass_reject": 0, "second_pass_failed": 0}
    for x in cs:
        shown = x["merged"] + x["failed_quotes"]
        for f in shown:
            is_unmatched = no_cuad_match(f, x["gold"])
            is_flagged = f["status"] != VERIFIED  # failed quote, rejected, or second pass failed
            unmatched += is_unmatched
            flagged += is_flagged
            flagged_unmatched += is_unmatched and is_flagged
            if is_unmatched and is_flagged:
                caught += 1
                caught_by["quote_check" if f["status"] == "failed_quote"
                          else "second_pass_reject" if f.get("verdict") == "reject"
                          else "second_pass_failed"] += 1
    present = [x for x in cs if x["gold"]]
    missed = [x for x in present if x["status"] != VERIFIED]
    not_found = [x for x in cs if x["status"] == NOT_FOUND]
    return {
        "a_no_cuad_match_findings": {
            "no_cuad_match": unmatched,
            "moved_to_needs_review": ratio(caught, unmatched),
            "left_as_verified": unmatched - caught,
            "caught_by": caught_by,
            "flagged_findings_with_no_cuad_match": ratio(flagged_unmatched, flagged),
        },
        "b_missed_clauses": {
            "cells_with_gold": len(present),
            "missed": len(missed),
            "landed_in_needs_review": sum(x["status"] == NEEDS_REVIEW for x in missed),
            "landed_in_not_found_check": sum(x["status"] == NOT_FOUND for x in missed),
        },
        "not_found_results_correct": ratio(sum(not x["gold"] for x in not_found), len(not_found)),
    }


def quote_check(cs: list[dict]) -> dict:
    raw = [f for x in cs for f in x["raw"]]
    return {"raw_findings": len(raw),
            "failed_quote": ratio(sum(f["status"] == "failed_quote" for f in raw), len(raw)),
            "wrong_category": sum(f["status"] == "wrong_category" for f in raw)}


def second_pass_stats(cs: list[dict], tokens: dict) -> dict:
    merged = [f for x in cs for f in x["merged"]]
    real = [f for f in merged if f.get("second_pass_cached") is False]
    fp_tok = tokens["first_pass_all_calls"]["total_tokens"]
    sp_tok = tokens["second_pass_all_calls"]["total_tokens"]
    return {"checks": len(merged),
            "real_calls": len(real),  # cache hits reuse an earlier verdict: not independent checks
            "rejected": ratio(sum(f.get("verdict") == "reject" for f in merged), len(merged)),
            "failed": sum(f.get("verdict") is None for f in merged),
            "token_share": ratio(sp_tok, fp_tok + sp_tok)}


def score(run: dict, categories: list[str] = config.CATEGORIES, cfg=config) -> dict:
    check_scorable(run["summary"]["run"], cfg)
    cs = list(cells(run["contracts"], categories))

    def block(sub):
        return {"contracts": len({x["title"] for x in sub}),
                "contract_level": {"after_second_pass": contract_level(sub, "after"),
                                   "before_second_pass": contract_level(sub, "before")},
                "span_level": {"after_second_pass": span_level(sub, "after"),
                               "before_second_pass": span_level(sub, "before")},
                "quote_check": quote_check(sub),
                "review_usefulness": review_usefulness(sub),
                "status_counts": {s: sum(x["status"] == s for x in sub)
                                  for s in (VERIFIED, NEEDS_REVIEW, NOT_FOUND)}}

    return {"run": run["summary"]["run"],
            "definitions": {"span_match": f"character-offset Jaccard >= {SPAN_THRESHOLD}",
                            "predicted_after": "cell status Verified",
                            "predicted_before": "any finding that passed the quote check",
                            "no_cuad_match": "failed quote, or span overlaps no gold span of its type (not yet judged wrong: see manual review)",
                            "tp_without_overlapping_quote": "contract-level true positive where no predicted quote overlaps any gold span of that type"},
            "overall": block(cs),
            "per_category": {c: block([x for x in cs if x["category"] == c]) for c in categories},
            "second_pass": second_pass_stats(cs, run["summary"]["tokens"])}


# --- disagreements for manual review -------------------------------------------

ERROR_COLUMNS = ["title", "category", "error_type", "clause_status", "finding_status", "verdict",
                 "pred_start", "pred_end", "best_jaccard", "pred_text", "gold_text", "first_pass_reason",
                 "verdict_reason", "review_label", "review_note"]


def error_rows(run: dict, texts: dict[str, str], categories: list[str] = config.CATEGORIES) -> list[dict]:
    """Every disagreement with gold, one row each. review_label is left blank for the manual
    review (model error / gold label issue / ambiguous)."""
    rows = []
    for x in cells(run["contracts"], categories):
        text = texts.get(x["title"], "")
        gold_text = " || ".join(text[s:e] for s, e in x["gold"])
        base = {"title": x["title"], "category": x["category"], "clause_status": x["status"]}

        def row(kind, f=None, gold=gold_text):
            r = {**base, "error_type": kind, "gold_text": gold}
            if f is not None:
                has_span = f.get("start") is not None
                r.update(finding_status=f["status"], verdict=f.get("verdict"),
                         pred_start=f.get("start"), pred_end=f.get("end"),
                         best_jaccard=round(best_jaccard(_span(f), x["gold"]), 3) if has_span else None,
                         pred_text=text[f["start"]:f["end"]] if has_span else f.get("quote"),
                         first_pass_reason=f.get("reason"), verdict_reason=f.get("verdict_reason"))
            rows.append(r)

        if x["gold"] and x["status"] != VERIFIED:
            row("missed_clause")
        for f in x["merged"]:
            j = best_jaccard(_span(f), x["gold"])
            if f["status"] == VERIFIED and not x["gold"]:
                row("false_positive", f)
            elif f["status"] == VERIFIED and j == 0:
                row("verified_no_cuad_match", f)
            elif f["status"] == VERIFIED and j < SPAN_THRESHOLD:
                row("span_mismatch", f)
            elif f["status"] != VERIFIED and j > 0:
                row("flagged_with_cuad_match", f)
            elif f["status"] != VERIFIED:
                row("flagged_no_cuad_match", f)
        for f in x["failed_quotes"]:
            row("failed_quote", f)
        if x["status"] == VERIFIED:  # contract found, but a gold span untouched by any Verified quote
            spans = [_span(f) for f in x["verified"]]  # (partly touched spans are already span_mismatch rows)
            for s, e in x["gold"]:
                if best_jaccard((s, e), spans) == 0:
                    row("missed_span", gold=text[s:e])
    return rows


# --- command line ----------------------------------------------------------------

def main(name: str) -> None:
    run = json.loads((config.RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    try:
        metrics = score(run)
    except RunNotScorable as e:
        sys.exit(f"Refusing to score {name}: {e}")
    titles = {k["title"] for k in run["contracts"]}
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        texts = {r["title"]: r["text"] for r in map(json.loads, f) if r["title"] in titles}
    rows = error_rows(run, texts)
    prefix = "" if name == "eval" else f"{name}_"
    out_m, out_e = config.RESULTS_DIR / f"{prefix}metrics.json", config.RESULTS_DIR / f"{prefix}errors.csv"
    out_m.write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_e, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ERROR_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(metrics["overall"], indent=1))
    print(f"Wrote {out_m} and {out_e} ({len(rows)} disagreement rows)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python evaluate.py <run name>   (reads results/<run name>.json)")
    main(sys.argv[1])
