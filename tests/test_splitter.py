import pytest

from splitter import HEADING, PARAGRAPH, find_cut_points, split_text


def make_contract(n_sections=40, body="The parties agree to the terms set out here. " * 6):
    parts = ["DISTRIBUTION AGREEMENT\n\n"]
    for i in range(1, n_sections + 1):
        parts.append(f"{i}. SECTION TITLE {i}\n{body}\n\n")
    return "".join(parts)


def check_invariants(text, chunks, max_chars, overlap):
    assert chunks[0]["start"] == 0 and chunks[-1]["end"] == len(text)
    for c in chunks:
        assert c["text"] == text[c["start"]:c["end"]]           # offsets are exact
        assert 0 < len(c["text"]) <= max_chars                  # never over the limit
    for a, b in zip(chunks, chunks[1:]):
        assert b["start"] > a["start"]                          # always moves forward
        assert a["end"] - b["start"] >= overlap                 # overlap at least `overlap`
    assert [c["index"] for c in chunks] == list(range(len(chunks)))


def test_short_text_is_one_chunk():
    text = "Short contract.\n\n1. Term. One year."
    assert split_text(text, 1000, 100) == [{"index": 0, "start": 0, "end": len(text), "text": text}]


def test_invariants_on_structured_contract():
    text = make_contract()
    chunks = split_text(text, 2000, 200)
    assert len(chunks) > 3
    check_invariants(text, chunks, 2000, 200)


def test_prefers_cutting_before_numbered_headings():
    text = make_contract()
    chunks = split_text(text, 2000, 200)
    for c in chunks[1:]:
        # each later chunk ends just before a heading (or at the end of the text)
        if c["end"] < len(text):
            assert text[c["end"]:].split("\n", 1)[0].split(".")[0].isdigit()


def test_heading_detection():
    text = ("PREAMBLE text.\nARTICLE II MARKETING\n2.01.  Sales. Text.\n"
            "II - WORK BY LEO\n1.1      \"AB rated\" means x.\n(a) not a heading\n")
    cuts = find_cut_points(text)
    for line in ["ARTICLE II", "2.01.", "II - WORK", "1.1 "]:
        assert cuts[text.index(line)] == HEADING, line
    assert cuts.get(text.index("(a)")) != HEADING


def test_falls_back_to_paragraphs_then_sentences_then_hard_cut():
    # no headings, only paragraphs
    paras = "\n\n".join(["Plain paragraph text without any heading at all. " * 5] * 30)
    check_invariants(paras, split_text(paras, 1500, 150), 1500, 150)
    cuts = find_cut_points(paras)
    assert PARAGRAPH in cuts.values() and HEADING not in cuts.values()
    # one huge line: sentences only
    one_line = "This is a sentence of the agreement. " * 300
    check_invariants(one_line, split_text(one_line, 1500, 150), 1500, 150)
    # no cut points at all: hard cuts, still correct
    blob = "x" * 5000
    check_invariants(blob, split_text(blob, 1500, 150), 1500, 150)


def test_clause_across_a_boundary_is_whole_in_some_chunk():
    text = make_contract()
    clause = "This Agreement shall be governed by the laws of the State of Texas."
    mid = len(text) // 2
    text = text[:mid] + clause + text[mid:]
    chunks = split_text(text, 2000, 200)
    assert any(clause in c["text"] for c in chunks)


def test_rejects_overlap_too_large():
    with pytest.raises(ValueError):
        split_text("abc", 1000, 300)
