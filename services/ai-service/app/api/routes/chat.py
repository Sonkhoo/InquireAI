"""
Chat endpoint for query-time retrieval and response generation.

Receives a user's chat request and passes it through the retrieval
pipeline before returning a grounded response.
"""

import time

from fastapi import APIRouter

from app.models import ChatRequest, ChatResponse
from app.logging import logfire
from app.config import get_settings
from app.retrieval.hybrid import hybrid_search
from app.retrieval.confidence import compute_confidence
from app.retrieval.synthesizer import synthesize_response


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

settings = get_settings()


@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(request: ChatRequest):
    """
    Process a user chat request through the retrieval pipeline.
    """

    start_time = time.perf_counter()

    logfire.info(
        "chat route: request received",
        thread_id=request.thread_id,
        workspace_id=request.workspace_id,
    )

    # Temporary role list for testing.
    # Eventually this will come from the authenticated gateway/auth layer.
    allowed_role_ids = ["admin"]

    # ------------------------------------------------------------------
    # 1. Hybrid retrieval
    # ------------------------------------------------------------------

    retrieved_chunks = hybrid_search(
        query=request.message,
        workspace_id=request.workspace_id,
        allowed_role_ids=allowed_role_ids,
        limit=5,
    )

    logfire.info(
        "chat route: retrieval complete",
        thread_id=request.thread_id,
        workspace_id=request.workspace_id,
        n_results=len(retrieved_chunks),
    )

    # ------------------------------------------------------------------
    # 2. Compute confidence
    # ------------------------------------------------------------------

    confidence = compute_confidence(
        query=request.message,
        retrieved_chunks=retrieved_chunks,
    )

    logfire.info(
        "chat route: confidence computed",
        thread_id=request.thread_id,
        confidence=confidence,
    )

    # ------------------------------------------------------------------
    # 3. Abstain if confidence is too low
    # ------------------------------------------------------------------

    CONFIDENCE_THRESHOLD = 0.3

    if confidence < CONFIDENCE_THRESHOLD:
        processing_time = time.perf_counter() - start_time

        logfire.warning(
            "chat route: low confidence, abstaining",
            thread_id=request.thread_id,
            confidence=confidence,
        )

        return ChatResponse(
            thread_id=request.thread_id,
            response=(
                "I don't have enough reliable information in the "
                "available documents to answer that question."
            ),
            source="doc_search",
            citations=[],
            confidence=confidence,
            abstained=True,
            model_used=settings.enrich_model,
            processing_time=processing_time,
            token_usage=None,
            cached=False,
        )

    # ------------------------------------------------------------------
    # 4. Generate grounded answer
    # ------------------------------------------------------------------

    synthesized = synthesize_response(
        query=request.message,
        retrieved_chunks=retrieved_chunks,
    )

    # ------------------------------------------------------------------
    # 5. Convert chunk IDs into structured citations
    # ------------------------------------------------------------------

    citations = []

    for chunk_id in synthesized.citations:
        for chunk in retrieved_chunks:
            if chunk.chunk_id == chunk_id:
                citations.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "file_id": chunk.file_id,
                        "filename": chunk.filename,
                        "section_title": chunk.section_title,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                    }
                )
                break

    processing_time = time.perf_counter() - start_time

    logfire.info(
        "chat route: response generated",
        thread_id=request.thread_id,
        workspace_id=request.workspace_id,
        confidence=confidence,
        citations=len(citations),
        processing_time=processing_time,
    )

    return ChatResponse(
        thread_id=request.thread_id,
        response=synthesized.response,
        source="doc_search",
        citations=citations,
        confidence=confidence,
        abstained=False,
        model_used=settings.enrich_model,
        processing_time=processing_time,
        token_usage=None,
        cached=False,
    )