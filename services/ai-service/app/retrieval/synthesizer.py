from __future__ import annotations
import time

from groq import Groq
from groq import APIStatusError, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.logging import logfire
from app.models import Chunk, RetrievedChunk, ChatResponse, Citation, ChunkMetadata, SynthesizedAnswer
from app.config import get_settings

"""
this module contains the logic for synthesizing a response from retrieved chunks.
It uses the Groq API to generate a response based on the retrieved chunks and the user query
"""

settings = get_settings()
# configurations
GROQ_MODEL = settings.enrich_model
DOC_TOKEN_THRESHOLD = 6000
MAX_ENRICH_RETRIES = 3
GROQ_API_KEY = settings.GROQ_API_KEY

SYSTEM_PROMPT = """
You are an enterprise knowledge assistant.

Answer the user's question using ONLY the supplied retrieved context.

Return your response as valid JSON.

The JSON object must have exactly these fields:
- "response": the grounded answer as a string
- "citations": an array of chunk IDs supporting the answer

Rules:
1. Do not use outside knowledge.
2. Do not invent facts.
3. Every factual claim derived from the retrieved context must be
   supported by one or more citation chunk IDs.
4. Citations MUST contain only chunk IDs supplied in the retrieved context.
5. Never invent a chunk ID.
6. Do not invent filenames, page numbers, sections, or other metadata.
7. If the retrieved context does not contain enough information to answer
   the question, say so clearly and return an empty citations array.
8. Do not expose internal chunk IDs in the natural-language response.
9. Return only the JSON object. Do not wrap it in markdown or code fences.
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


    client = Groq(api_key=GROQ_API_KEY)

    response = client.chat.completions.create(
        model=settings.enrich_model,
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

    result = SynthesizedAnswer.model_validate_json(
        response.choices[0].message.content
    )

    return result