# PROJECT_TRUTH — agente-local

This is a separate project from `llm/harness`. Different models, different
hardware assumptions. Do not inherit facts from `llm/harness/PROJECT_TRUTH.md`.

Every fact below carries the command that produced it and the date it was
verified. Facts reported by the user from a prior chat session (not run by
a command in this repo) are marked as such and are not independently
verified.

## Model / binary (reported by user, 2026-08-15; confirmed to exist by
`ls -la` and `llama-server --version` in this session, 2026-08-15)

MODEL: `/home/jkzero/models/Qwen3.8-27B/Qwen3.8-27B-IQ4_XS.gguf`
BINARY: `/home/jkzero/llama.cpp/build/bin/llama-server` (build 10434, commit 7e4c0a968)

Verified this session:
```
$ ls -la /home/jkzero/models/Qwen3.8-27B/Qwen3.8-27B-IQ4_XS.gguf /home/jkzero/llama.cpp/build/bin/llama-server
-rwxrwxr-x 1 jkzero jkzero       17904 Aug 14 16:49 /home/jkzero/llama.cpp/build/bin/llama-server
-rw-rw-r-- 1 jkzero jkzero 15705861088 Aug 14 17:02 /home/jkzero/models/Qwen3.8-27B/Qwen3.8-27B-IQ4_XS.gguf

$ /home/jkzero/llama.cpp/build/bin/llama-server --version
version: 0.1.0-dev (build 10434, commit 7e4c0a968)
built with GNU 15.2.0 for Linux x86_64
```
Build/commit match what the user reported.

Model released 2026-08-14 per user; measured in a chat session, not yet
written to disk before this file.

## Hardware

RTX 5060 Ti 16GB, headless (desktop on iGPU) (reported by user, 2026-08-15,
not independently verified).

User reported 16298 MiB free at time of certification (chat session,
2026-08-15, not run by a command in this repo).

This session's own reading (`nvidia-smi --query-gpu=name,memory.total,memory.free,memory.used --format=csv`,
2026-08-15 08:51):
```
name, memory.total [MiB], memory.free [MiB], memory.used [MiB]
NVIDIA GeForce RTX 5060 Ti, 16311 MiB, 146 MiB, 15705 MiB
```
Only 146 MiB free at this moment — a `llama-server` process is currently
resident (`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`,
2026-08-15 08:51):
```
pid, process_name, used_gpu_memory [MiB]
15943, /home/jkzero/llama.cpp/build/bin/llama-server, 15684 MiB
```
This contradicts the "16298 MiB free" figure at the moment of this reading —
not a discrepancy in the certification itself, just a reminder that free VRAM
depends on what else is resident at the time.

## Model / hardware notes (reported by user, 2026-08-15, not verified in
this session)

- The model's vocabulary is 248,320 tokens, making the prompt-processing
  buffer large; the 512 default `-ub` OOMs on this card.
- CPU: Ryzen 5 5600G, 6 cores.

## Profile "fast" (reported by user, 2026-08-15, not reproduced in this session)

```
-ngl 99 -fa on -c 8192 -ub 256 -t 6 --parallel 1
--spec-type draft-mtp --spec-draft-n-max 2
```

Certified by (per user): `eval.py` suite run twice (9/10 in 191.4s and
190.4s); interactive chat 43.3 t/s on prose, 58.5 t/s on code.

## Profile "deep" (reported by user, 2026-08-15, not reproduced in this session)

```
-ngl 99 -fa on -c 32768 -ub 256 -ctk q8_0 -ctv q8_0 -t 6 --parallel 1
```

Certified by (per user): real inference on a 17549-token prompt
(`research.py` in full), correct answer, prefill 928 t/s, generation 23.4
t/s. A 24576 variant of the same profile ran `eval.py` twice at 10/10
(280.9s, 265.5s).

`-ctk`/`-ctv q8_0` halves the KV cache; this is what makes `-c 32768` fit at
all (per user).

## reasoning_effort and long-context analysis on "deep" (reported by user,
chat session 2026-08-14, not verified in this session)

FACT — reasoning_effort must be lowered for long analysis on the deep profile.

Same task both times: the full pre-cleanup research.py (prompt 17,635
tokens) with a request to classify shadowed vs chained definitions,
temperature 0.2, deep profile at -c 32768.

With the model default (reasoning_effort xhigh) and max_tokens 12000:
predicted_n hit exactly 12000 and content came back EMPTY — the entire
budget was consumed by reasoning. ~8.7 minutes at 22.8 t/s, no answer.

With reasoning_effort=medium and max_tokens 14000: correct analysis
returned in ~4 minutes — 5,758 tokens generated, 13,004 characters of
reasoning, 23.2 t/s.

Note this only bites when a large prompt leaves little room; it did not
occur in any eval run, where tools deliver fragments.

## FORBIDDEN (reported by user, 2026-08-15, not reproduced in this session)

`--spec-draft-n-max 3`. Benchmarks at 58 t/s on a 26-token prompt but dies
with CUDA error out of memory in `cudaGraphLaunch` on the first real-sized
request. Loading successfully does not mean it works.

## Port (assigned by user, 2026-08-15)

PORT = 8092 (`config.py`, env-overridable via `AGENTE_LOCAL_PORT`). 8090 and
8091 belong to the search-assistant project (`llm/harness`) and must never
be used here.

Only one llama-server fits in this card's 16GB, so agente-local and
llm/harness cannot run at the same time regardless of port (reported by
user, 2026-08-15).

Corroborated this session (`nvidia-smi --query-gpu=... --format=csv`,
2026-08-15 08:51): with one llama-server resident (15684 MiB used), only 146
MiB of the 16311 MiB card was free — not enough for a second model.

Also confirmed this session (`ss -ltnp`, 2026-08-15): a llama-server started
by hand (not by this module) was bound to 127.0.0.1:8092, pid 15943, and
responded 200 on `/health`. `agent.server.current_profile()` against that
process returned `"unknown"`, as required — it did not assume a profile just
because a server was present.
