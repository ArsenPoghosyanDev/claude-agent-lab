"""Browser viewer for the agent — watch the agent loop live.

Runs the same agent as agent.py, but streams every step (assistant text, each
tool call, the final result) to a web page over Server-Sent Events. Open it,
type a question, and watch the agent loop happen live in your browser — the
agent equivalent of a Network tab.

Run:
    source .venv/bin/activate
    unset ANTHROPIC_API_KEY
    uvicorn web:app --reload
    # open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from agent import _options  # reuse the exact same agent config
from guardrails import approver_from_env, deny_approver

# The browser viewer has no approval UI yet: side-effecting tools are blocked
# unless you start it with APPROVAL_MODE=auto.
_WEB_APPROVER = approver_from_env() if os.environ.get("APPROVAL_MODE") == "auto" else deny_approver

app = FastAPI()

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>claude-agent-lab</title>
<style>
  body { font: 15px/1.5 -apple-system, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.2rem; }
  #log { margin-top: 1rem; }
  .turn { border-left: 3px solid #ddd; padding: .3rem .7rem; margin: .4rem 0; white-space: pre-wrap; }
  .text { border-color: #4a90d9; }
  .tool { border-color: #e0a500; background: #fff8e1; font-family: ui-monospace, monospace; font-size: 13px; }
  .done { border-color: #2e7d32; color: #2e7d32; font-size: 13px; }
  input { width: 70%; padding: .5rem; } button { padding: .5rem 1rem; }
</style></head><body>
<h1>claude-agent-lab — watch the agent loop</h1>
<form id="f"><input id="q" placeholder="e.g. ticket T-1001 is broken, what do I tell the customer?" autofocus>
<button>Ask</button></form>
<div id="log"></div>
<script>
const log = document.getElementById('log');
function add(kind, text) {
  const d = document.createElement('div');
  d.className = 'turn ' + kind;
  d.textContent = (kind === 'tool' ? '→ ' : '') + text;
  log.appendChild(d); window.scrollTo(0, document.body.scrollHeight);
}
document.getElementById('f').onsubmit = (e) => {
  e.preventDefault();
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  log.innerHTML = ''; add('text', 'you> ' + q);
  const es = new EventSource('/ask?q=' + encodeURIComponent(q));
  es.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.kind === 'end') { es.close(); return; }
    add(m.kind, m.text);
  };
  es.onerror = () => es.close();
};
</script></body></html>"""


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse(PAGE)


def _sse(kind: str, text: str) -> str:
    return f"data: {json.dumps({'kind': kind, 'text': text})}\n\n"


@app.get("/ask")
async def ask(q: str) -> StreamingResponse:
    async def stream():
        async for message in query(prompt=q, options=_options(approver=_WEB_APPROVER)):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield _sse("text", block.text)
                    elif isinstance(block, ToolUseBlock) and block.name.startswith("mcp__"):
                        # only our own tools; skip the SDK's internal ToolSearch noise
                        short = block.name.split("__")[-1]
                        yield _sse("tool", f"{short}({block.input})")
            elif isinstance(message, ResultMessage):
                # estimate only — subscription usage, not a charge
                cost = f" (~${message.total_cost_usd:.4f} plan usage)" if message.total_cost_usd else ""
                yield _sse("done", "done" + cost)
        yield _sse("end", "")

    return StreamingResponse(stream(), media_type="text/event-stream")
