"""Show how the dev contracts are split: chunk sizes, overlaps, cut types, and whether
each gold span sits whole inside at least one chunk.

Run:  .venv/Scripts/python scripts/show_splits.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from splitter import find_cut_points, split_text

NAMES = {4: "heading", 3: "paragraph", 2: "line", 1: "sentence", 0: "HARD CUT"}


def load(titles):
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        recs = {r["title"]: r for r in map(json.loads, f) if r["title"] in titles}
    return [recs[t] for t in titles]


def main():
    titles = json.loads(config.DEV_TITLES_PATH.read_text(encoding="utf-8"))
    for rec in load(titles):
        text = rec["text"]
        chunks = split_text(text)
        cuts = find_cut_points(text)
        print(f"\n{rec['title'][:70]}  ({len(text):,} chars) -> {len(chunks)} chunk(s)")
        for c in chunks:
            kind = NAMES[cuts.get(c["end"], 0)] if c["end"] < len(text) else "end of text"
            print(f"  chunk {c['index']}: {c['start']:>6,}-{c['end']:>6,}  {len(c['text']):>6,} chars  cut at: {kind}"
                  f"  | next line: {text[c['end']:c['end'] + 50]!r}" if c["end"] < len(text) else
                  f"  chunk {c['index']}: {c['start']:>6,}-{c['end']:>6,}  {len(c['text']):>6,} chars  (end)")
        for a, b in zip(chunks, chunks[1:]):
            print(f"  overlap {a['index']}/{b['index']}: {a['end'] - b['start']:,} chars")
        for cat in config.CATEGORIES:
            for s in rec["gold"][cat]:
                s_end = s["start"] + len(s["text"])
                whole = [c["index"] for c in chunks if c["start"] <= s["start"] and s_end <= c["end"]]
                print(f"  gold {cat:28s} {s['start']:>6,}-{s_end:>6,}  whole in chunk(s) {whole or 'NONE'}")


if __name__ == "__main__":
    main()
