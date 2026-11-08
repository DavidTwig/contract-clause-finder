"""The only place that talks to Groq: caching, throttling, retries, JSON checks, usage logging.

Never prints or logs the API key.
"""

import datetime as dt
import hashlib
import json
import os
import time
from collections import deque

from dotenv import load_dotenv
from groq import BadRequestError, Groq, RateLimitError

import config

RESPONSE_CACHE = config.CACHE_DIR / "responses"
USAGE_LOG = config.CACHE_DIR / "usage_log.jsonl"


class DailyLimitReached(RuntimeError):
    """Groq asked us to wait longer than MAX_RETRY_WAIT_SECONDS: almost certainly the daily limit.
    Stop now; cached results mean the next run carries on from here."""


class InvalidResponse(RuntimeError):
    """The model's reply was not valid JSON of the expected shape, even after one retry."""


_client = None
_recent: deque = deque()  # (timestamp, tokens) of calls in the last 60 seconds


def _get_client() -> Groq:
    global _client
    if _client is None:
        load_dotenv(config.ROOT / ".env")
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY is missing from .env")
        _client = Groq(max_retries=0)  # we handle retries ourselves, so every 429 is visible
    return _client


def cache_key(prompt_version: str, messages: list[dict], params: dict) -> str:
    blob = json.dumps({"model": config.MODEL, "prompt_version": prompt_version,
                       "messages": messages, "params": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def tokens_today() -> int:
    """Total tokens of real (non-cached) calls logged today, UTC."""
    if not USAGE_LOG.exists():
        return 0
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    total = 0
    with open(USAGE_LOG, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["date"] == today:
                total += row["total_tokens"]
    return total


def _throttle(estimated_tokens: int) -> None:
    """Wait until this call fits within the per-minute token and request limits."""
    while True:
        now = time.monotonic()
        while _recent and now - _recent[0][0] > 60:
            _recent.popleft()
        used = sum(t for _, t in _recent)
        if (used + estimated_tokens <= config.TOKENS_PER_MINUTE
                and len(_recent) < config.REQUESTS_PER_MINUTE) or not _recent:
            return
        wait = 60 - (now - _recent[0][0]) + 0.5
        print(f"    throttle: {used:,} tokens in last minute, waiting {wait:.0f}s")
        time.sleep(wait)


def _log_usage(prompt_version: str, usage, attempt: int) -> dict:
    details = getattr(usage, "completion_tokens_details", None)
    row = {
        "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "date": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "model": config.MODEL,
        "prompt_version": prompt_version,
        "attempt": attempt,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        "total_tokens": usage.total_tokens,
    }
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _call_once(messages: list[dict], params: dict, estimated_tokens: int):
    """One API call, retrying only on 429 (honouring retry-after)."""
    for _ in range(10):
        _throttle(estimated_tokens)
        try:
            response = _get_client().chat.completions.create(model=config.MODEL, messages=messages, **params)
        except RateLimitError as e:
            retry_after = float(e.response.headers.get("retry-after", 30))
            print(f"    429 rate limit: retry-after {retry_after:.0f}s")
            if retry_after > config.MAX_RETRY_WAIT_SECONDS:
                raise DailyLimitReached(f"retry-after {retry_after:.0f}s; tokens today {tokens_today():,}") from e
            time.sleep(retry_after + 1)
            continue
        _recent.append((time.monotonic(), response.usage.total_tokens))
        return response
    raise RuntimeError("Still rate limited after 10 attempts")


def chat_json(messages: list[dict], prompt_version: str, validate) -> dict:
    """Send messages, return the parsed JSON reply.

    `validate(obj)` must raise ValueError if the parsed object has the wrong shape.
    Returns {"data", "usage", "cached", "attempts"}. Re-runs with the same input cost nothing.
    """
    params = {
        "temperature": config.TEMPERATURE,
        "reasoning_effort": config.REASONING_EFFORT,
        "include_reasoning": False,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": config.MAX_COMPLETION_TOKENS,
    }
    key = cache_key(prompt_version, messages, params)
    path = RESPONSE_CACHE / f"{key}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        return {"data": cached["data"], "usage": cached["usage"], "cached": True, "attempts": 0}

    estimated = sum(len(m["content"]) for m in messages) // config.CHARS_PER_TOKEN + config.REPLY_TOKENS_ESTIMATE
    errors = []
    for attempt in (1, 2):  # one retry if the JSON is invalid
        try:
            response = _call_once(messages, params, estimated)
        except BadRequestError as e:  # e.g. Groq's json_validate_failed in JSON mode
            errors.append(f"attempt {attempt}: API 400 {getattr(e, 'code', '')}: {str(e)[:200]}")
            continue
        usage = _log_usage(prompt_version, response.usage, attempt)
        print(f"    tokens: prompt {usage['prompt_tokens']:,}, completion {usage['completion_tokens']:,} "
              f"(reasoning {usage['reasoning_tokens']}) | today {tokens_today():,} / {config.TOKENS_PER_DAY:,}")
        content = response.choices[0].message.content or ""
        try:
            data = json.loads(content)
            validate(data)
        except ValueError as e:  # json.JSONDecodeError is a ValueError
            errors.append(f"attempt {attempt}: {e}: {content[:200]!r}")
            continue
        RESPONSE_CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"data": data, "usage": usage, "model": response.model},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        return {"data": data, "usage": usage, "cached": False, "attempts": attempt}
    raise InvalidResponse("; ".join(errors))
