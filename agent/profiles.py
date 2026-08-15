"""Named llama-server profiles for agente-local. See PROJECT_TRUTH.md for
certification evidence (eval.py runs, interactive t/s, prefill/generation
numbers) behind each profile below.

--spec-draft-n-max 3 is FORBIDDEN: it benchmarks faster but dies with CUDA
OOM (cudaGraphLaunch) on real-sized prompts. Loading successfully does not
mean it works.
"""
from config import MODEL_PATH, BIN_PATH

PROFILES = {
    "fast": [
        BIN_PATH, "-m", MODEL_PATH,
        "-ngl", "99", "-fa", "on", "-c", "8192", "-ub", "256", "-t", "6",
        "--parallel", "1",
        "--spec-type", "draft-mtp", "--spec-draft-n-max", "2",
    ],
    "deep": [
        BIN_PATH, "-m", MODEL_PATH,
        "-ngl", "99", "-fa", "on", "-c", "32768", "-ub", "256",
        "-ctk", "q8_0", "-ctv", "q8_0", "-t", "6",
        "--parallel", "1",
    ],
}
