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
