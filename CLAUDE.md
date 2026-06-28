# CLAUDE.md


----


Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
---


## Commit & versioning convention (THIS REPO — follow exactly)

- **main carries ONE commit per session**: `floatN: <session headline>`
  (N increments once per session; e.g. Session F = 2.4.16, Session G = 2.4.17).
- **During a session, develop on a session branch** with step commits
  `floatN.m: <change>` (m = 1, 2, 3, …). Each step commit is small,
  self-contained, and carries measured results in its message where relevant.
- **Land on main via GitHub "Squash and merge".** ⚠️ **The squash dialog PREFILLS the
  commit title from the PR/branch name** (e.g. `Claude/handoff continuation prep … (#2)`)
  — that is WRONG and must NOT be accepted. **Manually overwrite the title to
  `floatN: <session headline>`** where:
  - **N is the session number** — the SAME N as this session's `…N.m` step commits (check
    `git log --oneline` on the branch; e.g. steps `float19.61–.76` → squash
    title `float19: …`). Do NOT include the step suffix `.m` in the squash title.
  - **`<session headline>` SUMMARIZES THE WHOLE SESSION'S NET OUTCOME** — the end result /
    headline metric achieved ACROSS ALL the step commits — NOT a copy of the last step commit.
    State the before→after of the session's main metric. (E.g. session 2.4.19 →
    `float19: float thread — Phase-1 per-ticker float recovery COMPLETE on the
    150-sample: within-5%-of-DT-float 90.7%→100% (150/150), within-1% 76%→86%; 15 imperfect
    names solved in isolation.`)
  (Exact same `floatN` format as every other main commit — check
  `git log main --oneline` first.) Keep the prefilled list of step messages in the body.
  A trailing ` (#N)` PR reference is fine. Keep (or tag) the session branch afterwards so the
  step-by-step history survives the squash. If the title was already merged wrong, fix it by
  amending the squash commit on main and force-pushing (message-only rewrite).
- In committed docs, reference **step-commit numbers (2.4.N.m) or branch names, not
  raw hashes** — squashing/rebasing invalidates hashes.
- `version.txt` is user-maintained — do not update it.
- Never commit credentials (`sapi.txt`/`mapi.txt`/`dbapi.txt`), `data/`, `*.jsonl`,
  or bulk artifacts (see `.gitignore` and `REBUILD.md`).

**ON STARTUP / AFTER ANY CONTEXT COMPRESSION:** before acting, re-read the latest
`FLOAT_HANDOFF_*` — its **§Durable Knowledge** (the load-bearing facts) and its
**§current state / in-progress** (the live work state). Conversation memory may be
summarized lossily; the committed handoff + git history are the source of truth.

**Working rules:**  Commit each self-contained step as
`floatN.m` with before/after numbers; **commit working state
frequently** (so a compression/restart loses no progress); keep the latest handoff's
current-state section fresh.

----



## TEMP INSTRUCTIONS

use only 12 agents at a time. make sure that it's work is interuption reselient, so if the llm is stopped by usage credits, it can pick up again later.  let me know if there are any concerns before you start.