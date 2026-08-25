from __future__ import annotations

from langgraph.runtime import Runtime
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

from app.graph.runtime import AgentState, RequestContext
from app.llm import get_secondary_model, get_groq_client
from groq.types.chat import ChatCompletionMessageParam
from app.logging import logfire

def general_chat_node(
    state: AgentState,
    runtime: Runtime[RequestContext],
) -> dict:
    """
    Generate a conversational response using the checkpointed
    conversation history.

    This node does not use RAG or query rewriting.
    """

    model_name = get_secondary_model()
    client = get_groq_client()

    messages = state.get("messages", [])

    if not messages:
        raise ValueError("No conversation messages available.")

    groq_messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": (
                "You are a helpful conversational assistant. "
                "Use the conversation history to answer the user's "
                "current question. Do not invent information."
            ),
        }
    ]

    for message in messages:
        if isinstance(message, HumanMessage):
            groq_messages.append({
                "role": "user",
                "content": str(message.content),
            })

        elif isinstance(message, AIMessage):
            groq_messages.append({
                "role": "assistant",
                "content": str(message.content),
            })

        elif isinstance(message, SystemMessage):
            groq_messages.append({
                "role": "system",
                "content": str(message.content),
            })

    response = client.chat.completions.create(
        model=model_name,
        messages=groq_messages,
        reasoning_effort="low",
        max_tokens=500,
        temperature=0.3
    )

    if not response.choices:
        raise ValueError(
            f"Groq returned no choices: {response!r}"
        )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise ValueError(
            "Groq returned empty content. "
            f"finish_reason={response.choices[0].finish_reason}, "
            f"response={response!r}"
        )
    logfire.info("General chat response generated", content_preview=content[:200])
    logfire.info("Messages used for response generation", messages=groq_messages)
    answer = content.strip()

    return {
        "answer": answer,
        "messages": [
            AIMessage(content=answer)
        ],
        "model_used": model_name,
    }