"""Check, with code only, that a quote from the model really appears in the contract.

Normalises whitespace, curly quotes and dashes, then requires an exact substring match.
Nothing else is forgiven: paraphrases, ellipses, case changes and "fixed" typos all fail.
"""

_CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",   # single quotes
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',   # double quotes
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",   # dashes
    "―": "-", "−": "-",
}


def normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Normalise text and return (normalised, index_map), where index_map[i] is the
    position in `text` of normalised character i. Whitespace runs become one space;
    leading and trailing whitespace is dropped."""
    out: list[str] = []
    index_map: list[int] = []
    pending_space = None  # position of the first whitespace char in the current run
    for i, ch in enumerate(text):
        if ch.isspace():
            if pending_space is None:
                pending_space = i
            continue
        if pending_space is not None and out:
            out.append(" ")
            index_map.append(pending_space)
        pending_space = None
        out.append(_CHAR_MAP.get(ch, ch))
        index_map.append(i)
    return "".join(out), index_map


def normalise(text: str) -> str:
    return normalise_with_map(text)[0]


def check_quote(quote: str, chunk_text: str, chunk_start: int) -> dict:
    """Return {"ok": True, "start": s, "end": e} with offsets in the ORIGINAL contract,
    or {"ok": False, "start": None, "end": None} if the quote is not in the chunk.
    Uses the first occurrence if the quote appears more than once."""
    needle = normalise(quote or "")
    if not needle:
        return {"ok": False, "start": None, "end": None}
    haystack, index_map = normalise_with_map(chunk_text)
    pos = haystack.find(needle)
    if pos < 0:
        return {"ok": False, "start": None, "end": None}
    start = chunk_start + index_map[pos]
    end = chunk_start + index_map[pos + len(needle) - 1] + 1
    return {"ok": True, "start": start, "end": end}
