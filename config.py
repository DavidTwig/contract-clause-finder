"""Project settings, kept in one place so every script uses the same values."""

from pathlib import Path

# Use the Windows certificate store for HTTPS. Needed on this machine because
# AVG Antivirus re-signs HTTPS traffic with its own certificate, which Python's
# built-in certificate list does not trust. Harmless on machines without AVG.
import truststore

truststore.inject_into_ssl()

# --- Model -----------------------------------------------------------------
MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.1
# GPT-OSS is a reasoning model. "low" keeps hidden reasoning (which still counts
# towards token limits) as small as possible.
REASONING_EFFORT = "low"
MAX_COMPLETION_TOKENS = 4_096   # upper bound per reply (reasoning + answer)

# --- Prompts (files in prompts/). Bump the version whenever a prompt changes.
# History: first_pass_v1 used category_definitions_v1 (Stage 2).
#          first_pass_v2 = same text as v1, with category_definitions_v2 (Governing Law quote rule).
#          category_definitions_v3 = v2 wording with the quote rule split out as "Quote guidance"
#          (first pass only). first_pass_v2 renders byte-identically from v2 and v3 (tested).
FIRST_PASS_PROMPT = "first_pass_v2"
SECOND_PASS_PROMPT = "second_pass_v1"
DEFINITIONS = "category_definitions_v3"
SECTION_MAX_SIDE_CHARS = 1_500  # second pass: at most this much context either side of the quote

# --- Rate limits (Groq's published limits for openai/gpt-oss-120b) ---------
TOKENS_PER_MINUTE = 8_000
REQUESTS_PER_MINUTE = 30
TOKENS_PER_DAY = 200_000
REPLY_TOKENS_ESTIMATE = 1_500   # used by the throttle before a call, when the real size is unknown
MAX_RETRY_WAIT_SECONDS = 120    # a longer retry-after means the daily limit: stop instead of waiting

# --- Splitting -------------------------------------------------------------
CHARS_PER_TOKEN = 4          # rough estimate, as in the spec
MAX_CHUNK_TOKENS = 3_000
OVERLAP_TOKENS = 200

# --- Clause types (exact CUAD category names) -------------------------------
CATEGORIES = [
    "Change of Control",
    "Termination for Convenience",
    "Cap on Liability",
    "Anti-Assignment",
    "Governing Law",
]

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CONTRACTS_PATH = DATA_DIR / "contracts.jsonl"
DEV_TITLES_PATH = DATA_DIR / "dev_titles.json"
EVAL_TITLES_PATH = DATA_DIR / "eval_titles.json"
PROMPTS_DIR = ROOT / "prompts"
CACHE_DIR = ROOT / "cache"
RESULTS_DIR = ROOT / "results"

# --- Sampling --------------------------------------------------------------
SEED = 42
DEV_SIZE = 5
DEV_MIN_PER_CATEGORY = 2
EVAL_SIZE = 20
EVAL_MAX_CHARS = 40_000
EVAL_MIN_PER_CATEGORY = 5
