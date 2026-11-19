"""Lightweight tracing: per-tool-call latency plus per-run cost and tokens.

`Tracer` plugs into the SDK through PreToolUse / PostToolUse hooks, so it sees
every tool call the model makes without touching the tools themselves. At the
end of a run, `record_result()` adds the run's cost, turns and token usage
from the SDK's `ResultMessage`. Spans are appended to a JSONL file
(traces/run-<timestamp>.jsonl by default) that you can grep, load into pandas,
or ship to any log pipeline.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookMatcher, ResultMessage


@dataclass
class ToolSpan:
    tool: str
    tool_use_id: str
    input: dict[str, Any]
    started_at: float
    latency_ms: float | None = None
    is_error: bool = False


@dataclass
class Tracer:
    run_name: str = "run"
    out_dir: Path | None = Path("traces")
    spans: list[ToolSpan] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    _open: dict[str, ToolSpan] = field(default_factory=dict, repr=False)

    # --- hooks -----------------------------------------------------------
    async def _pre(self, input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        span = ToolSpan(
            tool=input_data.get("tool_name", "?").split("__")[-1],
            tool_use_id=tool_use_id or "",
            input=input_data.get("tool_input", {}) or {},
            started_at=time.perf_counter(),
        )
        self._open[span.tool_use_id] = span
        self.spans.append(span)
        return {}

    async def _post(self, input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        span = self._open.pop(tool_use_id or "", None)
        if span is not None:
            span.latency_ms = round((time.perf_counter() - span.started_at) * 1000, 1)
            resp = input_data.get("tool_response")
            span.is_error = bool(isinstance(resp, dict) and resp.get("is_error"))
        return {}

    async def _failed(self, input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        span = self._open.get(tool_use_id or "")
        await self._post(input_data, tool_use_id, context)
        if span is not None:
            span.is_error = True
        return {}

    def hooks(self) -> dict[str, list[HookMatcher]]:
        m = "mcp__support__.*"
        return {
            "PreToolUse": [HookMatcher(matcher=m, hooks=[self._pre])],
            "PostToolUse": [HookMatcher(matcher=m, hooks=[self._post])],
            "PostToolUseFailure": [HookMatcher(matcher=m, hooks=[self._failed])],
        }

    # --- results ---------------------------------------------------------
    def record_result(self, msg: ResultMessage) -> None:
        usage = msg.usage or {}
        self.result = {
            "cost_usd": msg.total_cost_usd,
            "duration_ms": msg.duration_ms,
            "num_turns": msg.num_turns,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "is_error": msg.is_error,
        }

    def summary(self) -> str:
        lines = [f"trace: {self.run_name}"]
        for s in self.spans:
            flag = " ERROR" if s.is_error else ""
            lines.append(f"  {s.tool:<18} {s.latency_ms if s.latency_ms is not None else '?':>7} ms{flag}")
        r = self.result
        if r:
            lines.append(
                f"  total {r.get('duration_ms')} ms | turns {r.get('num_turns')} | "
                f"tokens in/out {r.get('input_tokens')}/{r.get('output_tokens')} | "
                f"~${(r.get('cost_usd') or 0):.4f}"
            )
        return "\n".join(lines)

    def flush(self) -> Path | None:
        if self.out_dir is None:
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{self.run_name}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        with path.open("a") as f:
            for s in self.spans:
                row = asdict(s)
                row.pop("started_at")
                f.write(json.dumps({"type": "tool", **row}) + "\n")
            f.write(json.dumps({"type": "result", **self.result}) + "\n")
        return path


def merge_hooks(*groups: dict[str, list[HookMatcher]]) -> dict[str, list[HookMatcher]]:
    out: dict[str, list[HookMatcher]] = {}
    for g in groups:
        for event, matchers in g.items():
            out.setdefault(event, []).extend(matchers)
    return out
