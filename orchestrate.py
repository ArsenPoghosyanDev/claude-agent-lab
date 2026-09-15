import asyncio
import sys

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

MODEL = "haiku"

SPECIALISTS = {
    "billing":   "You are a billing specialist. Be precise about invoices, charges, and refunds.",
    "technical": "You are a technical support engineer. Give concrete, numbered troubleshooting steps.",
    "account":   "You are an account specialist. Help with logins, passwords, and account settings.",
}


async def _text_of(prompt: str, system: str) -> str:
    """Run one agent, return its text."""
    out = ""
    async for m in query(prompt=prompt, options=ClaudeAgentOptions(model=MODEL, system_prompt=system)):
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock):
                    out += b.text
    return out


async def main() -> None:
    msg = " ".join(sys.argv[1:]) or "I was charged twice this month, can I get a refund?"
    print(f"you> {msg}")

    # 1) TRIAGE agent — classify into one word.
    label = await _text_of(
        msg, 
        "Classify the user's message into exactly ONE word: billing, technical, or account. "
        "Reply with only that word, lowercase.",
    )
    category = label.strip().lower().split()[0] if label.strip() else "technical"
    print(f"[triage] -> {category}")

    # 2) YOUR CODE routes to the matching SPECIALIST agent.
    system = SPECIALISTS.get(category, "You are a helpful support agent.")
    print(f"[{category} specialist]>")
    print(await _text_of(msg, system))


if __name__ == "__main__":
    asyncio.run(main())