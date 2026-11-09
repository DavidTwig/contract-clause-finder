"""Build the app's instant sample from a DEV contract, using cached API replies only.

Run:  .venv/Scripts/python scripts/make_sample.py
Writes samples/sample_contract.txt and samples/sample_result.json (committed, so the demo works
on a fresh clone, where cache/ and data/contracts.jsonl do not exist).

The network call is replaced by a function that fails, so if any reply is not already in the
cache the script stops instead of calling the API.
"""

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import llm
from pipeline import analyse_contract

SAMPLE_TITLE = "HertzGroupRealtyTrustInc_20190920_S-11A_EX-10.8_11816941_EX-10.8_Trademark License Agreement"
SAMPLES_DIR = config.ROOT / "samples"


def no_api(*args, **kwargs):
    raise RuntimeError("make_sample.py must not call the API: a reply was missing from the cache")


def main():
    dev = json.loads(config.DEV_TITLES_PATH.read_text(encoding="utf-8"))
    if SAMPLE_TITLE not in dev:
        sys.exit("The sample must be a dev contract.")
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        rec = next(r for r in map(json.loads, f) if r["title"] == SAMPLE_TITLE)
    llm._call_once = no_api
    out = analyse_contract(rec["text"])
    if out["failed_chunks"]:
        sys.exit(f"Failed chunks {out['failed_chunks']}: not a clean sample.")
    result = {"title": SAMPLE_TITLE, "source": "CUAD v1 (CC BY 4.0), train split, dev set of this project",
              "made": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "versions": {"model": config.MODEL, "first_pass_prompt": config.FIRST_PASS_PROMPT,
                           "second_pass_prompt": config.SECOND_PASS_PROMPT, "definitions": config.DEFINITIONS},
              "result": out}
    SAMPLES_DIR.mkdir(exist_ok=True)
    (SAMPLES_DIR / "sample_contract.txt").write_text(rec["text"], encoding="utf-8", newline="")
    (SAMPLES_DIR / "sample_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    for cl in out["clauses"]:
        print(f"{cl['category']:28s} {cl['status']}")
    print(f"Wrote {SAMPLES_DIR / 'sample_contract.txt'} and sample_result.json")


if __name__ == "__main__":
    main()
