"""A minimal support-center agent built on the Claude Agent SDK.

Unlike the raw Messages API, this SDK runs the Claude Code engine under the
hood, so it authenticates with whatever the `claude` CLI is logged into — your
Claude Code subscription. (Make sure ANTHROPIC_API_KEY is NOT set, or it bills
the API instead. Headless/CI: run `claude setup-token` and export the printed
CLAUDE_CODE_OAUTH_TOKEN.)

The agent answers support questions using four custom in-process tools defined
in tools.py. Side-effecting tools (create_ticket, escalate_to_human) need human
approval (guardrails.py), and every tool call is traced with latency and the
run's cost (tracing.py).

Run it:
    python agent.py                 # one canned demo question
    python agent.py "your question" # ask your own
    python agent.py -i              # interactive chat (keeps session context)
    APPROVAL_MODE=auto python agent.py "..."   # skip the approval prompt
"""

from __future__ import annotations

import asyncio
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from guardrails import Approver, approval_hooks, approver_from_env
from tools import ALLOWED_TOOLS, SUPPORT_SERVER
from tracing import Tracer, merge_hooks

# "haiku" = lightest on your subscription allowance — good default for practice.
# Use "sonnet" for better answers, "opus" for the strongest model.
MODEL = "haiku"

SYSTEM_PROMPT = (
    "You are a first-line support agent for a SaaS product. "
    "Use the tools to look up tickets and search the knowledge base before "
    "answering. Be concise and friendly. If you can't resolve an issue from "
    "the knowledge base, open a ticket. If the customer is angry, asks for a "
    "refund, reports a security problem, or asks for a person, escalate to a "
    "human. Never invent ticket ids, policies or refunds. If an action is not "
    "approved, say so and tell the customer what happens next. "
    "Always end with a clear next step."
)


def _options(
    approver: Approver | None = None,
    tracer: Tracer | None = None,
    audit_log: list | None = None,
) -> ClaudeAgentOptions:
    hooks = {"PreToolUse": approval_hooks(approver or approver_from_env(), audit_log)}
    if tracer is not None:
        hooks = merge_hooks(tracer.hooks(), hooks)
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"support": SUPPORT_SERVER},
        allowed_tools=ALLOWED_TOOLS,  # whitelist: only our tools, no bash/file access
        hooks=hooks,
        max_turns=8,
    )


def _print_message(message) -> None:
    """Render assistant text + tool activity as the agent works."""
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
            elif isinstance(block, ToolUseBlock) and block.name.startswith("mcp__"):
                # only our own tools; skip the SDK's internal ToolSearch noise
                short = block.name.split("__")[-1]
                print(f"  -> [{short}({block.input})]")
    elif isinstance(message, ResultMessage):
        if message.total_cost_usd:
            # NOTE: this is an API-price *estimate*, not a charge. On a Claude
            # Code subscription it's drawn from your plan, not billed per-token.
            print(f"  (~${message.total_cost_usd:.4f} plan usage — not a charge)")


async def ask_once(question: str) -> None:
    print(f"you> {question}\nagent>")
    tracer = Tracer(run_name="ask")
    async for message in query(prompt=question, options=_options(tracer=tracer)):
        _print_message(message)
        if isinstance(message, ResultMessage):
            tracer.record_result(message)
    print("\n" + tracer.summary())
    print(f"  trace written to {tracer.flush()}")


async def interactive() -> None:
    print("Support agent ready. Type a message (Ctrl-C or 'quit' to exit).\n")
    async with ClaudeSDKClient(options=_options()) as client:
        while True:
            try:
                user = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return
            if user.lower() in {"quit", "exit"}:
                return
            if not user:
                continue
            print("agent>")
            await client.query(user)
            async for message in client.receive_response():
                _print_message(message)
            print()


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in {"-i", "--interactive"}:
        asyncio.run(interactive())
        return

    question = (
        " ".join(args)
        if args
        else "Customer says ticket T-1001 is still broken. What's going on and what should I tell them?"
    )
    asyncio.run(ask_once(question))


if __name__ == "__main__":
    main()
