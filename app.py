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

import pandas as pd
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
    return rows


def context_html(text: str, start: int, end: int, side: int = CONTEXT_CHARS) -> str:
    """The quote highlighted in its surrounding text. All contract text is HTML-escaped."""
    s, e = max(0, start - side), min(len(text), end + side)
    before, quote, after = (html.escape(text[s:start]), html.escape(text[start:end]), html.escape(text[end:e]))
    return ('<div style="white-space: pre-wrap; font-family: Georgia, serif; line-height: 1.5; '
            'border: 1px solid #ccc; padding: 0.75em; max-height: 28em; overflow-y: auto;">'
            f'{"…" if s > 0 else ""}{before}<mark style="background:#ffe066;">{quote}</mark>'
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


def show_results(result: dict, text: str) -> None:
    st.subheader("Results")
    st.info(STATUS_NOTE)
    if result["failed_chunks"]:
        st.warning(f"Part of this contract could not be analysed (section(s) "
                   f"{', '.join(str(i + 1) for i in result['failed_chunks'])}). "
                   "Clause types with nothing verified are marked Needs review.")
    rows = build_rows(result, text)
    table = pd.DataFrame(rows)[["Clause type", "Status", "Exact wording", "Why"]]
    colours = [STATUS_COLOUR[r["status"]] for r in rows]
    styled = table.style.apply(lambda col: [f"background-color: {c}; color: #111;" for c in colours],
                               subset=["Status"])
    st.caption("Click a row to see the wording in its place in the contract.")
    event = st.dataframe(styled, hide_index=True, on_select="rerun", selection_mode="single-row",
                         key="results_table",
                         column_config={"Clause type": st.column_config.TextColumn(width="small"),
                                        "Status": st.column_config.TextColumn(width="small"),
                                        "Exact wording": st.column_config.TextColumn(width="large"),
                                        "Why": st.column_config.TextColumn(width="medium")})
    selected = event.selection.rows if event and event.selection else []
    if selected:
        r = rows[selected[0]]
        st.markdown(f"**{r['Clause type']}: {r['Status']}**")
        if r["start"] is not None:
            st.markdown(context_html(text, r["start"], r["end"]), unsafe_allow_html=True)
        elif r["status"] == NOT_FOUND:
            st.write("Nothing was found for this clause type, so there is no wording to show. "
                     "Search the contract yourself.")
        else:
            st.write("There is no matching wording in the contract to show.")


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
        st.markdown(f"**Sample:** {html.escape(data['title'])}  \n"
                    f"Source: {data['source']}. Saved result, shown instantly; no AI call is made.")
        show_results(data["result"], text)
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
        show_results(results[key], text)


if __name__ == "__main__":
    main()
