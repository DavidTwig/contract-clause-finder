import pytest

import config
from cuad_loader import build_records, category_from_question, meets_minimum, sample_titles

TEXT = "Governed by New York law. Not assignable. Either party may terminate."


def row(title, category, spans, context=TEXT, suffix=""):
    return {
        "id": f"{title}__{category}{suffix}",
        "title": title,
        "context": context,
        "question": f'Highlight the parts (if any) of this contract related to "{category}" that should be reviewed by a lawyer.',
        "answers": {"text": [s for s, _ in spans], "answer_start": [st for _, st in spans]},
    }


def test_category_mapping_handles_cuad_title_case():
    assert category_from_question(row("t", "Change Of Control", [])["question"]) == "Change of Control"
    assert category_from_question(row("t", "Governing Law", [])["question"]) == "Governing Law"
    assert category_from_question(row("t", "Parties", [])["question"]) is None


def test_build_records_groups_train_style_rows_and_dedupes():
    rows = [
        # train style: one span per row, several rows for the same category
        row("A", "Anti-Assignment", [("Not assignable.", 26)], suffix="_0"),
        row("A", "Anti-Assignment", [("Not assignable.", 26)], suffix="_1"),  # exact duplicate
        row("A", "Governing Law", [("Governed by New York law.", 0)]),
        row("A", "Cap On Liability", []),  # absent
        row("A", "Parties", [("Either party", 42)]),  # not one of our categories
    ]
    [rec] = build_records(rows, "train")
    assert rec["title"] == "A" and rec["split"] == "train" and rec["text"] == TEXT
    assert set(rec["gold"]) == set(config.CATEGORIES)
    assert rec["gold"]["Anti-Assignment"] == [{"text": "Not assignable.", "start": 26}]
    assert rec["gold"]["Governing Law"] == [{"text": "Governed by New York law.", "start": 0}]
    assert rec["gold"]["Cap on Liability"] == []


def test_build_records_rejects_bad_offsets():
    with pytest.raises(ValueError):
        build_records([row("A", "Governing Law", [("New York", 0)])], "test")


def make(title, present):
    return {"title": title, "gold": {c: ([{"text": "x", "start": 0}] if c in present else [])
                                     for c in config.CATEGORIES}}


def test_sample_titles_meets_minimum_and_is_reproducible():
    full = make("full", config.CATEGORIES)
    pool = [make(f"empty{i}", []) for i in range(10)] + [full]
    picked = sample_titles(pool, 3, 1, seed=1)
    assert "full" in picked and len(picked) == 3
    assert picked == sample_titles(pool, 3, 1, seed=1)


def test_sample_titles_raises_when_impossible():
    pool = [make(f"empty{i}", []) for i in range(5)]
    assert not meets_minimum(pool, 1)
    with pytest.raises(RuntimeError):
        sample_titles(pool, 3, 1, seed=1, max_tries=50)
