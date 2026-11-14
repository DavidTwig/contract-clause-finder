# Contract Clause Finder: write-up

## The need

When one company buys another, lawyers carry out due diligence, reading the target company's contracts to find risks. They read large numbers of contracts to find a few clauses that matter. Five common ones, out of many, are change of control, termination for convenience, caps on liability, restrictions on assignment and governing law. Much of their time goes on finding these clauses rather than judging them. A tool that finds them could save lawyers time, as long as it shows exactly what it relied on and the lawyer knows what it might miss.

## What I built

I built a prototype that uses a large language model (openai/gpt-oss-120b) to look for those five clause types in a contract. Contracts were too long for the free API's per-minute limit, and LLMs can miss details buried in long inputs, so I split each contract into sections at its headings, with some overlap so that no clause is cut in half. The model reads each section and quotes any of the five clause types word for word. Code then checks that each quote really appears in the contract, which catches made-up or misquoted text. Quotes that pass go to a second pass, where the model is shown the quote with the text around it and asked to confirm or reject it. Each clause type then gets one of three statuses: Verified, Needs review, or Not found: check. A simple web app shows the results, and you can see each quote in its place in the contract.

I tested it on 20 contracts from CUAD, a public dataset of labelled US commercial contracts. I tuned the prompts on 5 different contracts beforehand and didn't change them once testing started.

## Results

| Clause type | Contracts with the clause | Precision | Recall | Passages matched |
|---|---|---|---|---|
| Change of Control | 5 | 3/3 (100%) | 3/5 (60%) | 3/7 (43%) |
| Termination for Convenience | 6 | 5/9 (56%) | 5/6 (83%) | 5/7 (71%) |
| Cap on Liability | 6 | 4/4 (100%) | 4/6 (67%) | 3/16 (19%) |
| Anti-Assignment | 14 | 13/13 (100%) | 13/14 (93%) | 12/20 (60%) |
| Governing Law | 14 | 13/13 (100%) | 13/14 (93%) | 13/14 (93%) |
| **All five** | 45 | **38/42 (90%)** | **38/45 (84%)** | **36/64 (56%)** |

**Precision:** of the contracts the tool flagged as having a clause type, how many CUAD agrees really have one. **Recall:** of the contracts CUAD says have a clause type, how many the tool caught. **Passages matched:** how many of CUAD's marked passages the tool's quotes covered by at least half. Overall, the tool is good at spotting whether a contract has a clause type, with 90% precision and 84% recall, but weaker at finding every passage of that type, with 56% of passages matched.

## What the manual review found

I checked 16 of the 28 cases where my tool and CUAD disagreed.

- **The tool's "wrong" findings mostly weren't wrong.** None of the 9 findings that didn't match CUAD was a clear model error. Five were ambiguous, one was a clause CUAD missed, and three were correct quotes that the quote check rejected over a page number or a missing space. CUAD does mark those three passages.
- **The tool's real mistakes were missed clauses.** I found 4 model errors. Merger wording was quoted as Anti-Assignment but not as Change of Control, which explains both Change of Control misses. The tool missed an exclusion of indirect loss, which is exactly what the Cap on Liability definition names. It also missed a repair-or-replace clause, although it treated a similar clause in the same contract as a cap.
- **CUAD's labels have problems too.** It marks two indemnities as caps on liability, even though an indemnity adds liability rather than limiting it, and one of its marked passages stops mid-word.

## What failed and what I would change

- **The quote check is too strict.** All 4 failed quotes (4 of 54) were the right text, affected only by conversion damage like a stray page number or a missing space. In 3 of those cases, a correct clause was downgraded to Needs review. I would remove page numbers from the contract text before checking and allow for missing spaces. I wouldn't ignore numbers when matching, because in a contract "12 months" and "2 months" mean very different things.
- **The second pass added nothing measurable.** It made 0 rejections in 69 checks across development and testing, and used 24% of the test tokens. I would cut it, or redesign it to catch the mistakes the tool actually makes, like filing merger wording under the wrong clause type.
- **Cap on Liability is still weak.** The tool misses some Cap on Liability clauses and many of their passages, including exclusions of certain types of loss. These were still missed after I widened the definition, which suggests that changing a definition's wording doesn't guarantee the model follows it.
- **End-of-term opt-outs:** 2 of the 4 Termination for Convenience false positives look like rights to end the contract at the end of a term rather than at any time.

## How a lawyer would use it

A lawyer would use the tool as a first pass over a set of contracts. They would read the Needs review items first, since something was found but couldn't be confirmed. For Verified items, they would check each quote in its context: it's probably right, but still worth a look. Not found: check also needs reviewing. It was right 50 times out of 54 (93%), which is useful but not reliable enough to skip reading, because a missed clause is the costliest error. Verified means the quoted wording exists word for word in the contract and passed a second review by the model, but it doesn't mean every relevant clause of that type was found.

## Build or buy

Commercial tools such as Harvey or Microsoft Copilot cover far more tasks, work within the documents and systems lawyers already use, and come with security, support and contractual protections that my prototype doesn't have. I haven't tested these tools, so I can't compare their accuracy with mine. In my view, a firm should buy a commercial tool for general use, and build only for a narrow, repeated task where it wants to control exactly what counts as a match, see the evidence for every answer, and measure accuracy on its own contracts. The part of this project I would reuse most is the evaluation, not the tool, because a labelled test set and scoring like this could be used to test a bought tool before relying on it. Any tool, bought or built, also needs agreed terms for sending client documents to a model provider; my prototype sends text to an external service.

## Limitations

- 20 US contracts from public filings, with 5 to 14 contracts per clause type, so one or two cases move a percentage a lot.
- A single run. On the development contracts, a small change to one clause type's definition also changed some answers for other types, so some run-to-run variation is likely.
- Only contracts up to 40,000 characters were tested.
- I am not a lawyer. I did the manual review myself, and it covered 16 of the 28 disagreements.

Figures come from `results/metrics.json`, `results/error_review.csv`, `results/eval.json`, `results/stage3_dev.json` and `results/stage3_dev_defs_v4.json`.
