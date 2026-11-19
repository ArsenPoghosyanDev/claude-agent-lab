"""Fast, offline tests: no model calls, no network."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools  # noqa: E402
from evals.run_evals import check_tools, parse_judgement  # noqa: E402
from guardrails import approval_hook, auto_approver, deny_approver  # noqa: E402
from tracing import Tracer  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def text(result):
    return result["content"][0]["text"]


# --- tools -------------------------------------------------------------------

def test_lookup_ticket_found_and_case_insensitive():
    out = run(tools.lookup_ticket.handler({"ticket_id": " t-1001 "}))
    assert "Acme Corp" in text(out) and not out.get("is_error")


def test_lookup_ticket_missing_is_error():
    out = run(tools.lookup_ticket.handler({"ticket_id": "T-9999"}))
    assert out["is_error"] is True


def test_search_kb_hit_and_miss():
    assert "Rotating your API key" in text(run(tools.search_kb.handler({"query": "rotate api key"})))
    assert "No knowledge-base" in text(run(tools.search_kb.handler({"query": "okta sso"})))


def test_create_ticket_assigns_new_id():
    out = run(tools.create_ticket.handler({"subject": "SSO down", "body": "x", "priority": "high"}))
    new_id = text(out).split()[1]
    assert new_id in tools._TICKETS


def test_escalate_validates_urgency():
    bad = run(tools.escalate_to_human.handler({"reason": "r", "summary": "s", "urgency": "asap"}))
    assert bad["is_error"] is True
    ok = run(tools.escalate_to_human.handler({"reason": "refund", "summary": "s", "urgency": "high"}))
    assert "human support queue" in text(ok)


# --- guardrails ---------------------------------------------------------------

def _decision(hook_out):
    return hook_out["hookSpecificOutput"]["permissionDecision"]


def test_read_only_tools_skip_approval():
    log = []
    hook = approval_hook(deny_approver, log)
    out = run(hook({"tool_name": "mcp__support__search_kb", "tool_input": {}}, "id1", None))
    assert out == {} and log == []


def test_side_effecting_tool_denied_and_audited():
    log = []
    hook = approval_hook(deny_approver, log)
    out = run(hook({"tool_name": "mcp__support__escalate_to_human", "tool_input": {"reason": "x"}}, "id2", None))
    assert _decision(out) == "deny"
    assert log[0]["approved"] is False


def test_side_effecting_tool_allowed():
    hook = approval_hook(auto_approver)
    out = run(hook({"tool_name": "mcp__support__create_ticket", "tool_input": {}}, "id3", None))
    assert _decision(out) == "allow"


# --- tracing ------------------------------------------------------------------

def test_tracer_records_latency_and_writes_jsonl(tmp_path):
    t = Tracer(run_name="t", out_dir=tmp_path)
    run(t._pre({"tool_name": "mcp__support__lookup_ticket", "tool_input": {"ticket_id": "T-1001"}}, "u1", None))
    run(t._post({"tool_response": {}}, "u1", None))
    run(t._pre({"tool_name": "mcp__support__search_kb", "tool_input": {}}, "u2", None))
    run(t._failed({}, "u2", None))
    assert t.spans[0].tool == "lookup_ticket" and t.spans[0].latency_ms is not None
    assert t.spans[1].is_error is True
    rows = [json.loads(l) for l in t.flush().read_text().splitlines()]
    assert rows[0]["type"] == "tool" and rows[-1]["type"] == "result"


# --- eval helpers -------------------------------------------------------------

def test_check_tools():
    case = {"must_call": ["search_kb"], "must_not_call": ["create_ticket"]}
    assert check_tools(case, ["search_kb"]) == []
    assert check_tools(case, ["create_ticket"]) == ["missing search_kb", "unexpected create_ticket"]


def test_parse_judgement_tolerates_wrapping():
    assert parse_judgement('Sure! {"score": 5, "reason": "good"}')["score"] == 5
    assert parse_judgement("no json")["score"] == 0
