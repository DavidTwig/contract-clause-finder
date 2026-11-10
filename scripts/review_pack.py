"""Build the manual-review pack and the failed-quote comparison from the scored eval run.

Run:  .venv/Scripts/python scripts/review_pack.py
Reads results/eval.json and data/contracts.jsonl (no API calls). Writes:
  results/failed_quote_diffs.json   for each failed quote: the closest contract passage, the exact
                                    word differences, and whether that passage overlaps CUAD gold
  results/review_pack.md            numbered cases for the manual review (no labels suggested)

Case selection is fixed by rule, not picked by hand:
  - Termination for Convenience false positives: all (Verified, no CUAD gold for that type)
  - Verified findings with no CUAD match in contracts that do have gold of that type: all
  - failed quotes: all
  - Not found: check where CUAD marks the clause: all
  - Cap on Liability gold spans untouched by any Verified quote, in contracts Verified for Cap:
    3, taken from each such contract in turn (eval-title order, then span order)
"""

import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from evaluate import span_jaccard
from first_pass import load_definitions
from pipeline import NOT_FOUND, VERIFIED

CONTEXT = 150  # characters shown before and after the passage (about 300 in total)
OUT_DIFFS = config.RESULTS_DIR / "failed_quote_diffs.json"
OUT_PACK = config.RESULTS_DIR / "review_pack.md"


def words(s: str) -> list[tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", s)]


def closest_passage(quote: str, text: str) -> tuple[int, int, float]:
    """Contract span best matching the quote, by word sequence. Returns (start, end, similarity)."""
    qw = [w for w, _, _ in words(quote)]
    tw = words(text)
    tokens = [w for w, _, _ in tw]
    best = (0, 0, 0.0)
    n = len(qw)
    for size in (n, n - 2, n + 2, n - 5, n + 5):  # allow a few words dropped or added
        if size <= 0:
            continue
        for i in range(0, max(1, len(tokens) - size + 1)):
            ratio = difflib.SequenceMatcher(None, qw, tokens[i:i + size], autojunk=False).ratio()
            if ratio > best[2]:
                best = (i, min(i + size, len(tw)), ratio)
    i0, i1, ratio = best
    # trim contract words at either edge that the quote does not contain (window artefacts)
    ops = difflib.SequenceMatcher(None, qw, tokens[i0:i1], autojunk=False).get_opcodes()
    if ops and ops[0][0] == "insert":
        i0 += ops[0][4] - ops[0][3]
    if ops and ops[-1][0] == "insert":
        i1 -= ops[-1][4] - ops[-1][3]
    ratio = difflib.SequenceMatcher(None, qw, tokens[i0:i1], autojunk=False).ratio()
    return tw[i0][1], tw[i1 - 1][2], ratio


def word_diff(quote: str, passage: str) -> list[dict]:
    q, p = [w for w, _, _ in words(quote)], [w for w, _, _ in words(passage)]
    out = []
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, q, p, autojunk=False).get_opcodes():
        if op != "equal":
            out.append({"change": op, "model_quote": " ".join(q[a0:a1]), "contract": " ".join(p[b0:b1])})
    return out


def readable(s: str) -> str:
    """Collapse runs of spaces and blank lines, for reading only."""
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def context(text: str, start: int, end: int) -> str:
    s, e = max(0, start - CONTEXT), min(len(text), end + CONTEXT)
    return (("…" if s else "") + readable(text[s:start]) + " »" + readable(text[start:end]) + "« "
            + readable(text[end:e]) + ("…" if e < len(text) else ""))


def block(s: str) -> str:
    """A quoted block that wraps in any Markdown viewer; Markdown characters are escaped so the
    contract text shows exactly as written."""
    if not s:
        return "> (none)"
    s = re.sub(r"([\\`*_#\[\]<>|~])", r"\\\1", s)
    return "\n".join("> " + (line if line.strip() else "") for line in s.split("\n"))


def main():
    run = json.loads((config.RESULTS_DIR / "eval.json").read_text(encoding="utf-8"))
    titles = {k["title"] for k in run["contracts"]}
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        texts = {r["title"]: r["text"] for r in map(json.loads, f) if r["title"] in titles}
    defs = load_definitions()

    cases, diffs = [], []
    for k in run["contracts"]:
        text = texts[k["title"]]
        status = {cl["category"]: cl["status"] for cl in k["clauses"]}
        for c in config.CATEGORIES:
            gold = [(g["start"], g["end"]) for g in k["gold"][c]]
            ver = [f for f in k["findings"] if f["category"] == c and f["status"] == VERIFIED]
            base = {"title": k["title"], "category": c, "definition": defs[c], "status": status[c], "text": text,
                    "gold": gold}
            for f in ver:
                touches = any(span_jaccard((f["start"], f["end"]), g) > 0 for g in gold)
                if not gold and c == "Termination for Convenience":
                    cases.append({**base, "kind": "A. Termination for Convenience: Verified, no CUAD gold", "f": f})
                elif gold and not touches:
                    cases.append({**base, "kind": "B. Verified finding with no CUAD match (CUAD marks this type elsewhere)",
                                  "f": f})
            for f in k["raw_findings"]:
                if f["category"] == c and f["status"] == "failed_quote":
                    s, e, sim = closest_passage(f["quote"], text)
                    over = [g for g in gold if span_jaccard((s, e), g) > 0]
                    d = {"title": k["title"], "category": c, "model_quote": f["quote"],
                         "closest_contract_passage": text[s:e], "start": s, "end": e,
                         "word_similarity": round(sim, 3), "differences": word_diff(f["quote"], text[s:e]),
                         "passage_overlaps_cuad_gold": bool(over), "cuad_gold_for_type": bool(gold)}
                    diffs.append(d)
                    cases.append({**base, "kind": "C. Failed quote (not found word for word)", "f": f, "diff": d})
            if gold and status[c] == NOT_FOUND:
                cases.append({**base, "kind": "D. Not found: check, but CUAD marks this clause"})
    cap_misses = []
    for k in run["contracts"]:
        c = "Cap on Liability"
        st = next(cl["status"] for cl in k["clauses"] if cl["category"] == c)
        if st != VERIFIED:
            continue
        ver = [(f["start"], f["end"]) for f in k["findings"] if f["category"] == c and f["status"] == VERIFIED]
        for g in k["gold"][c]:
            gs = (g["start"], g["end"])
            if not any(span_jaccard(gs, v) > 0 for v in ver):
                cap_misses.append({"title": k["title"], "category": c, "definition": defs[c], "status": st,
                                   "text": texts[k["title"]], "gold": [gs],
                                   "kind": "E. Cap on Liability span missed in a contract Verified for Cap",
                                   "verified": [f for f in k["findings"] if f["category"] == c and f["status"] == VERIFIED]})
    n_cap_misses = len(cap_misses)
    # take misses from each contract in turn (eval-title order), so one contract can't fill all 3 places
    by_contract: dict[str, list] = {}
    for m in cap_misses:
        by_contract.setdefault(m["title"], []).append(m)
    picked, rnd = [], 0
    while len(picked) < 3 and any(len(v) > rnd for v in by_contract.values()):
        picked += [v[rnd] for v in by_contract.values() if len(v) > rnd][:3 - len(picked)]
        rnd += 1
    cases += picked

    OUT_DIFFS.write_text(json.dumps(diffs, ensure_ascii=False, indent=1), encoding="utf-8")

    order = "ABCDE"
    cases.sort(key=lambda x: order.index(x["kind"][0]))  # stable: eval-title order within each group
    lines = ["# Manual review pack (eval)", "",
             "For each case, reply with: **number: model error / gold label issue / ambiguous, short note**.",
             "",
             "Source: `results/eval.json` (eval attempt 2, complete) and `data/contracts.jsonl`. Built by "
             "`scripts/review_pack.py`; no API calls. Definitions are CUAD's (`category_definitions_v4`). "
             "Spaces and blank lines in contract text are collapsed for reading only. In the context, "
             "»…« marks the passage the case is about. Selection rules are in the script docstring.",
             "", f"Cap on Liability gold spans missed in Verified contracts: {n_cap_misses} in total, in "
             f"{len(by_contract)} contracts; 3 are included, taken from each contract in turn.", ""]
    current = None
    for i, x in enumerate(cases, 1):
        if x["kind"] != current:
            current = x["kind"]
            lines += ["---", "", f"## {current}", ""]
        text = x["text"]
        lines += [f"### Case {i}: {x['category']}, {x['title']}", "",
                  f"**Status shown:** {x['status']}", "", f"**CUAD definition:** {x['definition']}", ""]
        f = x.get("f")
        if f is not None:
            q = text[f["start"]:f["end"]] if f.get("start") is not None else f["quote"]
            lines += ["**Model's quote:**", block(readable(q)), "", f"**Model's reason:** {f.get('reason') or '(none)'}", ""]
            if f.get("verdict_reason"):
                lines += [f"**Second review ({f.get('verdict')}):** {f['verdict_reason']}", ""]
        if "diff" in x:
            d = x["diff"]
            lines += [f"**Closest contract passage** (word similarity {d['word_similarity']}):",
                      block(readable(d["closest_contract_passage"])), "", "**What differs (model's quote → contract):**", ""]
            lines += [f"- {c['change']}: “{c['model_quote']}” → “{c['contract']}”" for c in d["differences"]] or ["- (no word differences: spacing only)"]
            lines += ["", f"**Closest passage overlaps CUAD's marked text for this type:** "
                          f"{'yes' if d['passage_overlaps_cuad_gold'] else 'no'}", ""]
        if x["kind"].startswith("E"):
            for v in x["verified"]:
                lines += ["**Model's Verified Cap on Liability quote in this contract (for reference):**",
                          block(readable(text[v["start"]:v["end"]])), ""]
            lines += ["**Model's quote for this span:** none", ""]
        if x["kind"].startswith("D"):
            lines += ["**Model's quote:** none (no finding of this type in this contract)", ""]
        gold_text = [readable(text[s:e]) for s, e in x["gold"]]
        lines += [f"**CUAD's marked text for this type** ({len(gold_text)} span{'s' if len(gold_text) != 1 else ''}):",
                  block("\n\n(next span)\n\n".join(gold_text)), ""]
        if f is not None and f.get("start") is not None:
            anchor = (f["start"], f["end"])
        elif "diff" in x:
            anchor = (x["diff"]["start"], x["diff"]["end"])
        else:
            anchor = x["gold"][0]
        lines += ["**Surrounding contract text:**", block(context(text, *anchor)), "",
                  "**Your label:** ______  **Note:** ______", ""]
    OUT_PACK.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(cases)} cases -> {OUT_PACK}; {len(diffs)} failed quotes -> {OUT_DIFFS}")
    for d in diffs:
        print(f"\n{d['title'][:45]} | {d['category']} | similarity {d['word_similarity']} | "
              f"overlaps CUAD gold: {d['passage_overlaps_cuad_gold']} | CUAD gold for type: {d['cuad_gold_for_type']}")
        for c in d["differences"]:
            print(f"   {c['change']}: {c['model_quote']!r} -> {c['contract']!r}")


if __name__ == "__main__":
    main()
