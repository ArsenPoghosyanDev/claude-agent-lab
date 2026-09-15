# Progress tracker — tutor steps

How we work: you do a Step, report the **checkpoint**, I confirm, then hand you
the next Step. This file is the durable record (chat may be compacted). Concepts
live in `LEARNING.md`; this is the **order we're doing them** + what's done.

- Practice model: **haiku** (lightest on plan usage). Auth: **subscription** (keep `ANTHROPIC_API_KEY` unset).
- We front-loaded errors/orchestration before context/options for momentum — same
  concepts as `LEARNING.md`, just a different order. Mapping is noted per step.

## Status

| Step | Title | Maps to LEARNING.md | Status |
|------|-------|---------------------|--------|
| 1 | Run & read the loop | Phase 1 | ✅ done |
| 2 | See & change tool output | Phase 1 | ✅ done |
| 3 | Tool failure & `is_error` | Phase 4 | ✅ done |
| 4 | Orchestration (routing) | Phase 5 | ✅ done |
| 5 | Judgements (LLM-as-judge) | Phase 6 | 🔨 in progress |
| 6 | Context & memory | Phase 3 | planned |
| 7 | Options & permissions | Phase 2 / 7 | planned |

---

## Step 1 — Run & read the loop ✅
- **Goal:** see the agent *decide* which tools to call, in what order.
- **Did:** ran `web.py` (browser) + `agent.py` on "T-1001 is broken".
- **Result:** `lookup_ticket → search_kb → answer`.
- **Learned:** the model chooses the tools and their order — you don't script it.

## Step 2 — See & change tool output ✅
- **Goal:** a tool = a function returning text; that text drives the answer.
- **Did:** added `print(...)` in `_text()` to reveal tool returns; edited a KB article `body`.
- **Result:** the agent's answer followed the edited text.
- **Learned:** tools feed the model facts it doesn't have. Also: haiku is *less
  proactive* than sonnet (model = a dial).

## Step 3 — Tool failure & `is_error` ✅
- **Goal:** tools fail; return `is_error=True` so the model adapts instead of crashing.
- **Did:** (A) looked up **T-9999** → `is_error` "not found"; agent recovered.
  (B) simulated a KB outage (`raise` inside `try/except` → `is_error`); agent
  **opened a ticket instead** and told the customer honestly.
- **Learned:** *return `is_error`* = model sees the failure and reroutes; *raise*
  = uncaught exception kills the run. Always catch inside tools.
- **Side note:** `create_ticket` only writes an **in-memory dict** — nothing
  persists across runs (optional side-quest: back it with `tickets.json`).

## Step 4 — Orchestration (routing) ✅
- **Goal:** coordinate *multiple* agents — a triage agent classifies, a specialist answers.
- **Task:** create `orchestrate.py` (triage → route to billing / technical / account
  specialist by system prompt). Run 3 different messages; watch the routing.
- **Checkpoint:** 1) category per message  2) do specialists sound different  3) in
  your words, what does *your code* do vs. what does *each agent* do.

## Step 5 — Judgements (LLM-as-judge) — planned
Run the support agent, then a second "judge" agent grades the answer against a
rubric (pass/fail). Then gate: if it fails, re-run with the feedback.

## Step 6 — Context & memory — planned
`query()` (stateless) vs `ClaudeSDKClient` (keeps session). Make the browser chat
remember earlier turns. See context compaction on long chats.

## Step 7 — Options & permissions — planned
`model`, `max_turns`, `allowed_tools` whitelist, `permission_mode`, `can_use_tool`
hooks. Drop the whitelist and see the agent reach for real bash/file tools.
