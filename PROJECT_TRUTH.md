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

## Per-profile history cap (reported by user, 2026-08-15, not run by a
command in this session)

MEASURED: with `agent.profiles.MAX_HISTORY_CHARS` set asymmetrically
(`{"fast": 500, "deep": 40000}`), the `chain` task escalated on
`history_capped` and `deep` completed in 3 steps without being capped.
Under the prior single shared cap of 500 (applied to both profiles), `deep`
was capped 12 times and took all 14 steps — identical to `fast`, so the
escalation bought nothing.

NOT MEASURED / ESTIMATE: the `deep` value of 40000 itself is an estimate
derived from the 32768/8192 context ratio between the two profiles, not
from measurement. The cap has never fired at the real `fast` setting of
12000 in any eval run.

## delete_lines escalation policy (reported by user, 2026-08-15, not run by
a command in this session)

The gate has two conditions: STRUCTURAL (range must map to exactly one
top-level definition plus optional trailing blanks; .py only, since it
needs ast) and SIZE (over DELETE_REVIEW_MAX_LINES, all file types). Either
one refuses the deletion unless override is set.

The override parameter is deliberately absent from SYSTEM, so the model
cannot invoke it. Reason, worth recording: max_steps is injected into the
planner prompt and the model demonstrably adapts to it, so any unlock the
model can see is not a control.

ESTIMATE, NOT MEASURED: DELETE_REVIEW_MAX_LINES = 50. The nine real
deletions performed on 2026-08-15 ran 9, 13, 21, 32, 37, 40, 40, 44 and 77
lines, so 50 flags only the largest. No measurement supports the number;
the structural check is the real safeguard.

KNOWN CONSEQUENCE: two-part _orig_ chain deletions (e.g. the result_score
wrapper at 1719-1750, which includes the _original_result_score assignment
alongside the def) will now always require the human override, because
they contain a top-level statement in addition to the definition. This is
intended — that deletion is the near-miss that motivated the policy.

## local_task raw_text/call_failed fix (reported by user, 2026-08-15, not
run by a command in this session)

THE BUG: local_task returned status OK with the model's raw reasoning as
the answer. Causal chain: the planner runs enable_thinking=False but the
27B spends its budget in reasoning_content anyway, leaving content empty;
llm_json falls back to reasoning_content, which is never JSON;
_json_or_text wraps it as {"answer": <raw>, "raw_text": True}; and
local_task, finding no "tool" key, returned it as a successful answer.

THE FIX: local_task now checks raw_text and call_failed before the
done/tool branch and returns status ERROR. agent/llm.py deliberately
unchanged — the flags were already being set, they were just ignored.

MEASURED, chain x20 after the fix: 18/20 passed, with the status breakdown
ERROR/False 1, OK/False 1, OK/True 18. One of the two failures was a
budget overrun, correctly labelled for the first time.

CONSEQUENCE FOR ALL EARLIER NUMBERS: every eval run before this fix
counted budget overruns as reasoning failures. The chain reasoning-failure
rate recorded earlier (~1 in 10 across 48 observations) is inflated by an
unknown amount. Observed budget-overrun rate is roughly 5%. The clean
figure, once overruns were eliminated (see "PLANNER_MAX_TOKENS change"
below): 3 failures in 40 runs, ~7.5%.

NOT FIXED, noted only: max_tokens=900 is hardcoded in the llm_json call
inside local_task; llm_json's own default is 800.

## PLANNER_MAX_TOKENS change (reported by user, 2026-08-15, not run by a
command in this session)

- CHANGE: the planner's max_tokens was hardcoded to 900 in local_task. It
  is now config.PLANNER_MAX_TOKENS, default 3000, env-overridable as
  AGENTE_LOCAL_PLANNER_MAX_TOKENS, with an optional per-call max_tokens
  parameter on local_task.
- MEASURED, chain x20 before (900) vs after (3000): budget overruns went
  from 1 to 0; both batches passed 18/20; median seconds went from ~16.5
  to 15.7, max 26.8 on a single 4-step run. Raising the ceiling cost no
  time — the model does not consume the extra budget, it only needed the
  ceiling out of the way on the rare long run.
- MEASURED, clean chain reasoning-failure rate: with overruns eliminated,
  3 failures in 40 runs (~7.5%) across the two post-2d7e07c batches. All
  earlier figures conflated budget overruns with reasoning failures and
  should not be cited.
- NOT TESTED: reasoning_effort (xhigh|medium|low) is never sent by
  agent/llm.py, which only passes chat_template_kwargs.enable_thinking.
  A recorded case (17,635-token prompt: empty at xhigh/12000 tokens in
  ~8.7 min, correct at medium/14000 tokens in ~4 min) suggests runaway
  deliberation, not budget size, is the underlying issue.

## chain / function_ranges two-arm experiment (reported by user, 2026-08-15,
not run by a command in this session)

TWO-ARM EXPERIMENT (function_ranges removed from TOOLS and SYSTEM,
everything else identical): WITHOUT it, chain passed 23/25 (92%); WITH it,
20/23 (87%). The difference runs in the opposite direction and is inside
the noise. function_ranges does NOT improve correctness.

WHAT function_ranges DOES buy, measured and unambiguous: steps (3 with it
vs 5-6 without) and time (~16.5s vs ~22s median). Speed and determinism,
not accuracy.

THE FAILURE MODE is constant and inherent to the model on this task: it
describes the wrapper chain correctly, then concludes SAFE on a chain that
would break. It is not a retrieval problem — handing it the chain as data
does not fix it, because it was never misreading the chain. Diagnosed
cause: it reasons about the already-imported module's object graph instead
of about re-executing the source file top to bottom, where deleting an
earlier def makes the later capture line raise NameError.

CONSEQUENCE: this ~7.5% clean reasoning-failure rate (see "local_task
raw_text/call_failed fix" and "PLANNER_MAX_TOKENS change" above) is why
the delete_lines structural gate exists. A model that misjudges chain
safety at that rate cannot be the last line of defence on a two-part
deletion.

## eval/analyze.py (reported by user, 2026-08-15; schema finding and arm
figures corroborated this session via eval/analyze.py, see below)

- eval/analyze.py provides load/runs/summarize/compare plus a CLI
  (--list, --run, --compare, --task).
- MEASURED, schema finding: results.jsonl records drop keys depending on
  the code path that produced them — CONTEXT_ERROR and MAX_STEPS never set
  steps. Any steps statistic therefore excludes failed runs unless those
  records are counted explicitly. analyze.py counts them under
  missing_fields.
- MEASURED, arm identification: the two-arm chain runs are distinguishable
  from the data itself — the arm without function_ranges has median 5
  steps, the arm with it has median 3.
- CORRECTION to the two-arm figures already recorded: run 20260815_154155
  (the with-function_ranges arm) predates commit 2d7e07c, so its failures
  include at least one budget overrun miscounted as a reasoning failure.
  Adjusted it is 18/20 rather than 17/20, narrowing the gap to 5 points.
  Both arms predate the fix, so neither is a clean reasoning-failure
  measurement. The conclusion (no evidence function_ranges improves
  correctness) is unaffected; the specific rates should not be cited as
  clean.

Corroborated this session:
```
$ python3 -c "from eval import analyze as a; recs = a.load(); \
  print(a.summarize(recs, run_id='20260815_154155', task_id='chain')['steps']); \
  print(a.summarize(recs, run_id='20260815_153256', task_id='chain')['steps'])"
{'median': 3.0, 'min': 3, 'max': 4}
{'median': 5.0, 'min': 5, 'max': 6}
```
Of the 3 failing chain records in 20260815_154155, one is a raw
`{"thought": ...}` reasoning dump truncated mid-sentence with no SAFE/UNSAFE
verdict — the pre-2d7e07c budget-overrun signature — while the other two
are well-formed SAFE conclusions on a chain that is actually UNSAFE
(genuine reasoning failures).
