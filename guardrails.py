"""Human-in-the-loop approval for side-effecting tools.

Read-only tools (`lookup_ticket`, `search_kb`) run freely. Tools that change
state (`create_ticket`, `escalate_to_human`) pass through a `PreToolUse` hook
that asks an *approver* first. If the approver says no, the SDK blocks the call
and the model is told why, so it can tell the customer what happens next.

Approval policy comes from the APPROVAL_MODE env var:
    prompt  ask on the terminal (default for the CLI)
    auto    approve everything, but still log it (evals / demos)
    deny    block every side-effecting call (dry-run)
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk import HookMatcher

from tools import APPROVAL_REQUIRED

# An approver gets (tool_name, tool_input) and returns (approved, reason).
Approver = Callable[[str, dict[str, Any]], Awaitable[tuple[bool, str]]]


async def terminal_approver(tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str]:
    short = tool_name.split("__")[-1]
    print(f"\n  [approval needed] {short}({tool_input})")
    answer = input("  approve? [y/N] ").strip().lower()
    if answer in {"y", "yes"}:
        return True, "approved by operator"
    return False, "operator declined this action"


async def auto_approver(tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str]:
    return True, "auto-approved (APPROVAL_MODE=auto)"


async def deny_approver(tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str]:
    return False, "side-effecting tools are disabled (APPROVAL_MODE=deny)"


def approver_from_env() -> Approver:
    mode = os.environ.get("APPROVAL_MODE", "prompt").lower()
    return {"auto": auto_approver, "deny": deny_approver}.get(mode, terminal_approver)


def approval_hook(approver: Approver, audit_log: list[dict[str, Any]] | None = None):
    """Build a PreToolUse hook that gates APPROVAL_REQUIRED tools."""

    async def _hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        name = input_data.get("tool_name", "")
        if name not in APPROVAL_REQUIRED:
            return {}  # read-only tool: no opinion, let it run
        tool_input = input_data.get("tool_input", {}) or {}
        approved, reason = await approver(name, tool_input)
        if audit_log is not None:
            audit_log.append(
                {"tool": name, "input": tool_input, "approved": approved, "reason": reason}
            )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if approved else "deny",
                "permissionDecisionReason": reason,
            }
        }

    return _hook


def approval_hooks(approver: Approver, audit_log: list[dict[str, Any]] | None = None) -> list[HookMatcher]:
    return [HookMatcher(matcher="mcp__support__.*", hooks=[approval_hook(approver, audit_log)])]
