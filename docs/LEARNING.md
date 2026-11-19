# Learning path — Claude Agent SDK, by doing

> My learning journal from building this repo, coming from 7+ years of
> React/TypeScript. Kept here because it shows how the project grew step by step.

Written for a frontend dev who learns by building and *seeing* results. This file is
the curriculum: each phase has a concept, a way to **see it happen**, and a
**task you implement yourself**. Work top to bottom. The whole thing runs on
your Claude Code subscription (no API key).

> **Where am I / what's done?** See **`PROGRESS.md`** — the live step tracker.
> This file (`LEARNING.md`) is the *concept reference*; `PROGRESS.md` is the
> *order we're actually doing them* and your ✅ checkpoints. Each step there maps
> to a Phase here.

---

## How to SEE the agent work (your "browser / Postman")

As a FE dev you're used to a browser, a Network tab, and Postman. Here are the
three equivalent "windows" into an agent — use all three, they show different layers:

### 1. The browser viewer (closest to what you know)
```bash
source .venv/bin/activate
unset ANTHROPIC_API_KEY
uvicorn web:app --reload
# open http://127.0.0.1:8000
```
Type a question, watch each **assistant message** (blue) and each **tool call**
(yellow) stream in live. This is the agent's "UI" — like watching a page render.

### 2. The terminal (the agent's console)
```bash
python agent.py "ticket T-1001 is broken, what do I tell the customer?"
```
Same loop, printed as text + `-> [tool(args)]` lines. Fast feedback while coding.

### 3. The raw protocol (the agent's "Network tab")
```bash
echo "what is 2+2" | claude -p --output-format stream-json --verbose
```
This dumps the actual JSON messages the SDK consumes — `assistant`, `tool_use`,
`tool_result`, `result`. When something behaves weirdly, this is where you look,
exactly like opening DevTools → Network to see the real request/response.

> Mental model: `agent.py` and `web.py` are *your code*. The SDK runs the
> agent **loop** (decide → call tool → read result → repeat) and hands you a
> stream of typed messages. Your job is to define tools and render messages —
> the same split as "backend gives me JSON, I render the UI."

---

## Phase 0 — it runs (done)

The lab is built and a live run already worked. If you ever see a hang with a
`CPU lacks AVX` warning: the venv must use the **native arm64** Python in
`./python/bin/python3` (an x86/Rosetta Python makes the SDK's subprocess crash).
Rebuild: `rm -rf .venv && ./python/bin/python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

---

## Phase 1 — What *is* the SDK? The agent + tools

**Concept.** An "agent" = a model that, in a loop, decides whether to call a
**tool**, runs it, reads the result, and repeats until it can answer. The SDK
runs that loop. A *tool* = a function you write + a description the model reads.

**See it.** Run the browser viewer and ask *"ticket T-1001 is broken"*. Watch
the order: the model calls `lookup_ticket`, then `search_kb`, then answers. It
chose that order — you didn't script it.

**Tasks.**
1. In `tools.py`, change the `search_kb` **description** to be vague (e.g. just
   "search"). Re-run the same question. Does the agent still call it at the right
   time? → *Lesson: tool descriptions are how the model decides; they're prompt-engineering.*
2. Add a 4th tool `get_customer(name)` that returns a fake plan/tier. Wire it
   into `create_sdk_mcp_server(tools=[...])` **and** `ALLOWED_TOOLS`. Ask a
   question that should trigger it. → *Lesson: the full add-a-capability flow.*

---

## Phase 2 — Options: steering the agent

**Concept.** `ClaudeAgentOptions` is the agent's config: `model`, `system_prompt`,
`allowed_tools` (a whitelist — security boundary), `max_turns` (loop budget),
`permission_mode`.

**See it.** In `agent.py`, set `max_turns=1` and ask the T-1001 question. The
agent can't finish (it runs out of loop steps mid-tool-use). Set it back to 8.

**Tasks.**
1. Switch `MODEL` between `"haiku"`, `"sonnet"`, `"opus"`. Ask the same question
   and compare quality, speed, and the `cost` line. → *Lesson: model is a dial, not a constant.*
2. Remove one tool from `ALLOWED_TOOLS` (but leave it in the server). Ask a
   question needing it. The agent is *told* the tool exists but isn't *allowed*
   to call it — watch what it does instead. → *Lesson: allowed_tools is the guardrail.*

---

## Phase 3 — Context: memory and the conversation window

**Concept.** The model is stateless per call; "memory" = the conversation
history you keep sending. `query()` starts fresh each time; `ClaudeSDKClient`
keeps a session so follow-ups remember earlier turns.

**See it.** `python agent.py -i` (interactive). Ask "look up T-1001", then ask
"what priority was that?" — it remembers, because the session carries context.
Compare: two separate `python agent.py "..."` calls share nothing.

**Tasks.**
1. In `web.py`, switch from `query()` to a persistent `ClaudeSDKClient` so the
   browser keeps context across questions (a real chat). → *Lesson: stateless call vs. stateful session.*
2. Read about **context compaction** (long chats get summarized automatically).
   Make the agent hold a long multi-turn conversation and notice it never errors
   out on length. → *Lesson: the context window is finite; the SDK manages it.*

---

## Phase 4 — Errors: when tools and models fail

**Concept.** Two failure layers: (a) **your tool** errors → return
`{"content": [...], "is_error": True}` so the model sees the failure and adapts;
(b) the **model/process** errors → the SDK raises or returns a non-success
`ResultMessage`.

**See it.** Ask `lookup_ticket` for a ticket that doesn't exist ("look up T-9999").
The tool returns `is_error: True`; watch the agent recover (apologize / suggest
creating one) instead of crashing.

**Tasks.**
1. Make `search_kb` raise a real exception sometimes (e.g. `raise RuntimeError`).
   Confirm the `try/except` in the tool turns it into an `is_error` result and
   the agent keeps going. → *Lesson: never let a tool exception kill the loop.*
2. In `agent.py`, handle `ResultMessage` where `message.is_error` / a non-success
   subtype and print a friendly message. → *Lesson: distinguish tool errors from agent errors.*

---

## Phase 5 — Orchestration: multi-step and sub-agents

**Concept.** Orchestration = coordinating multiple steps or multiple agents.
A single agent already chains tools. The next level: one agent **delegates** a
sub-task to another agent (a sub-agent / specialist), or you run several agents
and combine results.

**See it.** Ask a question that forces several tools in sequence ("customer on
T-1001 also can't reset their password and wants to know your refund policy").
Watch the agent fan out across tools in one turn.

**Tasks.**
1. Build a 2-agent flow in a new script: a **triage** agent that classifies a
   message into {billing, technical, account}, then routes to a **specialist**
   agent with a different `system_prompt` per category. → *Lesson: agents as composable units.*
2. Run 3 agents in parallel (`asyncio.gather`) over 3 different tickets and print
   a combined summary. → *Lesson: parallel orchestration & where it helps.*

---

## Phase 6 — Judgements: the LLM as a grader

**Concept.** A powerful pattern: use a second model call to **evaluate** the
first's output against a rubric ("LLM-as-judge"). Used for self-checking,
quality gates, and automated evals.

**See it.** Take the agent's answer to the T-1001 question and feed it, plus a
rubric ("did it give the CSV workaround? did it end with a next step?"), to a
fresh `query()`. The judge returns pass/fail per criterion.

**Tasks.**
1. Write `judge.py`: run the support agent, then run a judge agent that scores
   the answer against a 3-point rubric and prints a verdict. → *Lesson: closing the quality loop.*
2. Make it a **gate**: if the judge fails the answer, re-run the support agent
   with the judge's feedback appended. → *Lesson: iterate-until-good (the core of agentic evals).*

---

## Phase 7 — The rest of the toolbox (pick what interests you)

- **Permissions / hooks** — intercept tool calls before they run (approve/deny,
  log, redact). Try `permission_mode` and a `can_use_tool` callback.
- **Built-in tools** — drop the `allowed_tools` whitelist and let the agent use
  Claude Code's real `bash`/`read`/`write`. Powerful and dangerous — see why the
  whitelist mattered.
- **Streaming partials** — render tokens as they arrive, not just whole messages.
- **MCP servers** — your `support` server is an in-process MCP server. Connect a
  *real* external MCP server (e.g. a filesystem or GitHub one) and give the agent
  new powers without writing tool code.

---

## Suggested order & pace

Phases 1→2→3 first (the core). Then 4 (errors) and 6 (judgements) — they're the
highest-leverage for understanding *real* agent systems. 5 (orchestration) and 7
are where it gets fun. Do the **tasks**, not just the reading — every concept
here only sticks once you've broken it and fixed it yourself.
