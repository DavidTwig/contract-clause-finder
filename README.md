# Contract Clause Finder

A prototype that reads a commercial contract, looks for five clause types used in due diligence, quotes the exact wording it relied on, and marks what a person must check. The five types are Change of Control, Termination for Convenience, Cap on Liability, Anti-Assignment and Governing Law.

It is a prototype. Check every output against the contract, and do not upload confidential documents: uploaded text is sent to an external AI service (Groq).

See [WRITEUP.md](WRITEUP.md) for a one-page summary of the results, what failed, and build versus buy.

## How it works

1. **Split.** The contract is cut into sections of up to about 12,000 characters, at headings or paragraph breaks where possible, with some overlap so a clause on a boundary is not lost.
2. **First pass.** For each section, the model (openai/gpt-oss-120b, via Groq) is asked for any of the five clause types, with each quote copied word for word and a short reason.
3. **Quote check.** Plain code checks that every quote appears in the contract, allowing only differences in whitespace, curly quotes and dashes. A quote that is not found is never shown as Verified.
4. **Second pass.** Each quote that passed is shown to the model again with its surrounding section, and the model confirms or rejects it.
5. **Status.** Each clause type gets one status:
   - **Verified**: the quote exists word for word and the second pass confirmed it. This does not mean every relevant clause of that type was found.
   - **Needs review**: something was found but not confirmed, or part of the contract could not be analysed.
   - **Not found: check**: nothing was found. This is unconfirmed: the clause may still be there.

Every valid API reply is cached on disk, so rerunning the same contract with the same prompts costs nothing. The prompts are plain text files in [prompts/](prompts/) and are versioned.

## Results

Tested on 20 contracts from the CUAD test set, with prompts developed on 5 separate contracts and frozen before the test. One run. From [results/metrics.json](results/metrics.json).

| Clause type | Contracts with the clause | Precision | Recall | Passages matched (overlap at least half) | Passages touched (any overlap) |
|---|---|---|---|---|---|
| Change of Control | 5 | 3/3 (100%) | 3/5 (60%) | 3/7 (43%) | 4/7 (57%) |
| Termination for Convenience | 6 | 5/9 (56%) | 5/6 (83%) | 5/7 (71%) | 6/7 (86%) |
| Cap on Liability | 6 | 4/4 (100%) | 4/6 (67%) | 3/16 (19%) | 6/16 (38%) |
| Anti-Assignment | 14 | 13/13 (100%) | 13/14 (93%) | 12/20 (60%) | 16/20 (80%) |
| Governing Law | 14 | 13/13 (100%) | 13/14 (93%) | 13/14 (93%) | 13/14 (93%) |
| **All five** | 45 | **38/42 (90%)** | **38/45 (84%)** | **36/64 (56%)** | **45/64 (70%)** |

- Precision and recall are per contract: is the clause type present? Verified counts as present.
- Statuses across the 100 contract and clause-type pairs: Verified 42, Needs review 4, Not found: check 54. Not found was correct 50 times out of 54 (93%).
- 4 of 54 quotes failed the quote check (7%). The second pass rejected 0 of 45 quotes and used 35,629 of 147,466 tokens (24%).
- A manual review of 16 of the 28 disagreements with CUAD ([results/error_review.csv](results/error_review.csv)) found 4 model errors, 3 CUAD label issues, 6 ambiguous cases, and 3 cases where the quote check was too strict.

The full error list is in [results/errors.csv](results/errors.csv), and the cases reviewed are in [results/review_pack.md](results/review_pack.md).

## Install

Needs Python 3.11 and a Groq API key (only for analysing new contracts and for running the evaluation).

```
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS or Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a file called `.env` in the project folder containing:

```
GROQ_API_KEY=your-key-here
```

`.env` is in `.gitignore`. Never commit it.

## Run

**The app:**

```
streamlit run app.py
```

It opens at http://localhost:8501. The sample contract shows a saved result instantly and makes no API calls, so it works without an API key. Uploading a `.txt` or `.docx` contract runs the full pipeline and uses your API quota.

**The data** (needed for the evaluation, not for the app's sample):

```
python cuad_loader.py
```

This downloads CUAD-QA from Hugging Face and writes `data/contracts.jsonl`. The development and test contract lists are committed in `data/`.

**The evaluation:**

```
python run_eval.py          # shows the plan; makes no API calls
python run_eval.py --run    # runs or resumes the evaluation on the 20 test contracts
python evaluate.py eval     # scores it: writes results/metrics.json and results/errors.csv
```

The evaluation can stop at the daily token limit or after repeated connection failures, and carries on from the cache next time. The full evaluation used 147,466 tokens; with an empty cache, expect a similar amount, against a daily limit of 200,000 for this model. `evaluate.py` refuses to score a run that is incomplete, used different prompts, or has parts that failed because of a connection or server error.

**The tests** (no API calls):

```
python -m pytest
```

## Project layout

| Path | What it is |
|---|---|
| `app.py` | Streamlit app |
| `pipeline.py`, `first_pass.py`, `splitter.py`, `quote_check.py`, `llm.py` | The pipeline: splitting, both passes, quote check, statuses, API calls, caching and rate limiting |
| `config.py` | Model, prompt versions, limits and paths |
| `prompts/` | Prompt and definition files, versioned |
| `cuad_loader.py` | Converts CUAD and picks the development and test contracts |
| `run_eval.py`, `evaluate.py` | Runs and scores the evaluation |
| `results/` | Every result the README and write-up rely on |
| `samples/` | The app's sample contract and its saved result |
| `scripts/` | Development runs, evidence and the review pack |
| `tests/` | Unit and end-to-end tests with fake API replies |

## Limitations

- Only 20 test contracts, all US contracts from public filings, with 5 to 14 contracts per clause type. One or two cases move a percentage a lot.
- A single run. On the development contracts, a small change to one clause type's definition also changed some answers for other types, so some run-to-run variation is likely.
- Only contracts up to 40,000 characters were tested.
- CUAD's labels are imperfect, so some measured errors are label errors. The manual review was done by a non-lawyer.
- The quote check rejects quotes that differ from the contract only because of text-conversion damage, such as a page number in mid-sentence or a missing space. That caused 3 of the 7 missed clauses.
- `.docx` reading ignores headers, footers, footnotes and text boxes.

## Data and credit

Uses CUAD (the Contract Understanding Atticus Dataset) by The Atticus Project, licensed under CC BY 4.0: Hendrycks, Burns, Chen and Ball (2021), "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review". The clause definitions in `prompts/` are CUAD's. The sample contract in `samples/` is a CUAD contract.

## How this was built

Built with AI coding assistance (Claude Code). I chose and reviewed the prompts and evaluation decisions, and did the manual error review myself.
