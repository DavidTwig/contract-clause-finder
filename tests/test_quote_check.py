from quote_check import check_quote, normalise, normalise_with_map

CONTRACT = (
    "ARTICLE 9 GENERAL\n\n"
    "9.05  Governing Law. This Agreement shall be governed by the laws of\n"
    "      the State of Texas — without regard to its “conflict of laws” rules.\n"
    "9.06  Notices. All notices shall be in writing."
)


def test_exact_quote_passes_with_original_offsets():
    q = "This Agreement shall be governed by the laws of"
    r = check_quote(q, CONTRACT, 0)
    assert r["ok"] and CONTRACT[r["start"]:r["end"]] == q


def test_line_breaks_curly_quotes_and_dashes_are_forgiven():
    q = 'the laws of the State of Texas - without regard to its "conflict of laws" rules.'
    r = check_quote(q, CONTRACT, 0)
    assert r["ok"]
    original = CONTRACT[r["start"]:r["end"]]
    assert original.startswith("the laws of\n") and original.endswith("rules.")
    assert normalise(original) == normalise(q)


def test_offsets_are_relative_to_the_whole_contract_not_the_chunk():
    chunk_start = CONTRACT.index("9.05")
    chunk = CONTRACT[chunk_start:]
    r = check_quote("Governing Law.", chunk, chunk_start)
    assert r["ok"] and CONTRACT[r["start"]:r["end"]] == "Governing Law."


def test_paraphrase_ellipsis_case_and_empty_quotes_fail():
    for q in [
        "This Agreement is governed by Texas law.",                       # paraphrase
        "This Agreement shall be governed ... State of Texas",            # ellipsis
        "THIS AGREEMENT SHALL BE GOVERNED BY THE LAWS OF",                # case changed
        "",                                                               # empty
        "   ",                                                            # whitespace only
        None,                                                             # missing
    ]:
        assert check_quote(q, CONTRACT, 0) == {"ok": False, "start": None, "end": None}


def test_quote_outside_the_chunk_fails():
    chunk = CONTRACT[:30]
    assert not check_quote("All notices shall be in writing.", chunk, 0)["ok"]


def test_index_map_points_back_into_original():
    text = "  a “b”\n\n c–d  "
    norm, idx = normalise_with_map(text)
    assert norm == 'a "b" c-d'
    assert len(norm) == len(idx)
    for n_ch, i in zip(norm, idx):
        assert n_ch == " " and text[i].isspace() or normalise(text[i]) == n_ch
