"""
LangGraph node: hybrid retrieval (dense + sparse, RRF-fused).
Reranking happens separately in rerank_node.
"""

from typing import cast, Literal
from langgraph.runtime import Runtime
from app.logging import logfire
from app.graph.runtime import AgentState, RequestContext
from app.llm import get_groq_client, get_primary_model
from app.retrieval.hybrid import hybrid_search
from pydantic import BaseModel, Field, ConfigDict

class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["search"] = Field(
        description="The agent must perform exactly one knowledge-base search."
    )

    query: str = Field(
        description=(
            "The exact search query to send to the knowledge-base "
            "retrieval tool."
        )
    )

    reason: str = Field(
        description="Why this search query is needed."
    )



def retrieval_planner_node(state: AgentState, runtime: Runtime[RequestContext]) -> dict:
    """
    Bounded retrieval agent.

    The agent decides the next search query but performs only ONE
    retrieval operation per graph iteration.

    The graph controls the loop and maximum number of searches.
    """

    user_query = state.get("query", "")  # the original raw user query

    rewritten_query = state.get(
        "rewritten_query",
        user_query,
    )

    retrieval_query = state.get(
        "retrieval_query",
        rewritten_query,
    )

    evidence = state.get(
        "evidence_chunks",
        [],
    )
    missing_information = state.get(
        "missing_information",
        "",
    )

    # Cold start / no new info: the STM-resolved query IS the right search.
    # Skip the planner LLM call entirely to save latency and tokens.
    hop_count = state.get("hop_count", 0)

    # First retrieval: use the STM-resolved query directly.
    # No planner LLM call is needed.
    if hop_count == 0:
        logfire.info(
            "Retrieval planner: initial retrieval",
            retrieval_query=rewritten_query,
            hop_count=hop_count,
        )

        return {
            "retrieval_query": rewritten_query,
        }

    # Serialize evidence as readable text instead of dumping Pydantic objects
    evidence_text = "\n\n".join(
        f"[{chunk.chunk_id}] {chunk.text[:500]}"
        for chunk in evidence
    )

    prompt = f"""
You are the retrieval agent for an enterprise RAG system.

Your job is to identify the best query for ONE knowledge-base
retrieval operation.

You are NOT responsible for answering the user.

The graph controls:
- retrieval execution
- maximum number of searches
- termination
- synthesis
- abstention

You only determine the next retrieval query.

Original user question:
{user_query}

STM-resolved query:
{rewritten_query}

Current retrieval query:
{retrieval_query}

Previously accumulated evidence:
{evidence_text}

The previous evidence evaluator determined that the following
information is still missing:

{missing_information}

Generate the next retrieval query specifically targeting this
missing information.

Instructions:

1. Generate exactly ONE retrieval query.

2. The query must target information required to answer the
   original user question.
3. If previous evidence exists, use it to identify what information
   is still missing.
4. Do not invent facts.
5. Do not answer the user's question.
6. Do not repeat the previous query unless absolutely necessary.
7. If the query is a question, rephrase it as a declarative statement.

Return the most useful query for the next knowledge-base search.
"""
    client = get_groq_client()
    response = client.chat.completions.create(
        model=get_primary_model(),
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
                "name": "agent_action",
                "schema": AgentAction.model_json_schema(),
            },
        }
    )
    if not response.choices[0].message.content:
            raise ValueError(
                "Groq API returned an empty structured response. "
                f"finish_reason={response.choices[0].finish_reason}, "
                f"message={response.choices[0].message}"
            )

    result = AgentAction.model_validate_json(
        response.choices[0].message.content
    )
    logfire.info("Based on Evidence retrieval query", retrieval_query=result.query)

    return {
        "retrieval_query": result.query,
    }