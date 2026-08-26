"""
LangGraph node: prompt injection and PII detection.
"""


from typing import cast
from app.graph.runtime import AgentState
from app.guardrails.prompt_guard import detect_prompt_injection
from app.guardrails.presidio_screen import detect_pii


def guard_node(state: AgentState) -> dict:
    query = cast(str, state.get("query", ""))

    # 1. Empty query check
    if not query.strip():
        return {
            "guard_status": "blocked",
            "guard_reason": "empty_query",
        }

    # 2. Prompt injection / jailbreak detection
    if detect_prompt_injection(query):
        return {
            "guard_status": "blocked",
            "guard_reason": "prompt_injection",
        }

    # 3. PII detection
    if detect_pii(query):
        return {
            "guard_status": "blocked",
            "guard_reason": "pii_detected",
        }

    # 4. Everything passed
    return {
        "guard_status": "allowed",
        "guard_reason": None,
    }


