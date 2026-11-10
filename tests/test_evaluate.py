"""Stage 4 metrics on a tiny hand-made run. Every expected number is worked out by hand below.

Two clause types (GL = Governing Law, AA = Anti-Assignment), four contracts:

  A  GL gold (100,150)  -> finding (100,150) confirmed: Verified. Exact span.
     AA gold (300,340)  -> finding (300,400) confirmed: Verified. Jaccard 40/100 = 0.4 (too long).
  B  GL gold (10,60)    -> no finding: Not found: check (a miss, by design).
     AA no gold         -> finding (500,550) rejected by second pass: Needs review (wrong, caught).
  C  GL no gold         -> finding (600,650) confirmed: Verified (false positive, slipped through).
     AA gold (0,40), (200,240) -> finding (0,40) confirmed: Verified; (200,240) missed;
                           plus one failed quote: wrong, caught by the quote check.
  D  GL gold (0,50)     -> finding (0,50) rejected: Needs review (correct finding, flagged anyway).
     AA no gold         -> nothing: Not found: check (correct).
"""

import types

import pytest

from evaluate import RunNotScorable, check_scorable, error_rows, score, span_jaccard
from pipeline import NEEDS_REVIEW, NOT_FOUND, VERIFIED

GL, AA = "Governing Law", "Anti-Assignment"
CATS = [GL, AA]
CFG = types.SimpleNamespace(MODEL="m", FIRST_PASS_PROMPT="fp1", SECOND_PASS_PROMPT="sp1", DEFINITIONS="d1")


def found(cat, s, e, verdict, cached=False):
    return {"category": cat, "start": s, "end": e, "chunk": 0, "status": "passed",
            "verdict": verdict, "second_pass_cached": cached, "reason": "r", "verdict_reason": "v",
            "quote": "q"}


def merged(f):
    return {**f, "status": VERIFIED if f["verdict"] == "confirm" else NEEDS_REVIEW}


def contract(title, gold, finds, statuses, failed_quotes=()):
    raw = [dict(f) for f in finds] + [{"category": c, "start": None, "end": None, "chunk": 0,
                                       "status": "failed_quote", "quote": "made up", "reason": "r"}
                                      for c in failed_quotes]
    return {"title": title, "gold": {c: [{"start": s, "end": e} for s, e in gold.get(c, [])] for c in CATS},
            "raw_findings": raw, "findings": [merged(f) for f in finds],
            "clauses": [{"category": c, "status": statuses[c]} for c in CATS]}


def make_run(contracts=None, **run_overrides):
    contracts = contracts or [
        contract("A", {GL: [(100, 150)], AA: [(300, 340)]},
                 [found(GL, 100, 150, "confirm"), found(AA, 300, 400, "confirm")],
                 {GL: VERIFIED, AA: VERIFIED}),
        contract("B", {GL: [(10, 60)]}, [found(AA, 500, 550, "reject")],
                 {GL: NOT_FOUND, AA: NEEDS_REVIEW}),
        contract("C", {AA: [(0, 40), (200, 240)]},
                 [found(GL, 600, 650, "confirm"), found(AA, 0, 40, "confirm", cached=True)],
                 {GL: VERIFIED, AA: VERIFIED}, failed_quotes=[AA]),
        contract("D", {GL: [(0, 50)]}, [found(GL, 0, 50, "reject")],
                 {GL: NEEDS_REVIEW, AA: NOT_FOUND}),
    ]
    info = {"model": "m", "first_pass_prompt": "fp1", "second_pass_prompt": "sp1", "definitions": "d1",
            "complete": True, "stopped_reason": None, **run_overrides}
    tokens = {"first_pass_all_calls": {"total_tokens": 700}, "second_pass_all_calls": {"total_tokens": 300}}
    return {"summary": {"run": info, "tokens": tokens}, "contracts": contracts}


@pytest.fixture
def m():
    return score(make_run(), CATS, CFG)


def counts(r):
    return (r["n"], r["of"])


# --- span measure --------------------------------------------------------------

def test_span_jaccard():
    assert span_jaccard((0, 10), (0, 10)) == 1.0
    assert span_jaccard((0, 10), (10, 20)) == 0.0          # touching is not overlapping
    assert span_jaccard((300, 400), (300, 340)) == 0.4     # quote too long
    assert span_jaccard((0, 10), (5, 15)) == 5 / 15


# --- refusal rules ---------------------------------------------------------------

def test_refuses_incomplete_run():
    with pytest.raises(RunNotScorable, match="incomplete"):
        score(make_run(complete=False, stopped_reason="daily limit"), CATS, CFG)


@pytest.mark.parametrize("key", ["model", "first_pass_prompt", "second_pass_prompt", "definitions"])
def test_refuses_mismatched_versions(key):
    with pytest.raises(RunNotScorable, match=key):
        score(make_run(**{key: "other"}), CATS, CFG)


def test_refuses_run_without_complete_flag():
    info = make_run()["summary"]["run"]
    del info["complete"]
    with pytest.raises(RunNotScorable):
        check_scorable(info, CFG)


# --- contract level -----------------------------------------------------------------

def test_contract_level_after_second_pass(m):
    gl = m["per_category"][GL]["contract_level"]["after_second_pass"]
    assert (gl["tp"], gl["fp"], gl["fn"], gl["tn"]) == (1, 1, 2, 0)        # A tp, C fp, B+D fn
    assert counts(gl["precision"]) == (1, 2) and counts(gl["recall"]) == (1, 3)
    assert gl["f1"] == round(2 * 0.5 * (1 / 3) / (0.5 + 1 / 3), 4)
    aa = m["per_category"][AA]["contract_level"]["after_second_pass"]
    assert (aa["tp"], aa["fp"], aa["fn"], aa["tn"]) == (2, 0, 0, 2)        # B's Needs review is not a positive
    ov = m["overall"]["contract_level"]["after_second_pass"]
    assert (ov["tp"], ov["fp"], ov["fn"], ov["tn"]) == (3, 1, 2, 2)


def test_contract_level_before_second_pass(m):
    gl = m["per_category"][GL]["contract_level"]["before_second_pass"]
    assert (gl["tp"], gl["fp"], gl["fn"]) == (2, 1, 1)                     # D's rejected finding counts before
    aa = m["per_category"][AA]["contract_level"]["before_second_pass"]
    assert (aa["tp"], aa["fp"], aa["fn"], aa["tn"]) == (2, 1, 0, 1)        # B's rejected finding was an fp


# --- span level ---------------------------------------------------------------------

def test_span_level(m):
    gl = m["per_category"][GL]["span_level"]["after_second_pass"]
    assert counts(gl["precision"]) == (1, 2) and counts(gl["recall"]) == (1, 3)
    aa = m["per_category"][AA]["span_level"]["after_second_pass"]
    assert counts(aa["precision"]) == (1, 2)          # (300,400) has Jaccard 0.4: not a match
    assert counts(aa["recall"]) == (1, 3)
    assert counts(aa["recall_any_overlap"]) == (2, 3)  # A's span is touched, C's (200,240) is not
    gl_before = m["per_category"][GL]["span_level"]["before_second_pass"]
    assert counts(gl_before["precision"]) == (2, 3) and counts(gl_before["recall"]) == (2, 3)
    aa_before = m["per_category"][AA]["span_level"]["before_second_pass"]
    assert counts(aa_before["precision"]) == (1, 3) and counts(aa_before["recall"]) == (1, 3)


def test_verified_contract_with_missed_span_shows_in_span_recall_only(m):
    # C/AA is a contract-level true positive, yet one of its two gold spans is missed
    assert m["per_category"][AA]["contract_level"]["after_second_pass"]["fn"] == 0
    assert counts(m["per_category"][AA]["span_level"]["after_second_pass"]["recall"]) == (1, 3)


# --- quote check, second pass ---------------------------------------------------------

def test_quote_check(m):
    assert counts(m["overall"]["quote_check"]["failed_quote"]) == (1, 7)  # 6 passed + 1 failed


def test_second_pass_stats(m):
    sp = m["second_pass"]
    assert sp["checks"] == 6 and sp["real_calls"] == 5                     # C's AA verdict was a cache hit
    assert counts(sp["rejected"]) == (2, 6) and sp["failed"] == 0
    assert counts(sp["token_share"]) == (300, 1000)


# --- review usefulness ----------------------------------------------------------------

def test_review_usefulness_a_no_cuad_match(m):
    a = m["overall"]["review_usefulness"]["a_no_cuad_match_findings"]
    # no CUAD match: B/AA (no gold), C/GL (no gold), C/AA failed quote. A/AA overlaps gold, so it matches.
    assert a["no_cuad_match"] == 3
    assert counts(a["moved_to_needs_review"]) == (2, 3)
    assert a["left_as_verified"] == 1
    assert a["caught_by"] == {"quote_check": 1, "second_pass_reject": 1, "second_pass_failed": 0}
    # flagged: B/AA, C failed quote, D/GL (D/GL was actually correct)
    assert counts(a["flagged_findings_with_no_cuad_match"]) == (2, 3)


def test_review_usefulness_b_missed_clauses_and_not_found(m):
    u = m["overall"]["review_usefulness"]
    assert u["b_missed_clauses"] == {"cells_with_gold": 5, "missed": 2,
                                     "landed_in_needs_review": 1,       # D/GL
                                     "landed_in_not_found_check": 1}    # B/GL
    assert counts(u["not_found_results_correct"]) == (1, 2)             # D/AA right, B/GL wrong


def test_status_counts(m):
    assert m["overall"]["status_counts"] == {VERIFIED: 4, NEEDS_REVIEW: 2, NOT_FOUND: 2}


# --- errors.csv rows ---------------------------------------------------------------------

def test_error_rows():
    texts = {t: "x" * 700 for t in "ABCD"}
    rows = error_rows(make_run(), texts, CATS)
    kinds = sorted((r["title"], r["category"], r["error_type"]) for r in rows)
    assert kinds == sorted([
        ("A", AA, "span_mismatch"),
        ("B", GL, "missed_clause"),
        ("B", AA, "flagged_no_cuad_match"),
        ("C", GL, "false_positive"),
        ("C", AA, "failed_quote"),
        ("C", AA, "missed_span"),
        ("D", GL, "missed_clause"),
        ("D", GL, "flagged_with_cuad_match"),
    ])
    assert all(r.get("review_label") is None for r in rows)  # left blank for the manual review
    assert not any("wrong" in r["error_type"] for r in rows)   # "no CUAD match" until reviewed


# --- right contract-level answer, but no quote on a gold span -----------------------------

def test_tp_without_overlapping_quote_counted(m):
    # in the main example every true positive has a quote overlapping gold (A/AA overlaps at 0.4)
    assert counts(m["overall"]["contract_level"]["after_second_pass"]["tp_without_overlapping_quote"]) == (0, 3)


def test_tp_without_overlapping_quote():
    # E: GL gold (0,50) but the Verified quote is elsewhere (100,150): a contract-level "hit" by luck.
    #    AA gold (200,240), Verified quote (210,300): overlaps, so it does not count.
    e = contract("E", {GL: [(0, 50)], AA: [(200, 240)]},
                 [found(GL, 100, 150, "confirm"), found(AA, 210, 300, "confirm")],
                 {GL: VERIFIED, AA: VERIFIED})
    res = score(make_run([e]), CATS, CFG)
    after = res["overall"]["contract_level"]["after_second_pass"]
    assert after["tp"] == 2 and counts(after["tp_without_overlapping_quote"]) == (1, 2)
    assert counts(res["per_category"][GL]["contract_level"]["after_second_pass"]
                  ["tp_without_overlapping_quote"]) == (1, 1)
    rows = error_rows(make_run([e]), {"E": "x" * 400}, CATS)
    assert ("verified_no_cuad_match", "missed_span") == tuple(
        r["error_type"] for r in rows if r["category"] == GL)


# --- connection/server failures refuse scoring; invalid model replies are scored ----------------

def _with_errors(chunk_error=None, second_pass_error=None):
    run = make_run()
    a = run["contracts"][0]
    if chunk_error:
        a["errors"] = [{"chunk": 1, "error": chunk_error}]
    if second_pass_error:
        a["findings"][0] = {**a["findings"][0], "status": NEEDS_REVIEW, "verdict": None,
                            "second_pass_error": second_pass_error}
    return run


def test_refuses_run_with_connection_failed_chunk():
    run = _with_errors(chunk_error="CallFailed: APIConnectionError: Connection error.")
    with pytest.raises(RunNotScorable, match="connection or server error"):
        score(run, CATS, CFG)


def test_refuses_run_with_server_failed_second_pass():
    run = _with_errors(second_pass_error="CallFailed: InternalServerError: 503")
    with pytest.raises(RunNotScorable, match="connection or server error"):
        score(run, CATS, CFG)


def test_invalid_model_replies_are_scored_and_counted():
    run = _with_errors(chunk_error="InvalidResponse: attempt 1: bad json; attempt 2: bad json",
                       second_pass_error="InvalidResponse: attempt 2: no verdict")
    m = score(run, CATS, CFG)  # not refused
    inv = m["invalid_model_replies"]
    assert inv["first_pass_chunks"] == 1 and inv["second_pass_checks"] == 1 and len(inv["parts"]) == 2
    # the finding whose check returned an invalid reply is Needs review, not Verified
    assert m["second_pass"]["failed"] == 1


def test_clean_run_reports_zero_invalid_replies(m):
    assert m["invalid_model_replies"]["first_pass_chunks"] == 0
    assert m["invalid_model_replies"]["second_pass_checks"] == 0
