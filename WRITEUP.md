# Contract Clause Finder: write-up

## The need

In due diligence, lawyers read large numbers of contracts to find a few clauses that matter to a deal: change of control, termination for convenience, caps on liability, restrictions on assignment, and governing law. Much of that time goes on finding clauses rather than judging them. A tool that finds candidate clauses and quotes them exactly could save some of that time, provided the reviewer can see what it relied on and knows what it may have missed.

## What I built

A prototype that looks for those five clause types in a contract. A large language model (openai/gpt-oss-120b) reads the contract in sections and quotes any matching clause word for word. A plain code check then confirms that each quote appears in the contract. Only quotes that pass go to a second pass, which shows the model each quote again with its surrounding section and asks it to confirm or reject it. Each clause type gets one of three statuses: **Verified**, **Needs review** or **Not found: check**. A simple web app shows the results, with each quote in context.

I tested it on 20 contracts from CUAD, a public dataset of labelled US commercial contracts. I developed the prompts on 5 other contracts and froze them before the test.

## Results

| Clause type | Contracts with the clause | Precision | Recall | Passages matched |
|---|---|---|---|---|
| Change of Control | 5 | 3/3 (100%) | 3/5 (60%) | 3/7 (43%) |
| Termination for Convenience | 6 | 5/9 (56%) | 5/6 (83%) | 5/7 (71%) |
| Cap on Liability | 6 | 4/4 (100%) | 4/6 (67%) | 3/16 (19%) |
| Anti-Assignment | 14 | 13/13 (100%) | 13/14 (93%) | 12/20 (60%) |
| Governing Law | 14 | 13/13 (100%) | 13/14 (93%) | 13/14 (93%) |
| **All five** | 45 | **38/42 (90%)** | **38/45 (84%)** | **36/64 (56%)** |

Precision: of the contracts marked Verified for a clause type, how many CUAD agrees contain one. Recall: of the contracts CUAD says contain one, how many were Verified. Passages matched: of the passages CUAD marks, how many a Verified quote overlapped by at least half. Finding the contract is much stronger than finding every passage in it.

## What the manual review found

I reviewed 16 of the 28 disagreements with CUAD.

- **None of the 9 findings the scoring counted as not matching CUAD was a clear model error.** 5 were ambiguous, 1 was a clause CUAD missed (either party may end the contract on six months' notice for any reason other than breach), and 3 were correct quotes that the quote check rejected. CUAD does mark the passages in those 3 cases.
- **4 were model errors:** 3 missed clauses and 1 missed passage in a contract that was otherwise found. Two patterns explain three of them. Merger wording was quoted as Anti-Assignment but not as Change of Control, which explains both Change of Control misses. And an exclusion of indirect loss was not treated as a cap on liability. The fourth was the missed passage: an exclusive-remedy clause (repair or exchange) was missed, although the model treated a similar exclusive-remedy clause in the same contract as a cap.
- **CUAD's labels have problems too.** It marks two indemnities as caps on liability, although an indemnity adds liability rather than limiting it, and one marked passage stops mid-word.

## What failed and what I would change

- **The quote check is too strict.** All 4 failed quotes (4 of 54) differed from the contract only because of text-conversion damage: a stray page number or a missing space. In 3 cases this moved a correct clause to Needs review. I would remove page-number artefacts from the contract text before matching and allow missing spaces. I would not ignore stray numbers when matching, because a missing digit can change the meaning ("12 months" against "2 months").
- **The second pass added nothing measurable:** 0 rejections in 69 checks across development and test, for 24% of the test tokens. I would cut it or redesign it, for example to look for the clause-type mix-ups above.
- **Cap on Liability passages:** exclusions of types of damage were still missed after I widened the definition.
- **End-of-term opt-outs:** 2 of the 4 Termination for Convenience false positives look like rights to end the contract at the end of a term rather than at any time.

## How a lawyer would use it

As a first pass over a set of contracts: read the Needs review items first, check each Verified quote in its context, and treat Not found: check as unchecked rather than absent. Not found was right 50 times out of 54 (93%). That is useful, but not reliable enough to skip reading. **Verified** means the quoted wording exists word for word in the contract and passed a second review. It does not mean every relevant clause of that type was found.

## Build or buy

Commercial tools such as Harvey or Microsoft Copilot cover far more tasks, work inside the documents and systems lawyers already use, and come with security, support and contractual protections that a prototype does not have. I have not tested them, so I cannot compare their accuracy with this. My view is that a firm should buy for general use. Building makes sense for a narrow, repeated task where the firm wants to decide exactly what counts as a match, show the evidence for every answer, and measure accuracy on its own contracts. The part of this project I would reuse most is the evaluation, not the tool: a labelled test set and scoring like this could be used to test a bought tool before relying on it. Any tool, bought or built, also needs agreed terms for sending client documents to a model provider. This prototype sends text to an external service.

## Limitations

- 20 US contracts from public filings, with 5 to 14 contracts per clause type, so one or two cases move a percentage a lot.
- A single run. On the development contracts, a small change to one clause type's definition also changed some answers for other types, so some run-to-run variation is likely.
- Only contracts up to 40,000 characters were tested.
- I am not a lawyer. I did the manual review myself, and it covered 16 of the 28 disagreements.

Figures come from `results/metrics.json`, `results/error_review.csv`, `results/eval.json`, `results/stage3_dev.json` and `results/stage3_dev_defs_v4.json`.
