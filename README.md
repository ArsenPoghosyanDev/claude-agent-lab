# claude-agent-lab

A tiny Python learning app for **building an agent with custom tools**, built on
the **Claude Agent SDK** (`claude-agent-sdk`) so it runs on your **Claude Code
subscription** — no separate API key needed.

It's a mock first-line **support agent**: the model answers customer questions
by calling three custom tools — `lookup_ticket`, `search_kb`, and
`create_ticket` — backed by in-memory fake data, so the only thing to study is
the agent itself.

This is the Python counterpart to the team's TS `claude-support-center` starter
(which imports the same SDK family, `@anthropic-ai/claude-agent-sdk`).

## Why the Agent SDK (and not the raw `anthropic` SDK)?

| | Raw `anthropic` Messages SDK | **Claude Agent SDK** (this app) |
| --- | --- | --- |
| Auth | needs a Console **API key** (pay-as-you-go) | uses the **`claude` CLI's** login = your **subscription** |
| Loop | you write the tool loop by hand | the SDK drives the loop |
| Tools | JSON-schema dicts | `@tool` functions in an in-process MCP server |

The Agent SDK shells out to the `claude` CLI, so it authenticates with whatever
you're already logged into in Claude Code.

## Layout

| File              | What it teaches                                                      |
| ----------------- | ------------------------------------------------------------------- |
| `tools.py`        | Define tools with `@tool(...)`, bundle them via `create_sdk_mcp_server`. |
| `agent.py`        | Run the agent with `query()` / `ClaudeSDKClient`, render text + tool calls. |
| `web.py`          | Browser viewer — watch text + tool calls stream live (`uvicorn web:app`). |
| **`LEARNING.md`** | **Start here** — 7-phase, learn-by-doing curriculum with tasks.        |
| `requirements.txt`| `claude-agent-sdk`, `fastapi`, `uvicorn`.                             |

> New here? Open **`LEARNING.md`** — the guided path (how to *see* the agent
> work, plus tasks for agent / context / errors / orchestration / LLM-as-judge).

## Setup

> ⚠️ Use a **native arm64** Python (this repo ships one in `./python/`). An
> x86/Rosetta Python makes the SDK's `claude` subprocess hang with a
> `CPU lacks AVX` warning.

```bash
cd ~/Apps/claude-agent-lab
./python/bin/python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
unset ANTHROPIC_API_KEY
```

**Auth — use your Claude Code subscription.** The only rule:

```bash
unset ANTHROPIC_API_KEY   # if set, it takes precedence and bills the API instead
```

Because you're already logged into Claude Code, that's it. For a headless /CI
machine, mint a portable token instead:

```bash
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN=...   # value printed by the command
```

## Run

```bash
python agent.py                      # canned demo question
python agent.py "How do I rotate my API key?"   # ask your own
python agent.py -i                   # interactive chat (keeps session context)
```

You'll see assistant text plus a `-> [tool(args)]` line each time the agent
calls a tool, so the loop is visible end to end.

## How it works, in one paragraph

`tools.py` defines three async `@tool` functions and wraps them in an
in-process MCP server. `agent.py` passes that server to `ClaudeAgentOptions`
(`mcp_servers=...`, `allowed_tools=[...]`) and runs the agent with `query()`
(one-shot) or `ClaudeSDKClient` (multi-turn). The SDK runs the whole agent loop
— deciding when to call tools, executing them, feeding results back — and yields
`AssistantMessage` (text + `ToolUseBlock`s) and a final `ResultMessage`. Tool
names are addressed as `mcp__support__<tool>`.

## Things to try next

- Add a tool (e.g. `escalate_to_human`): write a `@tool` fn in `tools.py`, add
  it to `create_sdk_mcp_server(tools=[...])` and to `ALLOWED_TOOLS`.
- Switch `MODEL` in `agent.py` between `"sonnet"`, `"opus"`, `"haiku"`.
- Tighten/loosen `max_turns` and watch the loop length change.
- Compare against the raw-SDK approach (needs a Console API key) to feel the
  difference between "drive the loop yourself" and "let the SDK drive it".

## Note on usage

Runs draw from your Claude Code subscription quota. `"sonnet"` is the default
here to keep that modest while you experiment.
