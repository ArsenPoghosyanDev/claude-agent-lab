"""Offline-style evaluation of the support agent.

Each case in cases.jsonl is scored two ways:

1. Deterministic tool checks: did the agent call every tool in `must_call`
   and none of the tools in `must_not_call`? (Read off the tracer's spans.)
2. LLM-as-judge: a separate, tool-less Claude call grades the final answer
   against the case's rubric on a 1-5 scale and returns JSON.

A case passes when the tool checks pass AND the judge score >= 4.
The script prints a table, writes evals/report.json, and exits non-zero if the
pass rate is below --threshold, so it can gate CI.

    APPROVAL_MODE=auto python -m evals.run_evals            # all cases
    python -m evals.run_evals --only angry-refund kb-api-key
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from agent import _options  # noqa: E402
from guardrails import auto_approver  # noqa: E402
from tracing import Tracer  # noqa: E402

JUDGE_MODEL = "haiku"
PASS_SCORE = 4

JUDGE_PROMPT = """You are grading a customer-support agent's reply.

Customer message:
<input>{input}</input>

Agent's final reply:
<reply>{reply}</reply>

Tools the agent called, in order: {tools}

Rubric (what a good reply must do):
<rubric>{rubric}</rubric>

Score 1-5: 5 = fully meets the rubric, 4 = meets it with minor issues,
3 = partially, 2 = mostly misses, 1 = wrong or invents facts.
Respond with ONLY a JSON object: {{"score": <1-5>, "reason": "<one sentence>"}}"""


def load_cases(only: list[str] | None) -> list[dict]:
    cases = [json.loads(l) for l in (ROOT / "cases.jsonl").read_text().splitlines() if l.strip()]
    return [c for c in cases if not only or c["id"] in only]


async def run_agent(case: dict) -> tuple[str, Tracer]:
    tracer = Tracer(run_name=case["id"], out_dir=None)
    texts: list[str] = []
    async for msg in query(prompt=case["input"], options=_options(approver=auto_approver, tracer=tracer)):
        if isinstance(msg, AssistantMessage):
            texts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
        elif isinstance(msg, ResultMessage):
            tracer.record_result(msg)
    return "\n".join(texts).strip(), tracer


def check_tools(case: dict, called: list[str]) -> list[str]:
    problems = [f"missing {t}" for t in case.get("must_call", []) if t not in called]
    problems += [f"unexpected {t}" for t in case.get("must_not_call", []) if t in called]
    return problems


def parse_judgement(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        return {"score": int(data["score"]), "reason": str(data.get("reason", ""))}
    except (ValueError, KeyError, TypeError):
        return {"score": 0, "reason": f"unparseable judge output: {raw[:120]!r}"}


async def judge(case: dict, reply: str, called: list[str]) -> dict:
    prompt = JUDGE_PROMPT.format(
        input=case["input"], reply=reply or "(empty)", tools=called or "none", rubric=case["rubric"]
    )
    opts = ClaudeAgentOptions(model=JUDGE_MODEL, tools=[], max_turns=1,
                              system_prompt="You are a strict, fair evaluator. Output JSON only.")
    raw = ""
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, AssistantMessage):
            raw += "".join(b.text for b in msg.content if isinstance(b, TextBlock))
    return parse_judgement(raw)


async def evaluate(case: dict) -> dict:
    reply, tracer = await run_agent(case)
    called = [s.tool for s in tracer.spans]
    problems = check_tools(case, called)
    verdict = await judge(case, reply, called)
    return {
        "id": case["id"],
        "passed": not problems and verdict["score"] >= PASS_SCORE,
        "tool_problems": problems,
        "tools_called": called,
        "judge_score": verdict["score"],
        "judge_reason": verdict["reason"],
        "cost_usd": tracer.result.get("cost_usd"),
        "duration_ms": tracer.result.get("duration_ms"),
        "reply": reply,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="case ids to run")
    ap.add_argument("--threshold", type=float, default=0.8, help="min pass rate (0-1)")
    args = ap.parse_args()

    results = []
    for case in load_cases(args.only):
        r = await evaluate(case)
        results.append(r)
        mark = "PASS" if r["passed"] else "FAIL"
        note = "; ".join(r["tool_problems"]) or r["judge_reason"]
        print(f"{mark}  {r['id']:<24} judge={r['judge_score']}  tools={r['tools_called']}  {note}")

    passed = sum(r["passed"] for r in results)
    rate = passed / len(results) if results else 0.0
    cost = sum(r["cost_usd"] or 0 for r in results)
    print(f"\n{passed}/{len(results)} passed ({rate:.0%}), ~${cost:.4f} estimated")
    (ROOT / "report.json").write_text(json.dumps({"pass_rate": rate, "results": results}, indent=2))
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
