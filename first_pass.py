"""First pass: ask the model for clauses in each chunk, then check every quote with code."""

import re

import config
import llm
from quote_check import check_quote
from splitter import split_text

_GUIDANCE_PREFIX = "Quote guidance:"


def _parse_definitions(name: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse prompts/<name>.txt into ({category: definition}, {category: quote guidance})."""
    defs: dict[str, str] = {}
    guidance: dict[str, str] = {}
    current = None
    for line in (config.PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            defs[current] = ""
        elif line.startswith("#") or not line.strip() or current is None:
            continue
        elif line.startswith(_GUIDANCE_PREFIX):
            guidance[current] = line[len(_GUIDANCE_PREFIX):].strip()
        else:
            defs[current] = (defs[current] + " " + line.strip()).strip()
    missing = set(config.CATEGORIES) - set(defs)
    if missing:
        raise ValueError(f"No definition for: {sorted(missing)}")
    return defs, guidance


def load_definitions(name: str = config.DEFINITIONS) -> dict[str, str]:
    """{category: definition}. Used by BOTH passes. Never includes quote guidance."""
    return _parse_definitions(name)[0]


def load_quote_guidance(name: str = config.DEFINITIONS) -> dict[str, str]:
    """{category: quote guidance}, for the FIRST PASS ONLY. Categories without guidance are absent."""
    return _parse_definitions(name)[1]


def neutralise_tags(text: str, tags: tuple[str, ...]) -> tuple[str, int]:
    """Replace any opening or closing <tag> (any case, stray spaces) so contract text
    cannot close or reopen the wrappers around it. Returns (safe_text, count)."""
    pattern = re.compile(r"<\s*/?\s*(" + "|".join(map(re.escape, tags)) + r")\s*>", re.IGNORECASE)
    return pattern.subn(lambda m: f"[{m.group(1).lower()} tag removed]", text)


def neutralise_delimiters(text: str) -> tuple[str, int]:
    """First pass: stop contract text from closing or reopening the <contract_text> wrapper."""
    return neutralise_tags(text, ("contract_text",))


def render_definitions(categories: list[str], name: str = config.DEFINITIONS) -> str:
    """First-pass definitions block: 'Category: definition [quote guidance]' per line."""
    defs, guidance = _parse_definitions(name)
    return "\n".join(f"{c}: {defs[c]}" + (f" {guidance[c]}" if c in guidance else "") for c in categories)


def build_messages(chunk_text: str, categories: list[str]) -> list[dict]:
    definitions = render_definitions(categories)
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


def normalise_category(name: str, categories: list[str]) -> str | None:
    """Match the model's category name to one we asked for, ignoring case and outer spaces only."""
    lookup = {c.lower(): c for c in categories}
    return lookup.get(name.strip().lower())


def run_first_pass(text: str, categories: list[str]) -> dict:
    """Run the first pass and quote check over one contract.

    Returns {"chunks": [...], "findings": [...], "errors": [...]}. Each finding has
    status "passed" (quote found, offsets in the original contract), "failed_quote",
    or "wrong_category" (a category we did not ask about). Only "passed" can be shown.
    A chunk whose call fails or returns invalid output has status "failed" in "chunks".
    llm.DailyLimitReached is not caught: the caller must stop the run.
    """
    chunks = split_text(text)
    findings, errors, chunk_log = [], [], []
    for chunk in chunks:
        _, n_tags = neutralise_delimiters(chunk["text"])
        try:
            reply = llm.chat_json(build_messages(chunk["text"], categories),
                                  config.FIRST_PASS_PROMPT, validate_findings)
        except (llm.InvalidResponse, llm.CallFailed) as e:
            errors.append({"chunk": chunk["index"], "error": f"{type(e).__name__}: {e}"})
            chunk_log.append({"index": chunk["index"], "start": chunk["start"], "end": chunk["end"],
                              "status": "failed", "delimiters_removed": n_tags})
            continue
        chunk_log.append({"index": chunk["index"], "start": chunk["start"], "end": chunk["end"],
                          "status": "ok", "cached": reply["cached"], "attempts": reply["attempts"],
                          "usage": reply["usage"], "n_findings": len(reply["data"]["findings"]),
                          "delimiters_removed": n_tags})
        for item in reply["data"]["findings"]:
            category = normalise_category(item["category"], categories)
            record = {"chunk": chunk["index"], "category": category or item["category"],
                      "model_category": item["category"], "quote": item["quote"], "reason": item["reason"]}
            if category is None:
                record.update(status="wrong_category", start=None, end=None)
            else:
                check = check_quote(item["quote"], chunk["text"], chunk["start"])
                record.update(status="passed" if check["ok"] else "failed_quote",
                              start=check["start"], end=check["end"])
            findings.append(record)
    return {"chunks": chunk_log, "findings": findings, "errors": errors}
