"""Split a contract into chunks that fit the model, cutting at the most natural place.

Every chunk keeps its character offsets, so that  chunk["text"] == contract[chunk["start"]:chunk["end"]].
"""

import re

import config

# Cut-point strength. Higher is a better place to cut.
HEADING, PARAGRAPH, LINE, SENTENCE = 4, 3, 2, 1

# A heading at the start of a line, e.g.
#   "ARTICLE II MARKETING", "Section 5.", "2.01.  Sales", "6. TERMS OF PAYMENT",
#   "1.1      \"AB rated\" means", "II - WORK BY LEO", "(a) ..." is NOT treated as a heading.
_HEADING_RE = re.compile(
    r"""^[ \t]*(?:
        (?:ARTICLE|Article|SECTION|Section)\s+[0-9IVXLC]+    # ARTICLE II / Section 5
      | \d{1,3}(?:\.\d{1,3})*\.?[ \t]+[\"A-Z(]                # 1. / 2.01 / 1.1 followed by a capital
      | [IVXLC]{1,6}[ \t]*[-.][ \t]+[A-Z]                     # II - WORK / IV. TERM
      | [A-Z][A-Z \t,&/-]{3,78}$                              # short ALL-CAPS title line
    )""",
    re.MULTILINE | re.VERBOSE,
)
_PARAGRAPH_RE = re.compile(r"\n[ \t]*\n")
_SENTENCE_RE = re.compile(r"[.;:][ \t]+(?=[A-Z\"(])")


def find_cut_points(text: str) -> dict[int, int]:
    """Return {offset: strength} for every place it would be reasonable to start a new chunk."""
    cuts: dict[int, int] = {}

    def add(pos: int, strength: int) -> None:
        if 0 < pos < len(text) and cuts.get(pos, 0) < strength:
            cuts[pos] = strength

    for m in _SENTENCE_RE.finditer(text):
        add(m.end(), SENTENCE)
    for m in re.finditer(r"\n", text):
        add(m.end(), LINE)
    for m in _PARAGRAPH_RE.finditer(text):
        add(m.end(), PARAGRAPH)
    for m in _HEADING_RE.finditer(text):
        add(m.start(), HEADING)  # cut just before the heading line
    return cuts


def _best_cut(cuts: dict[int, int], lo: int, hi: int) -> int | None:
    """The strongest cut point in (lo, hi]; the latest one if tied."""
    best = None
    for pos, strength in cuts.items():
        if lo < pos <= hi and (best is None or (strength, pos) > (cuts[best], best)):
            best = pos
    return best


def split_text(text: str,
               max_chars: int = config.MAX_CHUNK_TOKENS * config.CHARS_PER_TOKEN,
               overlap_chars: int = config.OVERLAP_TOKENS * config.CHARS_PER_TOKEN) -> list[dict]:
    """Split text into chunks of at most max_chars, overlapping by overlap_chars to 2x overlap_chars."""
    if overlap_chars >= max_chars // 4:
        raise ValueError("overlap must be less than a quarter of the chunk size")
    cuts = find_cut_points(text)
    chunks = []
    start = 0
    while True:
        if len(text) - start <= max_chars:
            end = len(text)
        else:
            # Cut in the second half of the window, so chunks are never tiny.
            end = _best_cut(cuts, start + max_chars // 2, start + max_chars) or start + max_chars
        chunks.append({"index": len(chunks), "start": start, "end": end, "text": text[start:end]})
        if end == len(text):
            return chunks
        # Next chunk starts between 1x and 2x overlap_chars before this one ended,
        # at the best cut point in that range, so the overlap is never smaller than overlap_chars.
        next_start = _best_cut(cuts, end - 2 * overlap_chars, end - overlap_chars) or end - overlap_chars
        start = max(next_start, start + 1)
