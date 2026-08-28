import numpy as np

from app.models import RetrievedChunk
from app.logging import logfire


def _sigmoid(x: float) -> float:
    """Convert a cross-encoder score into a bounded relevance signal."""
    return float(1.0 / (1.0 + np.exp(-np.clip(x, -10.0, 10.0))))


def _compute_top_evidence(
    rerank_scores: np.ndarray,
) -> float:
    """Strength of the single best cross-encoder result."""
    if len(rerank_scores) == 0:
        return 0.0

    return _sigmoid(float(rerank_scores[0]))


def _compute_evidence_agreement(
    rerank_scores: np.ndarray,
    k: int = 3,
) -> float:
    """
    Measures how consistently the top-k reranked chunks
    support the query.
    """
    if len(rerank_scores) == 0:
        return 0.0

    top_k = rerank_scores[:k]

    normalized_scores = np.array(
        [_sigmoid(float(score)) for score in top_k],
        dtype=float,
    )

    return float(np.mean(normalized_scores))


def compute_confidence(
    query: str,
    retrieved_chunks: list[RetrievedChunk],
    top_k_agreement: int = 3,
) -> float:
    if not retrieved_chunks:
        logfire.info(
            f"No retrieved chunks for query: '{query}'. "
            "Confidence: 0.0."
        )
        return 0.0

    # Keep only chunks that have a cross-encoder score.
    chunks_with_rerank = [
        chunk
        for chunk in retrieved_chunks
        if chunk.rerank_score is not None
    ]

    if not chunks_with_rerank:
        logfire.warning(
            f"No reranker scores available for query: '{query}'. "
            "Confidence: 0.0."
        )
        return 0.0

    # Sort by cross-encoder score.
    chunks_with_rerank.sort(
        key=lambda chunk: float(chunk.rerank_score or 0.0),
        reverse=True,
    )

    # At this point we know every chunk has a rerank score.
    # Explicitly narrow the type for the type checker.
    rerank_scores = np.array(
        [
            float(score)
            for chunk in chunks_with_rerank
            if (score := chunk.rerank_score) is not None
        ],
        dtype=float,
    )

    top_evidence = _compute_top_evidence(
        rerank_scores
    )

    evidence_agreement = _compute_evidence_agreement(
        rerank_scores,
        k=top_k_agreement,
    )

    confidence = (
        0.60 * top_evidence
        + 0.40 * evidence_agreement
    )

    confidence = float(
        np.clip(confidence, 0.0, 1.0)
    )

    logfire.info(
        "Deterministic confidence computed",
        query=query,
        confidence_score=round(confidence, 4),
        top_evidence=round(top_evidence, 4),
        evidence_agreement=round(evidence_agreement, 4),
        top_rerank_score=round(
            float(rerank_scores[0]),
            4,
        ),
        retrieved_count=len(retrieved_chunks),
        reranked_count=len(chunks_with_rerank),
    )

    return confidence