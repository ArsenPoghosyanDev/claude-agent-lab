"""Mock support-center tools, defined for the Claude Agent SDK.

Each tool is an async function wrapped with `@tool(name, description, schema)`.
The functions are bundled into an in-process MCP server with
`create_sdk_mcp_server(...)`, which the agent connects to — no separate process,
no network. The data is in-memory so the agent loop is the only moving part.

Tool handlers receive a validated `args` dict and must return:
    {"content": [{"type": "text", "text": "..."}]}
Set "is_error": True to tell the model a call failed.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# --- Fake data ---------------------------------------------------------------

_TICKETS: dict[str, dict] = {
    "T-1001": {
        "id": "T-1001",
        "customer": "Acme Corp",
        "subject": "Invoice export fails with 500",
        "status": "open",
        "priority": "high",
    },
    "T-1002": {
        "id": "T-1002",
        "customer": "Globex",
        "subject": "How do I rotate my API key?",
        "status": "waiting_on_customer",
        "priority": "low",
    },
}

_KB_ARTICLES = [
    {
        "title": "Rotating your API key",
        "keywords": ["api", "key", "rotate", "token", "credential"],
        "body": "Settings -> Security -> API Keys -> 'Rotate'. The old key stays valid for 24h.",
    },
    {
        "title": "Invoice export returns 500",
        "keywords": ["invoice", "export", "500", "error", "download"],
        "body": "Known issue. Workaround: ask the customer to retry after 10pm UTC when load is low.",
    },
    {
        "title": "Resetting a user's password",
        "keywords": ["password", "reset", "login", "locked"],
        "body": "Admins can trigger a reset from Users -> (pick user) -> 'Send reset link'.",
    },
]

_next_ticket_id = 1003


def _text(s: str, is_error: bool = False) -> dict[str, Any]:
    """Build the result shape the Agent SDK expects."""
    out: dict[str, Any] = {"content": [{"type": "text", "text": s}]}
    if is_error:
        out["is_error"] = True
    return out


# --- Tools -------------------------------------------------------------------


@tool(
    "lookup_ticket",
    "Fetch a support ticket by id. Call this whenever the user references a "
    "ticket number like 'T-1001'.",
    {"ticket_id": str},
)
async def lookup_ticket(args: dict[str, Any]) -> dict[str, Any]:
    ticket = _TICKETS.get(args["ticket_id"].strip().upper())
    if ticket is None:
        return _text(f"No ticket found with id {args['ticket_id']!r}.", is_error=True)
    return _text(
        f"{ticket['id']} | {ticket['customer']} | {ticket['subject']} | "
        f"status={ticket['status']} priority={ticket['priority']}"
    )


@tool(
    "search_kb",
    "Search the knowledge base for help articles. Call this before answering "
    "any 'how do I' or troubleshooting question.",
    {"query": str},
)

async def search_kb(args: dict[str, Any]) -> dict[str, Any]:
    try:
        q = args["query"].lower()
        hits = [a for a in _KB_ARTICLES if any(w in q for w in a["keywords"])]
        if not hits:
            return _text("No knowledge-base articles matched that query.")
        return _text("\n".join(f"- {a['title']}: {a['body']}" for a in hits))
    except Exception as e:
        return _text(f"search_kb failed: {e}", is_error=True)


@tool(
    "create_ticket",
    "Open a new support ticket. Only call this when the customer's issue cannot "
    "be resolved from the knowledge base and needs a human.",
    {"subject": str, "body": str, "priority": str},
)
async def create_ticket(args: dict[str, Any]) -> dict[str, Any]:
    global _next_ticket_id
    new_id = f"T-{_next_ticket_id}"
    _next_ticket_id += 1
    _TICKETS[new_id] = {
        "id": new_id,
        "customer": "(new)",
        "subject": args["subject"],
        "status": "open",
        "priority": args.get("priority", "medium"),
    }
    return _text(
        f"Created {new_id} (priority={args.get('priority', 'medium')}): {args['subject']}"
    )


# --- In-process MCP server the agent connects to -----------------------------

SUPPORT_SERVER = create_sdk_mcp_server(
    name="support",
    version="1.0.0",
    tools=[lookup_ticket, search_kb, create_ticket],
)

# Tools are addressed as mcp__<server>__<tool> in allowed_tools.
ALLOWED_TOOLS = [
    "mcp__support__lookup_ticket",
    "mcp__support__search_kb",
    "mcp__support__create_ticket",
]
