"""Full pipeline for one contract: first pass, quote check, merge, second pass, statuses."""

import config
import llm
from first_pass import load_definitions, neutralise_tags, run_first_pass
from splitter import HEADING, find_cut_points

VERIFIED = "Verified"
NEEDS_REVIEW = "Needs review"
NOT_FOUND = "Not found: check"

# Every wrapper tag used by either pass. Contract text in the second pass must not contain any of them.
_TAG_NAMES = ("quote", "contract_section", "contract_text")


# --- Merging duplicates from chunk overlap ---------------------------------

def _overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def merge_duplicates(findings: list[dict]) -> list[dict]:
    """Merge passed findings of the SAME clause type whose spans overlap; keep the longest.

    Findings of different clause types are never compared. Only "passed" findings have
    offsets, so only they can be merged. Each kept finding lists the chunks it came from.
    """
    kept: list[dict] = []
    passed = [f for f in findings if f["status"] == "passed"]
    # longest first, so the kept copy of a duplicate group is the most complete quote
    for f in sorted(passed, key=lambda f: (-(f["end"] - f["start"]), f["chunk"], f["start"])):
        dup = next((k for k in kept if k["category"] == f["category"] and _overlaps(k, f)), None)
        if dup:
            dup["merged_from_chunks"].append(f["chunk"])
        else:
            kept.append({**f, "merged_from_chunks": [f["chunk"]]})
    for k in kept:
        k["merged_from_chunks"].sort()
    return sorted(kept, key=lambda k: (k["start"], k["category"]))


# --- Second pass -----------------------------------------------------------

def section_around(text: str, start: int, end: int,
                   max_side: int = config.SECTION_MAX_SIDE_CHARS) -> tuple[int, int]:
    """The section containing text[start:end]: from the last heading at or before `start`
    to the next heading after `end`, capped at max_side chars each side. When capped,
    the edge moves to the nearest cut point inside the cap, so it does not split a word."""
    cuts = find_cut_points(text)
    headings = [p for p, s in cuts.items() if s == HEADING]
    sec_start = max([p for p in headings if p <= start], default=0)
    sec_end = min([p for p in headings if p >= end], default=len(text))
    if start - sec_start > max_side:
        lo = start - max_side
        sec_start = min([p for p in cuts if lo <= p <= start], default=lo)
    if sec_end - end > max_side:
        hi = end + max_side
        sec_end = max([p for p in cuts if end <= p <= hi], default=hi)
    return sec_start, sec_end


def _neutralise_all(text: str) -> str:
    return neutralise_tags(text, _TAG_NAMES)[0]


def build_second_pass_messages(quote: str, section: str, category: str) -> list[dict]:
    definition = load_definitions()[category]  # definition only: no first-pass quote guidance
    system = (config.PROMPTS_DIR / f"{config.SECOND_PASS_PROMPT}_system.txt").read_text(encoding="utf-8")
    user = (config.PROMPTS_DIR / f"{config.SECOND_PASS_PROMPT}_user.txt").read_text(encoding="utf-8")
    system = system.replace("{category}", category).replace("{definition}", definition)
    user = user.replace("{quote}", _neutralise_all(quote)).replace("{section}", _neutralise_all(section))
    return [{"role": "system", "content": system.strip()}, {"role": "user", "content": user.strip()}]


def validate_verdict(data) -> None:
    if not isinstance(data, dict) or data.get("verdict") not in ("confirm", "reject"):
        raise ValueError('expected {"verdict": "confirm" | "reject", ...}')
    if not isinstance(data.get("reason"), str):
        raise ValueError('expected a text "reason"')


def second_pass(text: str, finding: dict) -> dict:
    """Ask the model to confirm or reject one finding. Returns fields to add to the finding.
    A failed call gives verdict None: the finding becomes Needs review, never deleted."""
    s, e = section_around(text, finding["start"], finding["end"])
    quote_text = text[finding["start"]:finding["end"]]  # the exact contract wording, not the model's copy
    messages = build_second_pass_messages(quote_text, text[s:e], finding["category"])
    try:
        reply = llm.chat_json(messages, config.SECOND_PASS_PROMPT, validate_verdict)
    except (llm.InvalidResponse, llm.CallFailed) as err:
        return {"section_start": s, "section_end": e, "verdict": None,
                "verdict_reason": None, "second_pass_error": f"{type(err).__name__}: {err}",
                "second_pass_usage": None, "second_pass_cached": None}
    return {"section_start": s, "section_end": e, "verdict": reply["data"]["verdict"],
            "verdict_reason": reply["data"]["reason"], "second_pass_error": None,
            "second_pass_usage": reply["usage"], "second_pass_cached": reply["cached"]}


# --- Status logic ----------------------------------------------------------

def finding_status(finding: dict) -> str:
    """Verified only if the quote passed AND the second pass confirmed. Anything else: Needs review."""
    return VERIFIED if finding.get("verdict") == "confirm" else NEEDS_REVIEW


def clause_status(category: str, merged: list[dict], raw: list[dict], failed_chunks: list[int]) -> dict:
    """Status for one clause type in one contract, with every reason that applies."""
    mine = [f for f in merged if f["category"] == category]
    n_verified = sum(1 for f in mine if f["status"] == VERIFIED)
    n_review = sum(1 for f in mine if f["status"] == NEEDS_REVIEW)
    n_failed_quotes = sum(1 for f in raw if f["category"] == category and f["status"] == "failed_quote")
    reasons = []
    if n_verified:
        reasons.append(f"{n_verified} verified finding(s)")
    if n_review:
        reasons.append(f"{n_review} finding(s) not confirmed by second pass")
    if n_failed_quotes:
        reasons.append(f"{n_failed_quotes} quote(s) failed the quote check")
    if failed_chunks:
        reasons.append(f"chunk(s) {failed_chunks} could not be analysed")

    if n_verified:
        status = VERIFIED
    elif n_review or n_failed_quotes or failed_chunks:
        status = NEEDS_REVIEW
    else:
        status = NOT_FOUND
        reasons.append("no finding")
    return {"category": category, "status": status, "reasons": reasons,
            "n_verified": n_verified, "n_needs_review": n_review, "n_failed_quotes": n_failed_quotes}


# --- One contract ----------------------------------------------------------

def analyse_contract(text: str, categories: list[str] = config.CATEGORIES) -> dict:
    """Run everything on one contract. llm.DailyLimitReached propagates: the caller must stop."""
    first = run_first_pass(text, categories)
    merged = merge_duplicates(first["findings"])
    for f in merged:
        f.update(second_pass(text, f))
        f["status"] = finding_status(f)
    failed_chunks = [c["index"] for c in first["chunks"] if c["status"] == "failed"]
    clauses = [clause_status(c, merged, first["findings"], failed_chunks) for c in categories]
    return {"chunks": first["chunks"], "raw_findings": first["findings"], "findings": merged,
            "clauses": clauses, "failed_chunks": failed_chunks, "errors": first["errors"]}
