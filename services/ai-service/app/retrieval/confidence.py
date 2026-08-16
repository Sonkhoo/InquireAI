import numpy as np
from app.models import RetrievedChunk
from app.logging import logfire

# AI GENERATED CODE CAUSE I AINT DOING ALL THAT MATHS 
def compute_confidence(
    query: str, 
    retrieved_chunks: list[RetrievedChunk], 
    alpha: float = 0.2,
    low_confidence_threshold: float = -8.0
) -> float:
    """
    Computes a robust confidence score for a RAG pipeline combining 
    RRF Hybrid retrieval scores and Cross-Encoder Reranker logits.

    Args:
        query: The user's query string.
        retrieved_chunks: Chunks fetched by the retrieval pipeline.
        alpha: Weight given to retrieval score vs rerank score.
               Defaults to 0.2 (giving 80% weight to the Reranker).
        low_confidence_threshold: Cross-Encoder logit floor. Scores below this
                                  are treated as complete noise/off-topic.

    Returns:
        float: Final RAG system confidence score bounded between 0.0 and 1.0.
    """
    if not retrieved_chunks:
        logfire.info(f"No retrieved chunks for query: '{query}'. Confidence: 0.0.")
        return 0.0

    # 1. Extract raw scores
    retrieval_scores = np.array([chunk.retrieval_score for chunk in retrieved_chunks], dtype=float)
    rerank_scores = np.array([
        chunk.rerank_score if chunk.rerank_score is not None else -10.0 
        for chunk in retrieved_chunks
    ], dtype=float)

    # 2. Normalize RRF Retrieval Scores (Safe to use Min-Max because RRF is rank-relative)
    r_min, r_max = retrieval_scores.min(), retrieval_scores.max()
    r_range = r_max - r_min
    if r_range > 0:
        retrieval_norm = (retrieval_scores - r_min) / r_range
    else:
        retrieval_norm = np.ones_like(retrieval_scores)

    # 3. Normalize Cross-Encoder Scores using an Absolute Sigmoid Function
    # We clip to [-10, 10] to prevent exponential overflow/underflow errors
    rerank_norm = 1 / (1 + np.exp(-np.clip(rerank_scores, -10.0, 10.0)))

    # 4. Apply a Hard Penalty for off-topic queries
    # If the BEST chunk fails our threshold, force the final score to near zero
    if rerank_scores.max() < low_confidence_threshold:
        logfire.warning(f"Off-topic query detected: '{query}'. Max logit is {rerank_scores.max()}.")
        # Scale the confidence strictly into a zero-bound bucket
        return float(np.mean(rerank_norm) * 0.1)

    # 5. Linear Fusion per chunk
    combined_scores = (alpha * retrieval_norm) + ((1 - alpha) * rerank_norm)

    # 6. Sort descending to prepare for rank decay
    combined_scores = np.sort(combined_scores)[::-1]

    # 7. Aggregate with Harmonic Rank Decay (Position 1 matters more than position 5)
    rank_weights = 1.0 / (np.arange(len(combined_scores)) + 1)
    confidence_score = np.average(combined_scores, weights=rank_weights)

    logfire.info(f"Computed confidence for query: '{query}' is {confidence_score:.4f}.")
    return float(confidence_score)
