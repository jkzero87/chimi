# chimi

## 1. What this is

A local agent that works on files on this PC. It runs a plan-act-observe
loop (`agent/loop.py:local_task`): the model proposes one tool call at a
time, sees the real output, and decides whether it has enough evidence to
answer. The tools (`agent/tools.py`) are:

- `list_dir(path)` — list a directory
- `read_file(path, start_line, end_line)` — read a file, optionally just a
  line range
- `grep_files(pattern, path)` — recursive text search
- `run_safe_bash(cmd)` — shell commands, validated segment by segment
  against an allowlist
- `write_file(path, content, dry_run=True)` / `delete_lines(path,
  start_line, end_line, dry_run=True)` — the write tools; `dry_run`
  defaults to `True` on both

This is a **separate project** from the search assistant in `llm/harness`,
which answers questions from the web using two models (an executor and a
supervisor, on ports 8090/8091). The word "harness" here refers to the
scaffolding *pattern* — planner, judge, retry loop — not to either project
by name. `llm/harness` and `llm/chimi` do not share code, models, or
a PROJECT_TRUTH.md.

## 2. Prerequisites

A `llama-server` must be running on `PORT` (from `config.py`, default
`8092`, env-overridable via `CHIMI_PORT`) serving `MODEL_PATH` (from
`config.py`). See `agent/server.py` to start/stop/check it.

Only one `llama-server` fits in this card's 16GB VRAM (PROJECT_TRUTH.md),
so this project **cannot run at the same time** as the search assistant on
ports 8090/8091.

## 3. Profiles

| | `fast` (default) | `deep` |
|---|---|---|
| Context | 8192 | 32768 |
| MTP | `--spec-type draft-mtp --spec-draft-n-max 2` | none |
| KV cache | default | `-ctk q8_0 -ctv q8_0` (halved, so 32768 fits) |
| For | everyday tool-use tasks | long-context analysis over large spans of a file at once |

`fast` is the default (`config.DEFAULT_PROFILE`). Measured 2026-08-15, 3 eval
runs each: `fast` scored 15/15 at ~72s per run, `deep` scored 14/15 at ~133s
per run. The 8192 context of `fast` is enough because the tools deliver
fragments (grep matches, line ranges) rather than whole files, so the model
rarely needs long context.

`--spec-draft-n-max 3` is never used on either profile — see Known Limits.

## 4. Running

Start a profile and check what's running:

```python
from agent.server import ensure, current_profile

ensure("fast")          # no-op if "fast" is already up; otherwise stops
                         # whatever is on PORT and starts "fast"
current_profile()        # "fast", "deep", "unknown" (something else is on
                         # PORT), or None (nothing listening)
```

Run a task directly:

```python
from agent.loop import local_task

result = local_task(
    "How many times is result_score defined in "
    "agente_eval_u2m2mizm/research.py?",
    max_steps=14,
)
```

This is a real recorded example (`eval/results.jsonl`, `run_id
20260815_101436`, profile `deep`, 2 steps, 15.73s):

```
result = {
    "status": "OK",
    "answer": "result_score is defined 6 times in "
              "agente_eval_u2m2mizm/research.py (lines 578, 968, 1353, "
              "1583, 1818, and 1971).",
    "steps": 2,
}
```

Run the eval suite (`eval/tasks.py`, `eval/run_eval.py`):

```
.venv/bin/python eval/run_eval.py                          # DEFAULT_PROFILE (fast), all 5 tasks, 1 run
.venv/bin/python eval/run_eval.py --profile deep            # force deep
.venv/bin/python eval/run_eval.py --only chain              # just the chain task
.venv/bin/python eval/run_eval.py --runs 3                  # repeat every selected task 3 times
```

Each task line prints `[id] PASS/FAIL profile=... steps=... seconds=...
reasons=[...]`; every run also appends one JSON record per task to
`eval/results.jsonl`.

## 5. What it has actually done

On 2026-08-15 the agent removed all five shadowed `result_score`
definitions from the real `llm/harness/research.py` (six definitions were
present; Python was silently running the last one, the other five were dead
code). Each deletion was reviewed as a dry run (the tool contract requires
showing the diff before a real write — see Safety model) before being
applied for real, with a timestamped backup taken automatically on each
write. Verification per the commit message: `grep -c '^def result_score'`
went 6 → 1, `_original_result_score` and its dead wrapper were confirmed
gone, `ast.parse` and a real `import` succeeded, and the `build_evidence_pack`
and `format_evidence` `_orig_` chains were confirmed untouched.

Reference: commit `7702d58` ("Remove all five shadowed result_score
definitions") in the harness repo (`data-engineer-prep`,
`llm/harness/research.py`).

## 6. Safety model

- `dry_run` defaults to `True` on both write tools; nothing is written
  unless the caller explicitly passes `dry_run=False`.
- `.py` targets are validated with `ast.parse` before any write —
  `write_file` on the proposed content, `delete_lines` on the result after
  the deletion — refusing with a `RECHAZADO` message and touching nothing on
  disk if the result would not parse.
- Every real write makes a timestamped backup first
  (`<path>.bak_YYYYMMDD_HHMMSS`, via `shutil.copy2`) — `write_file` only
  when it is overwriting a file that already existed; `delete_lines` always,
  since its target must already exist.
- `run_safe_bash` rejects backtick, `$(`, `>`, `<`, and a lone `&` outright
  (no redirection, no command substitution), then splits the command on
  `|`, `;`, `&&`, `||` and requires every segment's first token to be in the
  `SAFE_CMDS` allowlist before running anything.
- All paths are sandboxed to `ROOT` (the user's home directory) —
  `_safe`/`_safe_new` resolve the path and reject anything outside `ROOT`;
  `_safe` also requires the target to already exist, `_safe_new` only
  requires the parent directory to exist.

## 7. Known limits

- `--spec-draft-n-max 3` is **forbidden** on both profiles. It benchmarks
  faster (58 t/s) on a short prompt but dies with a CUDA out-of-memory error
  in `cudaGraphLaunch` on the first real-sized request. Loading successfully
  does not mean it works. (PROJECT_TRUTH.md)
- On `deep`, a large prompt with the default `reasoning_effort` (`xhigh`)
  can consume the entire `max_tokens` budget on reasoning and return empty
  content. Lowering `reasoning_effort` to `medium` fixed it in the one
  recorded case (17,635-token prompt, empty at `xhigh`/12000 tokens in
  ~8.7min vs. a correct answer at `medium`/14000 tokens in ~4min). This has
  not occurred in any eval run, where tools deliver fragments rather than
  whole files. (PROJECT_TRUTH.md, "reasoning_effort and long-context
  analysis on 'deep'", user-reported, not verified in this session)
- The `chain` task (does deduplicating `build_evidence_pack` to its last
  definition require keeping the `_orig_` chain?) has a clean
  reasoning-failure rate of about 7.5% (3 failures in 40 runs, measured
  after the budget-overrun confound was eliminated — see
  PROJECT_TRUTH.md). The failure mode is constant: the model describes the
  wrapper chain correctly, then concludes SAFE on a chain that would
  break. It is not a retrieval problem — it reasons about the
  already-imported module's object graph instead of about the source file
  re-executing top to bottom, where deleting an earlier `def` makes the
  later capture line raise `NameError`. Giving it `function_ranges` does
  not fix this: a two-arm experiment found no correctness difference (see
  PROJECT_TRUTH.md), only fewer steps and less time. This rate is why the
  `delete_lines` structural gate exists — chain/safety judgments like this
  should not be trusted unsupervised before a destructive edit.
