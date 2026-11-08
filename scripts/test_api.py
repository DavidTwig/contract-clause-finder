"""One-line test call to Groq: checks the key, the model, JSON mode and token usage.

Run:  .venv/Scripts/python scripts/test_api.py
Never prints the API key.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from groq import Groq

import config

load_dotenv(config.ROOT / ".env")
if not os.getenv("GROQ_API_KEY"):
    sys.exit("GROQ_API_KEY is missing from .env")

client = Groq()  # reads GROQ_API_KEY from the environment
response = client.chat.completions.create(
    model=config.MODEL,
    temperature=config.TEMPERATURE,
    reasoning_effort=config.REASONING_EFFORT,
    include_reasoning=False,
    response_format={"type": "json_object"},
    messages=[{"role": "user", "content": 'Reply with JSON only: {"status": "ok"}'}],
)

print("Model:  ", response.model)
print("Reply:  ", response.choices[0].message.content)
print("Parsed: ", json.loads(response.choices[0].message.content))
print("Usage:  ", response.usage.model_dump(exclude_none=True))
