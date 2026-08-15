"""Paths and deployment settings for the agente-local project. See
PROJECT_TRUTH.md for provenance.

PORT must never be 8090 or 8091 — those belong to the search-assistant
project (llm/harness). Only one llama-server fits in this card's 16GB, so
agente-local and llm/harness cannot run at the same time regardless of port.
"""
import os
from pathlib import Path

MODEL_PATH = "/home/jkzero/models/Qwen3.8-27B/Qwen3.8-27B-IQ4_XS.gguf"
BIN_PATH = "/home/jkzero/llama.cpp/build/bin/llama-server"
PORT = int(os.environ.get("AGENTE_LOCAL_PORT", "8092"))

# fast: 15/15 in ~72s/run. deep: 14/15 in ~133s/run. 8192 ctx is enough
# because tools deliver fragments, not whole files. (3 runs each, 2026-08-15)
DEFAULT_PROFILE = os.environ.get("AGENTE_LOCAL_DEFAULT_PROFILE", "fast")

ROOT = Path.home().resolve()
MAX_CHARS = 4000
GREP_MAX_MATCHES = 200
MAX_HISTORY_CHARS = int(os.environ.get("AGENTE_LOCAL_MAX_HISTORY_CHARS", "12000"))
DELETE_REVIEW_MAX_LINES = int(os.environ.get("AGENTE_LOCAL_DELETE_REVIEW_MAX_LINES", "50"))
