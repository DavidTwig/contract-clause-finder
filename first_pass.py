"""First pass: ask the model for clauses in each chunk, then check every quote with code."""

import re

import config
import llm
from quote_check import check_quote
from splitter import split_text

_DELIMITER_RE = re.compile(r"</?\s*contract_text\s*>", re.IGNORECASE)


def load_definitions() -> dict[str, str]:
    """Parse prompts/category_definitions.txt into {category: definition}."""
    defs: dict[str, str] = {}
    current = None
    for line in (config.PROMPTS_DIR / "category_definitions.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            defs[current] = ""
        elif line.startswith("#") or not line.strip():
            continue
        elif current:
            defs[current] = (defs[current] + " " + line.strip()).strip()
    missing = set(config.CATEGORIES) - set(defs)
    if missing:
        raise ValueError(f"No definition for: {sorted(missing)}")
    return defs


def neutralise_delimiters(text: str) -> tuple[str, int]:
    """Stop contract text from closing or reopening our <contract_text> wrapper."""
    return _DELIMITER_RE.subn("[contract_text tag removed]", text)


def build_messages(chunk_text: str, categories: list[str]) -> list[dict]:
    defs = load_definitions()
    definitions = "\n".join(f"{c}: {defs[c]}" for c in categories)
    system = (config.PROMPTS_DIR / f"{config.FIRST_PASS_PROMPT}_system.txt").read_text(encoding="utf-8")
    user = (config.PROMPTS_DIR / f"{config.FIRST_PASS_PROMPT}_user.txt").read_text(encoding="utf-8")
    safe_text, _ = neutralise_delimiters(chunk_text)
    # str.replace, not str.format: the prompt contains literal JSON braces.
    return [
        {"role": "system", "content": system.replace("{category_definitions}", definitions).strip()},
        {"role": "user", "content": user.replace("{chunk_text}", safe_text).strip()},
    ]


def validate_findings(data) -> None:
    """Raise ValueError unless data looks like {"findings": [{"category", "quote", "reason"}, ...]}."""
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise ValueError('expected an object with a "findings" list')
    for item in data["findings"]:
        if not isinstance(item, dict):
            raise ValueError("each finding must be an object")
        for field in ("category", "quote", "reason"):
            if not isinstance(item.get(field), str):
                raise ValueError(f'finding is missing text field "{field}"')


def run_first_pass(text: str, categories: list[str]) -> dict:
    """Run the first pass and quote check over one contract.

    Returns {"chunks": [...], "findings": [...], "errors": [...]}. Each finding has
    status "passed" (quote found, offsets in the original contract), "failed_quote",
    or "wrong_category" (a category we did not ask about). Only "passed" can be shown.
    """
    chunks = split_text(text)
    findings, errors, chunk_log = [], [], []
    for chunk in chunks:
        _, n_tags = neutralise_delimiters(chunk["text"])
        try:
            reply = llm.chat_json(build_messages(chunk["text"], categories),
                                  config.FIRST_PASS_PROMPT, validate_findings)
        except llm.InvalidResponse as e:
            errors.append({"chunk": chunk["index"], "error": str(e)})
            chunk_log.append({"index": chunk["index"], "start": chunk["start"], "end": chunk["end"],
                              "status": "invalid_response", "delimiters_removed": n_tags})
            continue
        chunk_log.append({"index": chunk["index"], "start": chunk["start"], "end": chunk["end"],
                          "status": "ok", "cached": reply["cached"], "attempts": reply["attempts"],
                          "usage": reply["usage"], "n_findings": len(reply["data"]["findings"]),
                          "delimiters_removed": n_tags})
        for item in reply["data"]["findings"]:
            record = {"chunk": chunk["index"], "category": item["category"],
                      "quote": item["quote"], "reason": item["reason"]}
            if item["category"] not in categories:
                record.update(status="wrong_category", start=None, end=None)
            else:
                check = check_quote(item["quote"], chunk["text"], chunk["start"])
                record.update(status="passed" if check["ok"] else "failed_quote",
                              start=check["start"], end=check["end"])
            findings.append(record)
    return {"chunks": chunk_log, "findings": findings, "errors": errors}
