"""Convert CUAD-QA into one record per contract, and pick the dev and eval sets.

Run:  .venv/Scripts/python cuad_loader.py

Writes:
  data/contracts.jsonl   one line per contract: title, split, text, gold spans per category
  data/dev_titles.json   5 train contracts for prompt work
  data/eval_titles.json  20 test contracts for evaluation

Data notes (from inspecting the real records):
  - CUAD-QA has one row per (contract, category). In TRAIN, a category with several
    spans is split across several rows (id suffix _0, _1, ...), one span each. In TEST,
    all spans are in one row. Grouping by (title, category) handles both.
  - The id and question use title case ("Change Of Control"); we map to the official
    CUAD names used in the spec ("Change of Control").
  - One train contract appears twice with slightly different labels; see DROP_TITLES.

CUAD is by The Atticus Project, licensed CC BY 4.0.
"""

import json
import random
import re
import statistics

import config

HF_DATASET = "theatticusproject/cuad-qa"
# The dataset's own loading script is no longer supported by `datasets` (v4+).
# Hugging Face's auto-converted Parquet copy is the same data with the same splits.
HF_REVISION = "refs/convert/parquet"

# Same contract text as "ADUROBIOTECH,INC_06_02_2020-EX-10.7-CONSULTING AGREEMENT(1)".
# The two copies' labels differ only on Anti-Assignment: this copy misses the sentence
# "This Agreement shall not be assignable by Consultant." We keep the other copy.
DROP_TITLES = {"ADUROBIOTECH,INC_06_02_2020-EX-10.7-CONSULTING AGREEMENT"}

_BY_LOWER = {c.lower(): c for c in config.CATEGORIES}


def category_from_question(question: str) -> str | None:
    """Return our official category name if the question is about one of our five, else None."""
    m = re.search(r'related to "([^"]+)"', question)
    return _BY_LOWER.get(m.group(1).lower()) if m else None


def build_records(rows, split: str) -> list[dict]:
    """Group CUAD-QA rows into one record per contract, keeping only our five categories."""
    records: dict[str, dict] = {}
    for row in rows:
        title = row["title"]
        if title in DROP_TITLES:
            continue
        rec = records.setdefault(title, {
            "title": title,
            "split": split,
            "text": row["context"],
            "gold": {c: [] for c in config.CATEGORIES},
        })
        if rec["text"] != row["context"]:
            raise ValueError(f"Contract text differs between rows for {title!r}")
        category = category_from_question(row["question"])
        if category is None:
            continue
        for text, start in zip(row["answers"]["text"], row["answers"]["answer_start"]):
            if rec["text"][start:start + len(text)] != text:
                raise ValueError(f"Span offset mismatch in {title!r} / {category}")
            span = {"text": text, "start": start}
            if span not in rec["gold"][category]:
                rec["gold"][category].append(span)
    for rec in records.values():
        for spans in rec["gold"].values():
            spans.sort(key=lambda s: s["start"])
    return list(records.values())


def meets_minimum(records: list[dict], min_per_category: int) -> bool:
    """True if every category is present in at least `min_per_category` of the records."""
    return all(
        sum(1 for r in records if r["gold"][c]) >= min_per_category
        for c in config.CATEGORIES
    )


def sample_titles(candidates: list[dict], n: int, min_per_category: int,
                  seed: int, max_tries: int = 100_000) -> list[str]:
    """Pick n contracts at random (fixed seed), redrawing until each category
    appears in at least `min_per_category` of them. Every qualifying set is equally likely."""
    if len(candidates) < n:
        raise ValueError(f"Only {len(candidates)} candidates for a sample of {n}")
    rng = random.Random(seed)
    pool = sorted(candidates, key=lambda r: r["title"])  # stable order before shuffling
    for _ in range(max_tries):
        picked = rng.sample(pool, n)
        if meets_minimum(picked, min_per_category):
            return sorted(r["title"] for r in picked)
    raise RuntimeError("No sample met the per-category minimum; constraints may be impossible")


def load_rows():
    from datasets import load_dataset  # imported here so tests don't need the download
    return load_dataset(HF_DATASET, revision=HF_REVISION, cache_dir=str(config.RAW_DIR / "hf"))


def summarise(name: str, records: list[dict]) -> None:
    chars = [len(r["text"]) for r in records]
    print(f"\n{name}: {len(records)} contracts, {min(chars):,} to {max(chars):,} chars "
          f"(median {statistics.median(chars):,.0f})")
    for c in config.CATEGORIES:
        present = sum(1 for r in records if r["gold"][c])
        spans = sum(len(r["gold"][c]) for r in records)
        print(f"  {c:28s} present in {present:3d}   spans {spans:4d}")


def main() -> None:
    ds = load_rows()
    records = build_records(ds["train"], "train") + build_records(ds["test"], "test")

    config.DATA_DIR.mkdir(exist_ok=True)
    with open(config.CONTRACTS_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def short(split):
        return [r for r in records if r["split"] == split and len(r["text"]) <= config.EVAL_MAX_CHARS]

    dev = sample_titles(short("train"), config.DEV_SIZE, config.DEV_MIN_PER_CATEGORY, config.SEED)
    config.DEV_TITLES_PATH.write_text(json.dumps(dev, indent=2), encoding="utf-8")

    # The eval set is frozen once chosen: never redraw it, even if this code changes.
    by_title = {r["title"]: r for r in records}
    if config.EVAL_TITLES_PATH.exists():
        eval_ = json.loads(config.EVAL_TITLES_PATH.read_text(encoding="utf-8"))
        missing = [t for t in eval_ if t not in by_title]
        if missing:
            raise ValueError(f"Frozen eval titles not found in data: {missing}")
        print(f"Kept existing frozen eval set: {config.EVAL_TITLES_PATH}")
    else:
        eval_ = sample_titles(short("test"), config.EVAL_SIZE, config.EVAL_MIN_PER_CATEGORY, config.SEED)
        config.EVAL_TITLES_PATH.write_text(json.dumps(eval_, indent=2), encoding="utf-8")

    summarise("train (all)", [r for r in records if r["split"] == "train"])
    summarise("test (all)", [r for r in records if r["split"] == "test"])
    summarise(f"test <= {config.EVAL_MAX_CHARS:,} chars", short("test"))
    summarise("dev", [by_title[t] for t in dev])
    summarise("eval", [by_title[t] for t in eval_])
    print(f"\nWrote {config.CONTRACTS_PATH}, {config.DEV_TITLES_PATH}, {config.EVAL_TITLES_PATH}")


if __name__ == "__main__":
    main()
