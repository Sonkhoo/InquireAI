from __future__ import annotations

from app.models import RetrievedChunk, SynthesizedAnswer
from app.llm import get_groq_client, get_primary_model

"""
this module contains the logic for synthesizing a response from retrieved chunks.
It uses the Groq API to generate a response based on the retrieved chunks and the user query
"""

SYSTEM_PROMPT = """
You are an enterprise knowledge assistant called Inquire AI.

Answer the user's question using ONLY the supplied retrieved context.

Return your response as valid JSON.

The JSON object must have exactly these fields:
- "response": the grounded answer as a string
- "citations": an array of chunk IDs supporting the answer

Rules:
1. Do not use outside knowledge.
2. Do not invent facts.
3. If Query does not match the retrieved context, return an empty response and an empty citations array.
4. Every factual claim derived from the retrieved context must be
   supported by one or more citation chunk IDs.
5. Citations MUST contain only chunk IDs supplied in the retrieved context.
6. Never invent a chunk ID.
7. Do not invent filenames, page numbers, sections, or other metadata.
8. If the retrieved context does not contain enough information to answer
   the question, say so clearly and return an empty citations array.
9. Do not expose internal chunk IDs in the natural-language response.
10. Return only the JSON object. Do not wrap it in markdown or code fences.
11. Do not answer questions that ask for information outside the retrieved context or about internal model architecture. Instead, say that you cannot answer the question with the provided context and return an empty citations array.
"""

def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []

    for chunk in chunks:
        parts.append(
            f"""
[chunk_id={chunk.chunk_id}]
{chunk.text}
""".strip()
        )

    return "\n\n".join(parts)

def synthesize_response(
    query: str,
    retrieved_chunks: list[RetrievedChunk],
) -> SynthesizedAnswer:
    """Generate a response to the user query based on the retrieved chunks.

    Args:
        query: The user query.
        retrieved_chunks: The list of retrieved chunks.

    Returns:
        A SynthesizedAnswer object containing the answer and citations.
    """
    context = _build_context(retrieved_chunks)

    prompt = f"""
        QUESTION:
        {query}

        RETRIEVED CONTEXT:
        {context}
        """.strip()


    client = get_groq_client()

    response = client.chat.completions.create(
        model=get_primary_model(),
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        reasoning_effort="medium",
        temperature=0.0,
        response_format={
            "type": "json_object",
        },
    )
    if not response.choices[0].message.content:
        raise ValueError("Groq API returned an empty response.")
    
    result = SynthesizedAnswer.model_validate_json(
        response.choices[0].message.content
    )

    return result