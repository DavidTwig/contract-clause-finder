"""Contract Clause Finder: a prototype Streamlit app.

Run:  .venv/Scripts/streamlit run app.py

The sample contract shows a saved result (samples/), so it is instant and makes no API calls.
Uploading a contract runs the real pipeline, which calls the Groq API and uses the daily quota.
"""

import contextlib
import hashlib
import html
import io
import json
import re

import streamlit as st

import config
import llm
from pipeline import NEEDS_REVIEW, NOT_FOUND, VERIFIED, analyse_contract
from splitter import split_text

SAMPLES_DIR = config.ROOT / "samples"
CONTEXT_CHARS = 800  # contract text shown either side of a quote

# Status is always shown as words; the colour only repeats it.
STATUS_TEXT = {VERIFIED: "Verified", NEEDS_REVIEW: "Needs review", NOT_FOUND: "Not found: check"}
STATUS_COLOUR = {VERIFIED: "#d8eedc", NEEDS_REVIEW: "#fbe7b5", NOT_FOUND: "#e4e4e4"}
# Badge text is #111 (about 15:1 on these colours). The pale fills alone are faint on white
# (about 1.2:1), so each badge also has a darker border, at least 5:1 on white.
STATUS_BORDER = {VERIFIED: "#2e7d32", NEEDS_REVIEW: "#8a6100", NOT_FOUND: "#5f5f5f"}
STATUS_ORDER = {NEEDS_REVIEW: 0, NOT_FOUND: 1, VERIFIED: 2}
SAMPLE_LABEL = "Trademark License Agreement (public filing, from the CUAD dataset)"
SAMPLE_SOURCE = "From the public CUAD dataset (CC BY 4.0). This is a saved result, so no AI call is made."

PROTOTYPE_NOTE = ("**Prototype.** Check every output against the contract yourself. "
                  "**Do not upload confidential documents:** uploaded text is sent to an external "
                  "AI service (Groq) for analysis.")
STATUS_NOTE = (
    "**How to read the status**\n\n"
    "- **Verified**: the wording shown exists word for word in the contract and passed a second "
    "review. It does **not** mean every relevant clause of that type was found.\n"
    "- **Needs review**: something was found but could not be confirmed, or part of the contract "
    "could not be analysed. Read the wording and the contract yourself.\n"
    "- **Not found: check**: nothing was found. This is **unconfirmed**: the clause may still be "
    "in the contract. Check it yourself.")


# --- reading uploads -------------------------------------------------------------

def read_upload(name: str, data: bytes) -> str:
    """Plain text from a .txt or .docx upload. Raises ValueError with a readable message."""
    lower = name.lower()
    if lower.endswith(".txt"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
    elif lower.endswith(".docx"):
        import docx  # python-docx
        try:
            doc = docx.Document(io.BytesIO(data))
        except Exception as e:
            raise ValueError(f"Could not read this Word file ({type(e).__name__}).") from e
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(parts)
    else:
        raise ValueError("Please upload a .txt or .docx file.")
    if not text.strip():
        raise ValueError("The file contains no text.")
    return text


# --- results table ---------------------------------------------------------------

def _why(f: dict) -> str:
    why = f.get("reason") or ""
    if f.get("verdict") == "reject":
        why += f"  Second review disagreed: {f.get('verdict_reason') or ''}"
    elif f.get("verdict") is None and f.get("status") == NEEDS_REVIEW:
        why += "  The second review could not be run."
    return why.strip()


def build_rows(result: dict, text: str) -> list[dict]:
    """One row per finding; one row for each clause type with no finding. In clause-type order."""
    rows = []
    for cl in result["clauses"]:
        c = cl["category"]
        found = [f for f in result["findings"] if f["category"] == c]
        failed = [f for f in result["raw_findings"] if f["category"] == c and f["status"] == "failed_quote"]
        for f in sorted(found, key=lambda f: f["start"]):
            rows.append({"Clause type": c, "status": f["status"], "Exact wording": text[f["start"]:f["end"]],
                         "Why": _why(f), "start": f["start"], "end": f["end"]})
        for f in failed:
            rows.append({"Clause type": c, "status": NEEDS_REVIEW,
                         "Exact wording": f"(Not found word for word in the contract.) The AI's quote: {f['quote']}",
                         "Why": f"{f.get('reason') or ''}  The quote could not be matched to the contract text, "
                                "so it may be misquoted or invented.".strip(),
                         "start": None, "end": None})
        if not found and not failed:
            if cl["status"] == NOT_FOUND:
                why = "No clause of this type was found. Unconfirmed: check the contract yourself."
            else:
                why = "Part of the contract could not be analysed, so this clause type may have been missed."
            rows.append({"Clause type": c, "status": cl["status"], "Exact wording": "",
                         "Why": why, "start": None, "end": None})
    for r in rows:
        r["Status"] = STATUS_TEXT[r["status"]]
    # what needs the reader's attention first; sorted() is stable, so clause-type order is kept within each status
    return sorted(rows, key=lambda r: STATUS_ORDER[r["status"]])


def context_html(text: str, start: int, end: int, side: int = CONTEXT_CHARS) -> str:
    """The quote highlighted in its surrounding text. All contract text is HTML-escaped."""
    s, e = max(0, start - side), min(len(text), end + side)
    before, quote, after = (html.escape(text[s:start]), html.escape(text[start:end]), html.escape(text[end:e]))
    return ('<div style="white-space: pre-wrap; font-family: Georgia, serif; line-height: 1.5; '
            'color: #111; background: #fff; border: 1px solid #767676; padding: 0.75em; '
            'max-height: 28em; overflow-y: auto;">'
            f'{"…" if s > 0 else ""}{before}<mark style="background:#ffe066; color:#111; '
            f'border-bottom: 2px solid #8a6100;">{quote}</mark>'
            f'{after}{"…" if e < len(text) else ""}</div>')


# --- running the pipeline ----------------------------------------------------------

# Measured on the four dev contracts over 10,000 chars (results/stage3_dev_defs_v4.json):
# total tokens of both passes were 1.38x to 2.46x (characters / 4). Shorter contracts cost
# relatively more because each call has fixed prompt overhead.
TOKEN_FACTOR_RANGE = (1.4, 2.5)


def token_estimate(text: str) -> tuple[int, int]:
    base = len(text) / config.CHARS_PER_TOKEN
    return int(round(base * TOKEN_FACTOR_RANGE[0], -2)), int(round(base * TOKEN_FACTOR_RANGE[1], -2))


class _LineWriter(io.TextIOBase):
    """Turns the pipeline's console lines into calls to on_line (used for progress)."""

    def __init__(self, on_line):
        self.on_line, self.buf = on_line, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.on_line(line.strip())
        return len(s)


def progress_message(line: str, replies: int) -> str | None:
    if line.startswith("tokens:"):
        return f"Working… {replies} AI repl{'y' if replies == 1 else 'ies'} received so far."
    m = re.match(r"throttle: .* waiting (\d+)s", line)
    if m:
        return f"Pausing about {m.group(1)} s to stay within the AI service's per-minute limit…"
    m = re.match(r"429 rate limit: retry-after (\d+)s", line)
    if m:
        return f"The AI service asked us to wait {m.group(1)} s (rate limit)…"
    return None


def run_analysis(text: str, on_progress=lambda msg: None) -> tuple[dict | None, str | None]:
    """Run the pipeline. Returns (result, None) or (None, a message for the user)."""
    replies = 0

    def on_line(line):
        nonlocal replies
        replies += line.startswith("tokens:")
        msg = progress_message(line, replies)
        if msg:
            on_progress(msg)

    try:
        with contextlib.redirect_stdout(_LineWriter(on_line)):
            return analyse_contract(text), None
    except llm.DailyLimitReached:
        return None, ("**Daily limit reached.** Today's quota for the AI service is used up, so this "
                      "contract could not be analysed. Please try again later (usually the next day). "
                      "Any parts already analysed are saved and will not be charged again.")
    except RuntimeError as e:
        if "rate limited" in str(e).lower():
            return None, ("**Rate limit.** The AI service is busy and kept asking us to wait. "
                          "Please try again in a few minutes.")
        if "GROQ_API_KEY" in str(e):
            return None, "**No API key.** Uploads need a Groq API key in the `.env` file."
        return None, f"**The analysis stopped with an error:** {html.escape(str(e))}"
    except Exception as e:  # anything unexpected: show it plainly rather than crash the page
        return None, f"**The analysis stopped with an error:** {type(e).__name__}"


# --- page --------------------------------------------------------------------------

def load_sample():
    data = json.loads((SAMPLES_DIR / "sample_result.json").read_text(encoding="utf-8"))
    text = (SAMPLES_DIR / "sample_contract.txt").read_text(encoding="utf-8")
    return data, text


def current_versions() -> dict:
    return {"model": config.MODEL, "first_pass_prompt": config.FIRST_PASS_PROMPT,
            "second_pass_prompt": config.SECOND_PASS_PROMPT, "definitions": config.DEFINITIONS}


def summary_line(result: dict) -> str:
    """e.g. "4 clause types verified, 1 to check yourself (1 not found)". Counts clause types."""
    statuses = [cl["status"] for cl in result["clauses"]]
    v, nr, nf = statuses.count(VERIFIED), statuses.count(NEEDS_REVIEW), statuses.count(NOT_FOUND)
    line = f"{v} clause type{'' if v == 1 else 's'} verified, {nr + nf} to check yourself"
    detail = [d for d in (f"{nr} need{'s' if nr == 1 else ''} review" if nr else "",
                          f"{nf} not found" if nf else "") if d]
    return line + (f" ({', '.join(detail)})" if detail else "")


def _cell(value: str) -> str:
    """Contract or AI text as escaped HTML that wraps and keeps line breaks."""
    return f'<div style="white-space: pre-wrap; overflow-wrap: anywhere;">{html.escape(value)}</div>'


def _badge(status: str) -> str:
    return (f'<span style="background:{STATUS_COLOUR[status]}; color:#111; padding:2px 8px; '
            f'border:1px solid {STATUS_BORDER[status]}; '
            f'border-radius:4px; font-weight:600; white-space:nowrap;">{STATUS_TEXT[status]}</span>')


COLUMN_WIDTHS = [2, 1.6, 5, 3.4, 1.4]
COLUMN_LABELS = ["Clause type", "Status", "Exact wording", "Why"]

# Makes the header and rows read as one table. Header and rows are separate bordered containers
# with the same column widths, so the header lines up with the columns; these rules shade the
# header, remove the corner rounding between them and overlap their borders by 1px so each line
# is single. Streamlit stacks columns at 640px and below: there the header row is hidden and each
# cell shows its own label instead.
TABLE_CSS = """<style>
div[class*="st-key-reshead_"] { background: #eef0f3; border-radius: 0.5rem 0.5rem 0 0 !important; }
div[class*="st-key-reshead_"] .cc-head { font-weight: 700; color: #111; }
div[class*="st-key-resrow_"] { border-radius: 0 !important; margin-top: -1px; }
div[class*="st-key-reslast_"] { border-radius: 0 0 0.5rem 0.5rem !important; margin-top: -1px; }
.cc-label { display: none; }
@media (max-width: 640px) {
  div[class*="st-key-reshead_"] { display: none; }
  .cc-label { display: block; font-size: 0.8rem; font-weight: 700; color: #333; margin-bottom: 0.1rem; }
}
</style>"""


def _labelled(label: str, inner_html: str) -> str:
    """A cell's own label (shown only in a narrow window, where the header row is hidden)."""
    return f'<div class="cc-label">{label}</div>{inner_html}'


def show_results(result: dict, text: str, result_id: str) -> None:
    st.subheader("Results")
    st.markdown(f"**{summary_line(result)}**")
    st.info(STATUS_NOTE)
    if result["failed_chunks"]:
        st.warning(f"Part of this contract could not be analysed (section(s) "
                   f"{', '.join(str(i + 1) for i in result['failed_chunks'])}). "
                   "Clause types with nothing verified are marked Needs review.")
    rows = build_rows(result, text)
    open_key = f"context_open_{result_id}"
    st.caption("Items to check come first. Use “Show in context” to see the wording in its place in the contract.")
    st.markdown(TABLE_CSS, unsafe_allow_html=True)
    table = st.container(gap=None, key=f"restable_{result_id}")  # no space between header and rows
    with table.container(border=True, key=f"reshead_{result_id}"):
        for col, label in zip(st.columns(COLUMN_WIDTHS), COLUMN_LABELS + [""]):
            col.markdown(f'<div class="cc-head">{label}</div>', unsafe_allow_html=True)
    for i, r in enumerate(rows):
        row_key = f"reslast_{result_id}" if i == len(rows) - 1 else f"resrow_{result_id}_{i}"
        with table.container(border=True, key=row_key):
            c_type, c_status, c_words, c_why, c_btn = st.columns(COLUMN_WIDTHS)
            c_type.markdown(_labelled("Clause type", _cell(r["Clause type"])), unsafe_allow_html=True)
            c_status.markdown(_labelled("Status", _badge(r["status"])), unsafe_allow_html=True)
            c_words.markdown(_labelled("Exact wording", _cell(r["Exact wording"] or "(no wording found)")),
                             unsafe_allow_html=True)
            c_why.markdown(_labelled("Why", _cell(r["Why"])), unsafe_allow_html=True)
            is_open = st.session_state.get(open_key) == i
            if r["start"] is not None:
                if c_btn.button("Hide context" if is_open else "Show in context", key=f"ctx_{result_id}_{i}"):
                    st.session_state[open_key] = None if is_open else i
                    st.rerun()
            if is_open and r["start"] is not None:
                st.caption("The wording in its place in the contract:")
                st.markdown(context_html(text, r["start"], r["end"]), unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="Contract Clause Finder", layout="wide")
    st.title("Contract Clause Finder")
    st.write("Finds five clause types in a commercial contract: Change of Control, Termination for "
             "Convenience, Cap on Liability, Anti-Assignment and Governing Law. It shows the exact "
             "wording it relied on and marks what you must check.")
    st.warning(PROTOTYPE_NOTE)

    choice = st.radio("Contract", ["Sample contract (instant)", "Upload a contract (.txt or .docx)"],
                      horizontal=True)

    if choice.startswith("Sample"):
        data, text = load_sample()
        if data["versions"] != current_versions():
            st.error("The saved sample was made with different prompts from the current settings, "
                     "so it is not shown. Rebuild it with scripts/make_sample.py.")
            return
        st.markdown(f"**Sample:** {SAMPLE_LABEL}")
        st.caption(SAMPLE_SOURCE)
        show_results(data["result"], text, "sample")
        return

    upload = st.file_uploader("Choose a contract", type=["txt", "docx"])
    if upload is None:
        return
    try:
        text = read_upload(upload.name, upload.getvalue())
    except ValueError as e:
        st.error(str(e))
        return
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    parts = len(split_text(text, config.MAX_CHUNK_TOKENS * config.CHARS_PER_TOKEN,
                           config.OVERLAP_TOKENS * config.CHARS_PER_TOKEN))
    est_low, est_high = token_estimate(text)
    st.write(f"{len(text):,} characters, read in {parts} part{'s' if parts != 1 else ''}, "
             f"plus a second review of each finding. This can take several minutes because of the "
             f"AI service's rate limits. Tokens used today: {llm.tokens_today():,} of "
             f"{config.TOKENS_PER_DAY:,}. A contract this size uses very roughly "
             f"{est_low:,}–{est_high:,} tokens.")

    results = st.session_state.setdefault("results", {})
    if key not in results and st.button("Analyse this contract (uses the API quota)", type="primary"):
        with st.status("Analysing the contract…", expanded=True) as status:
            line = st.empty()
            result, error = run_analysis(text, on_progress=line.write)
            if error:
                status.update(label="Analysis stopped", state="error")
                st.error(error)
                return
            status.update(label="Analysis complete", state="complete", expanded=False)
        results[key] = result
    if key in results:
        show_results(results[key], text, key[:16])


if __name__ == "__main__":
    main()
