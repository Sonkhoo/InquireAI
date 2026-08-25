from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict
from app.graph.runtime import AgentState
from app.llm import get_groq_client, get_secondary_model
from app.logging import logfire

class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str = Field(
        description=(
            "Route for the user's current query. "
            "Must be either general_chat or doc_search."
        )
    )


def intent_router_node(state: AgentState) -> dict:
    query = state.get("query", "")
    messages = state.get("messages", [])

    recent_messages = messages[-10:]

    conversation = "\n".join(
        f"{type(message).__name__}: {message.content}"
        for message in recent_messages
    )

    prompt = f"""
You are an intent router for an agentic RAG assistant.

Decide whether the user's CURRENT query requires document
retrieval or can be answered as normal conversation.

Conversation:
{conversation}

CURRENT QUERY:
{query}

Choose exactly one route:

general_chat:
- Greetings
- Casual conversation
- Personal conversation based on the conversation history
- Questions answerable from the conversation itself
- Questions that do not require external documents
- Follow-up questions whose answer is already contained in the conversation

doc_search:
- Questions requiring information from documents
- Questions asking about company/internal knowledge
- Questions requiring retrieval from the knowledge base
- Questions where the user explicitly asks about a document/file
- Follow-up questions about previously discussed information when
  the answer requires retrieving additional document information

Important:
The existence of conversation history does NOT automatically mean
general_chat.

Return only the route.
"""

    client = get_groq_client()

    response = client.chat.completions.create(
        model=get_secondary_model(),
        messages=[
            {
                "role": "system",
                "content": prompt,
            }
        ],
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "strict": True,
                "name": "rewritten_query",
                "schema": RouteDecision.model_json_schema(),
            },
        },
    )

    if not response.choices:
        raise ValueError("Router received no choices from Groq.")

    content = response.choices[0].message.content

    if not content:
        raise ValueError(
            f"Router received empty response: {response!r}"
        )

    decision = RouteDecision.model_validate_json(content)

    if decision.route not in ("general_chat", "doc_search"):
        raise ValueError(
            f"Invalid route returned by router: {decision.route}"
        )

    logfire.info("Intent router decision", route=decision.route)

    return {
        "route": decision.route,
    }