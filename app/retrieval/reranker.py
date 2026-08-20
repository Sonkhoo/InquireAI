"""
Cross Encoder Reranker for Qdrant retrieval results based on pairs[query, qdrant retrieved chunk text] using a pretrained model from HuggingFace.
"""

from sentence_transformers import CrossEncoder
from app.models import RetrievedChunk
from app.logging import logfire
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")



def rerank_chunks(query: str, retrieved_chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """
    Rerank the retrieved chunks based on the query using a cross-encoder model.

    Args:
        query (str): The user's query.
        retrieved_chunks (list[RetrievedChunk]): List of retrieved chunks from Qdrant.

    Returns:
        list[RetrievedChunk]: Reranked list of chunks with updated scores.
    """
    pairs = [(query, chunk.text) for chunk in retrieved_chunks]

    scores = model.predict(pairs)

    print(f"Scores from cross-encoder: {scores}")

    scored_chunks = list(zip(retrieved_chunks, scores))

    scored_chunks.sort(
        key=lambda item: float(item[1]),
        reverse=True,
    )

    for chunk, score in scored_chunks:
        chunk.rerank_score = float(score)

    return [chunk for chunk, _ in scored_chunks]
