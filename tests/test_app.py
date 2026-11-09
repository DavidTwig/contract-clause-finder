"""The Streamlit app, with no real API calls: the network call fails if anything reaches it."""

import io
import json

import pytest

import app
import config
import llm
from pipeline import NEEDS_REVIEW, NOT_FOUND, VERIFIED


@pytest.fixture(autouse=True)
def no_api(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_call_once", lambda *a, **k: pytest.fail("real API call attempted"))
    monkeypatch.setattr(llm, "RESPONSE_CACHE", tmp_path / "responses")
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage_log.jsonl")


# --- uploads -------------------------------------------------------------------------

def test_read_txt_and_bad_files():
    assert app.read_upload("a.TXT", "Governed by Texas law.".encode("utf-8")) == "Governed by Texas law."
    assert app.read_upload("a.txt", "Café".encode("cp1252")) == "Café"   # non-UTF-8 still readable
    with pytest.raises(ValueError, match=".txt or .docx"):
        app.read_upload("a.pdf", b"%PDF")
    with pytest.raises(ValueError, match="no text"):
        app.read_upload("a.txt", b"   \n ")
    with pytest.raises(ValueError, match="Word file"):
        app.read_upload("a.docx", b"not a zip")


def test_read_docx_paragraphs_and_tables():
    import docx
    d = docx.Document()
    d.add_paragraph("1. Law. This Agreement is governed by the laws of Texas.")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Term", "One year"
    buf = io.BytesIO()
    d.save(buf)
    text = app.read_upload("contract.docx", buf.getvalue())
    assert "governed by the laws of Texas" in text and "Term | One year" in text


# --- the sample -------------------------------------------------------------------------

def test_sample_is_a_dev_contract_and_matches_current_prompts():
    data, text = app.load_sample()
    assert data["title"] in json.loads(config.DEV_TITLES_PATH.read_text(encoding="utf-8"))
    assert data["title"] not in json.loads(config.EVAL_TITLES_PATH.read_text(encoding="utf-8"))
    assert data["versions"] == app.current_versions()
    assert data["result"]["failed_chunks"] == []
    assert len(text) == 14_313


def test_sample_rows_show_wording_and_unconfirmed_not_found():
    data, text = app.load_sample()
    rows = app.build_rows(data["result"], text)
    # Not found first, then the Verified ones in the usual clause-type order
    assert [r["Clause type"] for r in rows] == ["Cap on Liability", "Change of Control",
                                                 "Termination for Convenience", "Anti-Assignment", "Governing Law"]
    for r in rows:
        assert r["Status"] == app.STATUS_TEXT[r["status"]]          # status always in words
        if r["start"] is not None:
            assert r["Exact wording"] == text[r["start"]:r["end"]]  # exact contract wording
    cap = next(r for r in rows if r["Clause type"] == "Cap on Liability")
    assert cap["Status"] == "Not found: check" and "Unconfirmed" in cap["Why"]


# --- rows for the other statuses -----------------------------------------------------------

def test_rows_for_rejected_failed_quote_and_failed_chunk():
    text = "Neither party may assign this Agreement. Texas law governs."
    result = {
        "findings": [{"category": "Anti-Assignment", "start": 0, "end": 40, "status": NEEDS_REVIEW,
                      "verdict": "reject", "verdict_reason": "about subcontracting", "reason": "assignment"}],
        "raw_findings": [{"category": "Governing Law", "status": "failed_quote",
                          "quote": "Delaware law governs.", "reason": "law"}],
        "clauses": [{"category": "Anti-Assignment", "status": NEEDS_REVIEW},
                    {"category": "Governing Law", "status": NEEDS_REVIEW},
                    {"category": "Cap on Liability", "status": NEEDS_REVIEW}],  # failed chunk
        "failed_chunks": [1],
    }
    ordered = app.build_rows(result, text)
    rows = {r["Clause type"]: r for r in ordered}
    assert "Second review disagreed: about subcontracting" in rows["Anti-Assignment"]["Why"]
    gl = rows["Governing Law"]
    assert gl["Status"] == "Needs review" and gl["start"] is None
    assert "Not found word for word" in gl["Exact wording"] and "Delaware" in gl["Exact wording"]
    assert "could not be analysed" in rows["Cap on Liability"]["Why"]


def test_rows_ordered_needs_review_then_not_found_then_verified():
    text = "a" * 100
    result = {
        "findings": [{"category": "Governing Law", "start": 0, "end": 5, "status": VERIFIED,
                      "verdict": "confirm", "reason": "r"},
                     {"category": "Anti-Assignment", "start": 10, "end": 20, "status": NEEDS_REVIEW,
                      "verdict": "reject", "verdict_reason": "v", "reason": "r"}],
        "raw_findings": [],
        "clauses": [{"category": "Change of Control", "status": NOT_FOUND},
                    {"category": "Anti-Assignment", "status": NEEDS_REVIEW},
                    {"category": "Governing Law", "status": VERIFIED},
                    {"category": "Cap on Liability", "status": NOT_FOUND}],
        "failed_chunks": [],
    }
    rows = app.build_rows(result, text)
    assert [(r["status"], r["Clause type"]) for r in rows] == [
        (NEEDS_REVIEW, "Anti-Assignment"), (NOT_FOUND, "Change of Control"),
        (NOT_FOUND, "Cap on Liability"), (VERIFIED, "Governing Law")]
    assert app.summary_line(result) == "1 clause type verified, 3 to check yourself (1 needs review, 2 not found)"


def test_summary_line_counts_clause_types():
    data, _ = app.load_sample()
    assert app.summary_line(data["result"]) == "4 clause types verified, 1 to check yourself (1 not found)"
    all_ok = {"clauses": [{"category": c, "status": VERIFIED} for c in config.CATEGORIES]}
    assert app.summary_line(all_ok) == "5 clause types verified, 0 to check yourself"


def test_long_wording_is_not_cut_and_is_escaped():
    long = "IN NO EVENT SHALL <b>LICENSOR</b> BE LIABLE " * 40
    out = app._cell(long)
    assert "white-space: pre-wrap" in out and "&lt;b&gt;LICENSOR&lt;/b&gt;" in out
    assert out.count("IN NO EVENT SHALL") == 40   # nothing truncated


def test_context_is_escaped_and_highlighted():
    text = "<script>alert(1)</script> before. Texas law governs. after"
    s = text.index("Texas")
    out = app.context_html(text, s, s + len("Texas law governs."))
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert ('<mark style="background:#ffe066; color:#111; border-bottom: 2px solid #8a6100;">'
            'Texas law governs.</mark>') in out


def test_light_theme_config():
    import tomllib
    theme = tomllib.loads((config.ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    assert theme["base"] == "light"


def test_badges_have_a_visible_border():
    for status in (VERIFIED, NEEDS_REVIEW, NOT_FOUND):
        badge = app._badge(status)
        assert f"border:1px solid {app.STATUS_BORDER[status]}" in badge and "color:#111" in badge


# --- running an upload: limits and progress --------------------------------------------------

def test_daily_limit_message(monkeypatch):
    def limit(*a, **k):
        raise llm.DailyLimitReached("retry-after 3600s")
    monkeypatch.setattr(llm, "_call_once", limit)
    result, error = app.run_analysis("1. Law. This Agreement is governed by the laws of Texas.")
    assert result is None and "Daily limit reached" in error


def test_rate_limit_message(monkeypatch):
    def busy(*a, **k):
        raise RuntimeError("Still rate limited after 10 attempts")
    monkeypatch.setattr(llm, "_call_once", busy)
    result, error = app.run_analysis("1. Law. This Agreement is governed by the laws of Texas.")
    assert result is None and "Rate limit" in error


def test_progress_messages():
    assert "1 AI reply" in app.progress_message("tokens: prompt 1, completion 1", 1)
    assert "about 59 s" in app.progress_message("throttle: 7,000 tokens in last minute, waiting 59s", 0)
    assert "wait 30 s" in app.progress_message("429 rate limit: retry-after 30s", 0)
    assert app.progress_message("something else", 0) is None


def test_token_estimate_range():
    assert app.token_estimate("x" * 40_000) == (14_000, 25_000)


# --- the page itself -------------------------------------------------------------------------

def _page():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=30).run()


def _all_text(at) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def test_page_renders_sample_instantly_without_api():
    at = _page()
    assert not at.exception
    assert any("Prototype" in w.value and "confidential" in w.value for w in at.warning)
    note = " ".join(i.value for i in at.info)
    assert "word for word" in note and "does **not** mean every relevant clause" in note
    assert "**unconfirmed**" in note
    text = _all_text(at)
    assert "**Sample:** Trademark License Agreement (public filing, from the CUAD dataset)" in text
    assert "From the public CUAD dataset (CC BY 4.0). This is a saved result, so no AI call is made." in text
    data, _ = app.load_sample()
    assert data["title"] not in text and "HertzGroup" not in text      # no filename in the main view
    assert "**4 clause types verified, 1 to check yourself (1 not found)**" in text
    for label in ("Clause type", "Status", "Exact wording", "Why"):
        assert f'<div class="cc-head">{label}</div>' in text           # header row
    assert text.count("<style>") == 1 and "st-key-reshead_" in text   # table styling added once
    # statuses in words, in order: the Not found row before the Verified rows
    import re
    badges = re.findall(r'border-radius:4px[^>]*>([^<]+)</span>', text)
    assert badges == ["Not found: check"] + ["Verified"] * 4
    # every cell carries its own label for narrow windows
    assert text.count('<div class="cc-label">Exact wording</div>') == 5
    # full wording shown, wrapping, not cut off
    words = [r["Exact wording"] for r in app.build_rows(data["result"], app.load_sample()[1]) if r["Exact wording"]]
    longest = max(words, key=len)
    assert any(app._cell(longest) in m.value for m in at.markdown)


def test_show_in_context_button_opens_and_closes():
    at = _page()
    buttons = [b for b in at.button if b.label == "Show in context"]
    assert len(buttons) == 4                       # the 4 Verified rows; none for the Not found row
    buttons[0].click().run()
    assert not at.exception
    marked = [m.value for m in at.markdown if "<mark" in m.value]
    assert len(marked) == 1
    rows = app.build_rows(app.load_sample()[0]["result"], app.load_sample()[1])
    first_found = next(r for r in rows if r["start"] is not None)
    assert html_escape(first_found["Exact wording"]) in marked[0]
    hide = [b for b in at.button if b.label == "Hide context"]
    assert len(hide) == 1
    hide[0].click().run()
    assert not [m for m in at.markdown if "<mark" in m.value]


def html_escape(s):
    import html
    return html.escape(s)


def test_page_upload_mode_shows_uploader_without_running():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=30).run()
    at.radio[0].set_value("Upload a contract (.txt or .docx)").run()
    assert not at.exception
    assert not [b for b in at.button if b.label == "Show in context"]   # no results until analysed
    assert not any("clause type" in m.value and "verified" in m.value for m in at.markdown)
