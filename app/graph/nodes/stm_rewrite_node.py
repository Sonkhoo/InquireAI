from __future__ import annotations
from typing import Optional
from app.graph.runtime import AgentState
from pydantic import BaseModel, Field, ConfigDict
from app.llm import get_groq_client, get_secondary_model
from app.logging import logfire

class RewrittenQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rewritten_query: str = Field(...,
        description="The rewritten query after STM processing."
    )


def stm_rewrite_node(state: AgentState) -> dict:
    """
    LangGraph node: Short Term Memory (STM) rewrite of the query.
    This node rewrites the query based on the current conversation context and previous messages.
    """
    query = state.get("query", "")
    session_history = state.get("session_history", [])

    # No history -> no need for complex rewriting.
    if not session_history:

        return {
            "rewritten_query": query,
        }

    conversation = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in session_history
    )
    logfire.info("STM rewrite input", query=query, conversation=conversation)

    prompt = f"""
    You are a query-resolution component for an enterprise AI assistant.

    Convert the user's CURRENT query into a standalone query using
    the previous conversation only when necessary.

    Conversation history:

    {conversation}

    CURRENT USER QUERY:

    {query}

    Rules:

    1. Preserve the exact intent of the current query.

    2. Resolve pronouns such as:
    "it", "this", "that", "they", "those".

    3. Resolve references to entities mentioned earlier.

    4. Do not answer the question.

    5. Do not add information that was not present in the conversation.

    6. If the current query is already standalone, return it unchanged.

    7. Do not rewrite a casual greeting into a knowledge query.

    8. Return the response in JSON format.

    Return only the structured output requested by the schema.
    """

    client = get_groq_client()

    response = client.chat.completions.create(
        model=get_secondary_model(),
        messages=[
            {
                "role": "system",
                "content": prompt,
            },
        ],
        reasoning_effort="medium",
        temperature=0.0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "strict": True,
                "name": "rewritten_query",
                "schema": RewrittenQuery.model_json_schema(),
            },
        }
    )
    if not response.choices[0].message.content:
            raise ValueError(
                "Groq API returned an empty structured response. "
                f"finish_reason={response.choices[0].finish_reason}, "
                f"message={response.choices[0].message}"
            )

    result = RewrittenQuery.model_validate_json(
        response.choices[0].message.content
    )
    logfire.info("STM rewrite result", rewritten_query=result.rewritten_query)
    return {
        "rewritten_query": result.rewritten_query
    }